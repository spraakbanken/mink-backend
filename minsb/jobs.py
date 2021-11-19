"""Utilities related to Sparv jobs."""

import datetime
import hashlib
import json
import re
import subprocess
from enum import IntEnum
from itertools import count
from pathlib import Path

from dateutil.parser import parse
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

    def __init__(self, user, corpus_id, status=Status.none, pid=None, started=None, completed=None, sparv_exports=None,
                 files=None):
        self.user = user
        self.corpus_id = corpus_id
        self.id = self.get_id()
        self.status = status
        self.pid = pid
        self.started = started
        self.completed = completed
        self.sparv_exports = sparv_exports or []
        self.files = files or []

        self.sparv_user = app.config.get("SPARV_USER")
        self.sparv_server = app.config.get("SPARV_SERVER")
        self.nohupfile = app.config.get("SPARV_NOHUP_FILE")
        self.runscript = app.config.get("SPARV_TMP_RUN_SCRIPT")
        self.remote_corpus_dir = str(paths.get_corpus_dir(domain="sparv", user=self.user, corpus_id=self.corpus_id))

    def __str__(self):
        return json.dumps({"user": self.user, "corpus_id": self.corpus_id, "status": self.status.name, "pid": self.pid,
                           "started": self.started, "completed": self.completed, "sparv_exports": self.sparv_exports,
                           "files": self.files})

    def save(self):
        """Write a job item to the cache and filesystem."""
        dump = str(self)
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

    def get_id(self, corpus_id=None):
        """Get hashed ID for job."""
        if corpus_id is None:
            corpus_id = self.corpus_id
        return hashlib.sha1(f"{self.user}{corpus_id}".encode("UTF-8")).hexdigest()[:10]

    def change_id(self, new_corpus_id):
        """Change the corpus ID on the Sparv server and in cache."""
        new_corpus_dir = str(paths.get_corpus_dir(domain="sparv", user=self.user, corpus_id=new_corpus_id))
        p = subprocess.run(["ssh", "-i", "~/.ssh/id_rsa", f"{self.sparv_user}@{self.sparv_server}",
                            f"cd /home/{self.sparv_user} && mv {self.remote_corpus_dir} {new_corpus_dir}"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p.stderr:
            raise Exception(f"Failed to rename corpus on Sparv server! {p.stderr.decode()}")

        self.remove()
        self.corpus_id = new_corpus_id
        self.id = self.get_id(corpus_id=new_corpus_id)
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
        self.started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        self.completed = None
        sparv_env = app.config.get("SPARV_ENVIRON")
        sparv_command = f"{app.config.get('SPARV_COMMAND')} {app.config.get('SPARV_RUN')} {' '.join(self.sparv_exports)}"
        if self.files:
            sparv_command += f" --file {' '.join(self.files)}"
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
        if self.status == Status.done_annotating:
            self.set_status(Status.aborted)
            return
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
            progress, _warnings, errors, misc = self.get_output()
            if (progress == "100%" or misc.startswith("Nothing to be done.")):
                self.set_status(Status.done_annotating)
                self.completed = self.get_nohup_timestamp()
                self.set_pid(None)
            else:
                if errors:
                    app.logger.debug(f"Error in Sparv: {errors}")
                if misc:
                    app.logger.debug(f"Sparv output: {misc}")
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
        progress = warnings = errors = misc = ""
        if stdout:
            warnings = []
            errors = []
            misc = []
            latest_msg = misc
            for line in stdout.split("\n"):
                matchobj = re.match(r"(?:\d\d:\d\d:\d\d|\s{8}) ([A-Z]+)\s+(.+)$", line)
                if matchobj:
                    msg = matchobj.group(2).strip()
                    if matchobj.group(1) == "PROGRESS":
                        progress = msg
                    elif matchobj.group(1) == "WARNING":
                        warnings.append = matchobj.group(1) + " " + msg
                        latest_msg = warnings
                    elif matchobj.group(1) == "ERROR":
                        errors.append = matchobj.group(1) + " " + msg
                        latest_msg = errors
                elif re.match(r"\s{8,}.+", line):
                    latest_msg.append(line.strip())
                else:
                    if line.strip():
                        misc.append(line.strip())
            warnings = "\n".join(warnings)
            errors = "\n".join(errors)
            misc = "\n".join(misc)

        return progress, warnings, errors, misc

    def get_nohup_timestamp(self):
        """Get the last modification time of the nohup file."""
        p = subprocess.run(["ssh", "-i", "~/.ssh/id_rsa", f"{self.sparv_user}@{self.sparv_server}",
                            (f"cd /home/{self.sparv_user}/{self.remote_corpus_dir}"
                            f" && date -r {self.nohupfile} -R")],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out = p.stdout.decode() if p.stdout else ""
        try:
            return parse(out.strip()).isoformat()
        except Exception:
            return None

    def sync_results(self, oc):
        """Sync exports from Sparv server to Nextcloud."""
        local_corpus_dir = str(paths.get_corpus_dir(user=self.user, corpus_id=self.corpus_id, mkdir=True))
        nc_corpus_dir = str(paths.get_corpus_dir(domain="nc", corpus_id=self.corpus_id))

        corpus_contents = utils.list_contents(oc, nc_corpus_dir, exclude_dirs=False)
        file_index = utils.create_file_index(corpus_contents, self.user)

        # Get exports from Sparv
        remote_export_dir = paths.get_export_dir(domain="sparv", user=self.user, corpus_id=self.corpus_id)
        p = subprocess.run(["rsync", "-av", f"{self.sparv_user}@{self.sparv_server}:~/{remote_export_dir}",
                            local_corpus_dir], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p.stderr:
            self.set_status(Status.error)
            return utils.response("Failed to retrieve Sparv exports", err=True, info=p.stderr.decode()), 404

        # Get plain text sources from Sparv
        remote_work_dir = paths.get_work_dir(domain="sparv", user=self.user, corpus_id=self.corpus_id)
        p = subprocess.run(["rsync", "-av", "--include=@text", "--include=*/", "--exclude=*", "--prune-empty-dirs",
                            f"{self.sparv_user}@{self.sparv_server}:~/{remote_work_dir}",
                            local_corpus_dir], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Transfer exports to Nextcloud
        local_export_dir = paths.get_export_dir(user=self.user, corpus_id=self.corpus_id)
        try:
            utils.upload_dir(oc, nc_corpus_dir, local_export_dir, self.corpus_id, self.user, file_index)
        except Exception as e:
            self.set_status(Status.error)
            raise Exception(f"Failed to upload exports to Nextcloud! {e}")

        # Transfer plain text sources to Nextcloud
        local_work_dir = paths.get_work_dir(user=self.user, corpus_id=self.corpus_id)
        try:
            app.logger.warning(local_work_dir)
            utils.upload_dir(oc, nc_corpus_dir, local_work_dir, self.corpus_id, self.user, file_index)
        except Exception as e:
            self.set_status(Status.error)
            app.logger.warning(e)
            raise Exception(f"Failed to upload plain text sources to Nextcloud! {e}")

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
        """Remove annotation and export files from Sparv server by running 'sparv clean --all'."""
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

    def clean_export(self):
        """Remove export files from Sparv server by running 'sparv clean --export'."""
        sparv_command = app.config.get("SPARV_COMMAND") + " clean --export"
        p = subprocess.run([
            "ssh", "-i", "~/.ssh/id_rsa", f"{self.sparv_user}@{self.sparv_server}",
            f"cd /home/{self.sparv_user}/{self.remote_corpus_dir} && "
            f"{sparv_command}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p.stderr:
            raise Exception(p.stderr.decode())

        sparv_output = p.stdout.decode() if p.stdout else ""
        sparv_output = ", ".join([line for line in sparv_output.split("\n") if line])
        return sparv_output


def get_job(user, corpus_id, sparv_exports=None, files=None):
    """Get an existing job from the cache or create a new one."""
    job = Job(user, corpus_id, sparv_exports=sparv_exports, files=files)
    if utils.memcached_get(job.id) is not None:
        return load_from_str(utils.memcached_get(job.id), sparv_exports=sparv_exports, files=files)
    return job


def load_from_str(jsonstr, sparv_exports=None, files=None):
    """Load a job object from a json string."""
    job_info = json.loads(jsonstr)
    job_info["status"] = getattr(Status, job_info.get("status"))
    if sparv_exports is not None:
        job_info["sparv_exports"] = sparv_exports
    if files is not None:
        job_info["files"] = files
    return Job(**job_info)


class DefaultJob():
    """A default job item for running generic Sparv commands like `sparv run -l`.

    A default job is not part of the job queue
    """

    def __init__(self, language="swe"):
        self.lang = language

        self.sparv_user = app.config.get("SPARV_USER")
        self.sparv_server = app.config.get("SPARV_SERVER")
        self.remote_corpus_dir = str(paths.get_corpus_dir(domain="sparv-default", corpus_id=self.lang))
        self.config_file = app.config.get("SPARV_CORPUS_CONFIG")

    def list_languages(self):
        """List the languages available in Sparv."""
        # Create and corpus dir with config file on Sparv server
        p = subprocess.run(["ssh", "-i", "~/.ssh/id_rsa", f"{self.sparv_user}@{self.sparv_server}",
                            f"cd /home/{self.sparv_user} && mkdir -p {self.remote_corpus_dir} && "
                            f"echo 'metadata:\n  language: {self.lang}'>{self.remote_corpus_dir}/{self.config_file}"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p.stderr:
            raise Exception(f"Failed to create corpus dir on Sparv server! {p.stderr.decode()}")

        sparv_env = app.config.get("SPARV_ENVIRON")
        sparv_command = f"{app.config.get('SPARV_COMMAND')} languages"
        p = subprocess.run(["ssh", "-i", "~/.ssh/id_rsa", f"{self.sparv_user}@{self.sparv_server}",
                            f"cd /home/{self.sparv_user}/{self.remote_corpus_dir} && {sparv_env} {sparv_command}"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if p.returncode != 0:
            stderr = p.stderr.decode() if p.stderr else ""
            raise exceptions.JobError(f"Failed to run Sparv! {stderr}")

        languages = []
        stdout = p.stdout.decode() if p.stdout else ""
        lines = [line.strip() for line in stdout.split("\n") if line.strip()][1:]
        for line in lines:
            matchobj = re.match(r"(.+?)\s+(\S+)$", line)
            if matchobj:
                languages.append({"name": matchobj.group(1), "code": matchobj.group(2)})
        return languages

    def list_exports(self):
        """List the available exports for the current language."""
        # Create and corpus dir with config file on Sparv server
        p = subprocess.run(["ssh", "-i", "~/.ssh/id_rsa", f"{self.sparv_user}@{self.sparv_server}",
                            f"cd /home/{self.sparv_user} && mkdir -p {self.remote_corpus_dir} && "
                            f"echo 'metadata:\n  language: {self.lang}'>{self.remote_corpus_dir}/{self.config_file}"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p.stderr:
            raise Exception(f"Failed to create corpus dir on Sparv server! {p.stderr.decode()}")

        sparv_env = app.config.get("SPARV_ENVIRON")
        sparv_command = f"{app.config.get('SPARV_COMMAND')} run -l"
        p = subprocess.run(["ssh", "-i", "~/.ssh/id_rsa", f"{self.sparv_user}@{self.sparv_server}",
                            f"cd /home/{self.sparv_user}/{self.remote_corpus_dir} && {sparv_env} {sparv_command}"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if p.returncode != 0:
            stderr = p.stderr.decode() if p.stderr else ""
            raise exceptions.JobError(f"Failed to run Sparv! {stderr}")

        exports = []
        stdout = p.stdout.decode() if p.stdout else ""
        lines = [line for line in stdout.split("\n") if line.strip()][1:-1]
        for line in lines:
            if line.startswith("    "):
                exports[-1]["description"] += " " + line.strip()
            else:
                matchobj = re.match(r"(\S+)\s+(.+)$", line.strip())
                if matchobj:
                    exports.append({"export": matchobj.group(1), "description": matchobj.group(2)})
        return exports
