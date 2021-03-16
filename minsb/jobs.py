"""Utilities related to Sparv jobs."""

import hashlib
import json
import re
import subprocess
from enum import IntEnum
from itertools import count
from pathlib import Path

from flask import current_app as app

from minsb import exceptions, paths, utils

_status_count = count(0)


class Status(IntEnum):
    """Class for representing the status of a Sparv job.

    Inspired from:
    https://stackoverflow.com/questions/64038885/adding-attributes-and-starting-value-to-python-enum-intenum
    """

    none = "Job does not exist"
    syncing_corpus = "Syncing from Nextcloud to Sparv server"
    waiting = "Waiting to be run with Sparv"
    annotating = "Sparv annotation process is running"
    done_annotating = "Annotation process has finished"
    syncing_results = "Syncing results from Sparv to Nextcloud"
    done = "Results have been synced to Nexcloud"
    error = "An error occurred"
    aborted = "Aborted by the user"

    def __new__(cls, desc):
        value = next(_status_count)
        member = int.__new__(cls, value)
        member._value_ = value
        member.desc = desc
        return member


class Job():
    """A job item holding information about a Sparv job."""

    def __init__(self, user, corpus_id, status=Status.none, pid=None, sparv_exports=None):
        self.user = user
        self.corpus_id = corpus_id
        self.id = hashlib.sha1(f"{self.user}{self.corpus_id}".encode("UTF-8")).hexdigest()[:10]
        self.status = status
        self.pid = pid
        self.sparv_exports = sparv_exports or []

        self.sparv_user = app.config.get("SPARV_USER")
        self.sparv_server = app.config.get("SPARV_SERVER")
        self.nohupfile = app.config.get("SPARV_NOHUP_FILE")
        self.runscript = app.config.get("SPARV_TMP_RUN_SCRIPT")
        self.remote_corpus_dir = str(paths.get_corpus_dir(domain="sparv", user=self.user, corpus_id=self.corpus_id))

    def __str__(self):
        return json.dumps({"user": self.user, "corpus_id": self.corpus_id, "status": self.status.name, "pid": self.pid,
                           "sparv_exports": self.sparv_exports})

    def save(self):
        """Write a job item to the cache and filesystem."""
        dump = json.dumps({"user": self.user, "corpus_id": self.corpus_id, "status": self.status.name, "pid": self.pid,
                           "sparv_exports": self.sparv_exports})
        # Save in cache
        utils.memcached_set(self.id, dump)
        # Save backup to file system queue
        queue_dir = Path(app.instance_path) / Path(app.config.get("QUEUE_DIR"))
        queue_dir.mkdir(exist_ok=True)
        backup_file = queue_dir / Path(self.id)
        with backup_file.open("w") as f:
            f.write(dump)

    def remove(self, abort=False):
        """Remove a job item from the cache and file system."""
        if self.status == Status.annotating:
            if abort:
                try:
                    self.abort_sparv()
                except exceptions.ProcessNotRunning:
                    pass
                except Exception as e:
                    raise e
            else:
                raise exceptions.JobError("Job cannot be removed due to a running Sparv process!")

        # Remove from cache
        mc = app.config.get("cache_client")
        mc.delete(self.id)
        # Remove backup from file system
        queue_dir = Path(app.instance_path) / Path(app.config.get("QUEUE_DIR"))
        filename = queue_dir / Path(self.id)
        filename.unlink(missing_ok=True)

    def set_status(self, status):
        """Change the status of a job."""
        if not self.status == status:
            self.status = status
            self.save()

    def set_pid(self, pid):
        """Set pid of job and save."""
        self.pid = pid
        self.save()

    def sync_to_sparv(self, oc):
        """Sync corpus files from Nextcloud to the Sparv server."""
        self.set_status(Status.syncing_corpus)

        # Get relevant directories
        nc_corpus_dir = str(paths.get_corpus_dir(domain="nc", corpus_id=self.corpus_id))
        local_user_dir = str(paths.get_corpus_dir(user=self.user, mkdir=True))

        # Check if required corpus contents are present
        corpus_contents = utils.list_contents(oc, nc_corpus_dir, exclude_dirs=False)
        if not app.config.get("SPARV_CORPUS_CONFIG") in [i.get("name") for i in corpus_contents]:
            self.set_status(Status.error)
            raise Exception(f"No config file provided for '{self.corpus_id}'!")
        if not len([i for i in corpus_contents if i.get("path").endswith(app.config.get("SPARV_SOURCE_DIR"))]):
            self.set_status(Status.error)
            raise Exception(f"No input files provided for '{self.corpus_id}'!")

        # Create file index with timestamps
        file_index = utils.create_file_index(corpus_contents, self.user)

        # Create user and corpus dir on Sparv server
        p = subprocess.run(["ssh", "-i", "~/.ssh/id_rsa", f"{self.sparv_user}@{self.sparv_server}",
                            f"cd /home/{self.sparv_user} && mkdir -p {self.remote_corpus_dir} && "
                            f"rm -f {self.nohupfile} {self.runscript}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p.stderr:
            self.set_status(Status.error)
            raise Exception(f"Failed to create corpus dir on Sparv server! {p.stderr.decode()}")

        # Download from Nextcloud to local tmp dir
        # TODO: do this async?
        try:
            utils.download_dir(oc, nc_corpus_dir, local_user_dir, self.corpus_id, file_index)
        except Exception as e:
            self.set_status(Status.error)
            raise Exception(f"Failed to download corpus '{self.corpus_id}' from Nextcloud! {e}")

        # Sync corpus config to Sparv server
        p = subprocess.run(["rsync", "-av", paths.get_config_file(user=self.user, corpus_id=self.corpus_id),
                            f"{self.sparv_user}@{self.sparv_server}:~/{self.remote_corpus_dir}/"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p.stderr:
            self.set_status(Status.error)
            raise Exception(f"Failed to copy corpus config file to Sparv server! {p.stderr.decode()}")

        # Sync corpus files to Sparv server
        # TODO: do this async!
        local_source_dir = paths.get_source_dir(user=self.user, corpus_id=self.corpus_id)
        p = subprocess.run(["rsync", "-av", "--delete", local_source_dir,
                            f"{self.sparv_user}@{self.sparv_server}:~/{self.remote_corpus_dir}/"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p.stderr:
            self.set_status(Status.error)
            raise Exception(f"Failed to copy corpus files to Sparv server! {p.stderr.decode()}")

        # TODO: Set this status when done syncing
        self.set_status(Status.waiting)

    def run_sparv(self):
        """Start a Sparv annotation process."""
        sparv_env = app.config.get("SPARV_ENVIRON")
        sparv_command = f"{app.config.get('SPARV_COMMAND')} {app.config.get('SPARV_RUN')} {' '.join(self.sparv_exports)}"
        p = subprocess.run(["ssh", "-i", "~/.ssh/id_rsa", f"{self.sparv_user}@{self.sparv_server}",
                            (f"cd /home/{self.sparv_user}/{self.remote_corpus_dir}"
                             f" && echo '{sparv_env} nohup {sparv_command} >{self.nohupfile} 2>&1 &\necho $!' > {self.runscript}"
                             f" && chmod +x {self.runscript} && ./{self.runscript}")],
                           # f" && nohup {sparv_command} > {nohupfile} 2>&1 & echo $!")],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if p.returncode != 0:
            stderr = p.stderr.decode() if p.stderr else ""
            self.set_status(Status.error)
            raise exceptions.JobError(f"Failed to run Sparv! {stderr}")

        # Get pid from Sparv process and store job info
        self.set_pid(int(p.stdout.decode()))
        self.set_status(Status.annotating)

    def abort_sparv(self):
        """Abort running Sparv process."""
        if not self.status == Status.annotating:
            raise exceptions.ProcessNotRunning("Failed to abort job because Sparv was not running!")
        if not self.pid:
            raise exceptions.ProcessNotFound("Failed to abort job because no process ID was found!")

        p = subprocess.run(["ssh", "-i", "~/.ssh/id_rsa", f"{self.sparv_user}@{self.sparv_server}",
                            f"kill -SIGTERM {self.pid}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p.returncode == 0:
            self.set_pid(None)
            self.set_status(Status.aborted)
        else:
            raise exceptions.JobError(f"Failed to abort job! Error: '{p.stderr.decode()}'")

    def process_running(self):
        """Check if process with this job's pid is still running on Sparv server."""
        if not self.pid:
            return False

        p = subprocess.run(["ssh", "-i", "~/.ssh/id_rsa", f"{self.sparv_user}@{self.sparv_server}",
                            f"kill -0 {self.pid}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p.returncode == 0:
            self.set_status(Status.annotating)
            return True
        else:
            app.logger.debug(f"stderr: '{p.stderr.decode()}'")
            self.set_pid(None)
            progress, _warnings, errors, nothing_to_be_done = self.get_output()
            if (progress == "Progress: 100%" or nothing_to_be_done):
                self.set_status(Status.done_annotating)
            else:
                app.logger.debug(f"Error in Sparv: {errors}")
                self.set_status(Status.error)
            return False

    def get_output(self):
        """Check latest Sparv output of this job by reading the nohup file."""
        if self.status < Status.annotating:
            return ""

        nohupfile = app.config.get("SPARV_NOHUP_FILE")
        remote_corpus_dir = str(paths.get_corpus_dir(domain="sparv", user=self.user, corpus_id=self.corpus_id))

        p = subprocess.run(["ssh", "-i", "~/.ssh/id_rsa", f"{self.sparv_user}@{self.sparv_server}",
                            f"cd /home/{self.sparv_user}/{remote_corpus_dir} && cat {nohupfile}"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        stdout = p.stdout.decode().strip() if p.stdout else ""
        progress = warnings = errors = ""
        if stdout:
            progress = [line for line in stdout.split("\n") if line.startswith("Progress:")]
            progress = progress[-1] if progress else ""
            warnings = []
            errors = []
            for msg in re.findall(r"^\d\d:\d\d:\d\d (WARNING|ERROR)\s+(.+(?:\n\s{8,}.+)*)", stdout, flags=re.MULTILINE):
                m = "{} {}".format(msg[0], re.sub(r"\s*\n\s+", " ", msg[1].strip()))
                if msg[0] == "WARNING":
                    warnings.append(m)
                else:
                    errors.append(m)
            warnings = "\n".join(warnings)
            errors = "\n".join(errors)
            nothing_to_be_done = stdout.startswith("Nothing to be done.")
        return progress, warnings, errors, nothing_to_be_done

    def sync_results(self, oc):
        """Sync exports from Sparv server to Nextcloud."""
        local_corpus_dir = str(paths.get_corpus_dir(user=self.user, corpus_id=self.corpus_id, mkdir=True))
        nc_corpus_dir = str(paths.get_corpus_dir(domain="nc", corpus_id=self.corpus_id))

        corpus_contents = utils.list_contents(oc, nc_corpus_dir, exclude_dirs=False)
        file_index = utils.create_file_index(corpus_contents, self.user)

        remote_export_dir = paths.get_export_dir(domain="sparv", user=self.user, corpus_id=self.corpus_id)
        p = subprocess.run(["rsync", "-av", f"{self.sparv_user}@{self.sparv_server}:~/{remote_export_dir}",
                            local_corpus_dir], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p.stderr:
            return utils.response("Failed to retrieve Sparv exports!", err=True, info=p.stderr.decode()), 404

        # Transfer exports to Nextcloud
        local_export_dir = paths.get_export_dir(user=self.user, corpus_id=self.corpus_id)
        try:
            utils.upload_dir(oc, nc_corpus_dir, local_export_dir, self.corpus_id, self.user, file_index)
        except Exception as e:
            raise Exception(f"Failed to upload exports to Nextcloud! {e}")
        self.set_status(Status.done)

    def remove_from_sparv(self):
        """Remove corpus dir from the Sparv server and abort running job if necessary."""
        try:
            self.abort_sparv()
        except exceptions.ProcessNotRunning:
            pass
        except Exception as e:
            raise e

        p = subprocess.run(["ssh", "-i", "~/.ssh/id_rsa", f"{self.sparv_user}@{self.sparv_server}",
                            f"rm -rf /home/{self.sparv_user}/{self.remote_corpus_dir}"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p.stderr:
            app.logger.error(f"Failed to remove corpus dir '{self.remote_corpus_dir}'!")

    def clean(self):
        """Remove annotation files from Sparv server by running 'sparv clean'."""
        sparv_command = app.config.get("SPARV_COMMAND") + " clean --all"
        p = subprocess.run([
            "ssh", "-i", "~/.ssh/id_rsa", f"{self.sparv_user}@{self.sparv_server}",
            f"cd /home/{self.sparv_user}/{self.remote_corpus_dir} && rm -f {self.nohupfile} {self.runscript} && "
            f"{sparv_command}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if p.stderr:
            raise Exception(p.stderr.decode())

        sparv_output = p.stdout.decode() if p.stdout else ""
        sparv_output = ", ".join([line for line in sparv_output.split("\n") if line])
        return sparv_output


def get_job(user, corpus_id, sparv_exports=None, save=False):
    """Get an existing job from the cache or create a new one."""
    job = Job(user, corpus_id, sparv_exports=sparv_exports)
    if utils.memcached_get(job.id) is not None:
        return load_from_str(utils.memcached_get(job.id))
    if save:
        job.save()
    return job


def load_from_str(jsonstr):
    """Load a job object from a json string."""
    job_info = json.loads(jsonstr)
    job_info["status"] = getattr(Status, job_info.get("status"))
    return Job(**job_info)
