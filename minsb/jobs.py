"""Utilities related to Sparv jobs."""

import json
from os import mkdir
import subprocess
from enum import IntEnum
from pathlib import Path

from flask import current_app as app

from minsb import paths


class Status(IntEnum):
    """Class for representing the status of a Sparv job."""

    none = 0
    running = 1
    error = 2
    done = 3


def get_id(user, corpus_id):
    """Create an ID for a Sparv job."""
    return f"{user}_{corpus_id}"


def get_status(oc, user, corpus_id):
    """Get PID and status of a Sparv job."""
    job_id = get_id(user, corpus_id)
    mc = app.config.get("cache_client")
    mc_return = mc.get(job_id)

    if mc_return is not None:
        pid, status = mc_return

    # Job does not exist in cache, check Nextcloud
    else:
        pid, status = get_from_nc(oc, corpus_id)
        mc.set(job_id, (pid, status))
        # Job does not exist in Nextcloud either
        if status == Status.none:
            return status

    # Check process if possible
    if status == Status.running:
        if not process_running(pid):
            status = Status.done
            set_status(oc, user, corpus_id, status)

    # TODO: Error detection?

    return status


def set_status(oc, user, corpus_id, status, pid=None):
    """Set or update the status of a Sparv job."""
    job_id = get_id(user, corpus_id)
    mc = app.config.get("cache_client")
    if pid is None:
        mc_return = mc.get(job_id)
        if mc_return is None:
            raise Exception(f"Job '{job_id}' does not exist!")
        pid, _ = mc_return

    # Store in Memcached
    mc.set(job_id, (pid, status))
    # Store in Nextcloud as backup
    try:
        statusfile = str(paths.get_corpus_dir(domain="nc", corpus_id=corpus_id, oc=oc)
                         / Path(app.config.get("NC_STATUS_FILE")))
        oc.put_file_contents(statusfile, json.dumps({"pid": pid, "status": status.name}))
    except Exception as e:
        app.logger.error(f"Failed to safe job status in Nextcloud: {e}")

    app.logger.debug(f"Job in cache: '{mc.get(job_id)}'")


def get_from_nc(oc, corpus_id):
    """Get job status info from Nextcloud."""
    app.logger.debug("Getting status from Nextcloud")
    status_file = str(paths.get_corpus_dir(domain="nc", corpus_id=corpus_id, oc=oc)
                      / Path(app.config.get("NC_STATUS_FILE")))
    try:
        file_contents = oc.get_file_contents(status_file)
        status_obj = json.loads(file_contents)
        return status_obj.get("pid", 0), getattr(Status, status_obj.get("status", "none"))
    except Exception:
        return 0, Status.none


def process_running(pid):
    """Check if process with pid is running on Sparv server."""
    sparv_user = app.config.get("SPARV_USER")
    sparv_server = app.config.get("SPARV_SERVER")
    p = subprocess.run(["ssh", "-i", "~/.ssh/id_rsa", f"{sparv_user}@{sparv_server}", f"kill -0 {pid}"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.stderr:
        app.logger.debug(f"stderr: '{p.stderr.decode()}'")
        if p.stderr.decode().endswith("No such process\n"):
            return False
        if p.stderr.decode().endswith("Operation not permitted\n"):
            # TODO: what do we do if we don't have permission to check the process?
            return False
    return True


def get_output(user, corpus_id):
    """Check latest Sparv output by reading the nohup file."""
    nohupfile = app.config.get("SPARV_NOHUP_FILE")
    remote_corpus_dir = str(paths.get_corpus_dir(domain="sparv", user=user, corpus_id=corpus_id))
    sparv_user = app.config.get("SPARV_USER")
    sparv_server = app.config.get("SPARV_SERVER")

    p = subprocess.run(["ssh", "-i", "~/.ssh/id_rsa", f"{sparv_user}@{sparv_server}",
                        f"cd /home/{sparv_user}/{remote_corpus_dir} && tail {nohupfile}"],
                       capture_output=True)

    stdout = p.stdout.decode().strip().split("\n") if p.stdout else ""
    if stdout[-1].startswith("Progress:"):
        return stdout[-1]
    return " ".join([line for line in stdout if line and not line.startswith("Progress:")])


def clear_job():
    """Erase job from Memcached and Nextcloud."""
    # TODO
    pass
