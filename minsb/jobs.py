"""Utilities related to Sparv jobs."""

import subprocess
from enum import IntEnum

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


def get_status(user, corpus_id):
    """Get PID and status of a Sparv job."""
    job_id = get_id(user, corpus_id)
    mc = app.config.get("cache_client")
    mc_return = mc.get(job_id)

    # Job does not exist in cache
    if mc_return is None:
        return Status.none

    # Check process if possible
    pid, status = mc_return
    if status == Status.running:
        if not process_running(pid):
            status = Status.done
            set_status(user, corpus_id, status)

    # TODO: Error detection?

    return status


def set_status(user, corpus_id, status, pid=None):
    """Set or update the status of a Sparv job."""
    job_id = get_id(user, corpus_id)
    mc = app.config.get("cache_client")
    if pid is None:
        mc_return = mc.get(job_id)
        if mc_return is None:
            raise Exception(f"Job '{job_id}' does not exist!")
        pid, _ = mc_return
    mc.set(job_id, (pid, status))
    app.logger.debug(f"Job in cache: '{mc.get(job_id)}'")


def clear_job():
    """Erase job from memory."""
    pass


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
