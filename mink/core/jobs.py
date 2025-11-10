"""Utilities related to Sparv jobs."""

import datetime
import json
import re
import shlex
import subprocess
from typing import TYPE_CHECKING, Any

import dateutil
from fastapi import status

from mink.core import exceptions, registry, utils
from mink.core.config import settings
from mink.core.logging import logger
from mink.core.status import JobStatuses, ProcessName, Status
from mink.sparv import storage
from mink.sparv import utils as sparv_utils

if TYPE_CHECKING:
    from mink.core.info import Info


PROGRESS_DONE = 100


class Job:
    """A job item holding information about a Sparv job."""

    def __init__(
        self,
        id: str,  # noqa: A002
        status: dict | None = None,
        current_process: str | None = None,
        pid: int | None = None,
        sparv_exports: list | None = None,
        current_files: list | None = None,
        install_scrambled: bool = False,
        installed_korp: bool = False,
        installed_strix: bool = False,
        priority: int | str = "",
        warnings: str = "",
        errors: str = "",
        sparv_output: str = "",
        progress: str = "",
        started: str = "",
        ended: str = "",
        duration: int = 0,
        **_obsolete,  # needed to catch invalid arguments from outdated job items (avoids crashes)  # noqa: ANN003
    ) -> None:
        """Initialize job by setting class variables.

        Args:
            id: Job ID.
            status: Job status dictionary.
            current_process: Current process (e.g. 'sparv', 'korp', 'strix').
            pid: Process ID in the Sparv server.
            sparv_exports: List of Sparv exports to create (e.g. ['xml_export:pretty']).
            current_files: List of current source files to process (all files if left empty).
            install_scrambled: Whether to install the corpus scrambled in Korp.
            installed_korp: Whether corpus is installed in Korp.
            installed_strix: Whether corpus is installed in Strix.
            priority: Number in queue.
            warnings: Latest Sparv warnings.
            errors: Latest Sparv errors.
            sparv_output: Latest Sparv misc output.
            progress: Progress percentage as a string (e.g. '45%').
            started: Timestamp of when the current Sparv process started.
            ended: Timestamp of when the current Sparv process ended.
            duration: The time elapsed for the current Sparv process (in seconds), until ended or until now.
            **_obsolete: Catch invalid arguments from outdated job items.
        """
        self.id = id
        self.status = JobStatuses(status)
        self.current_process = current_process
        self.pid = pid
        self.sparv_exports = sparv_exports or []
        self.current_files = current_files or []
        self.install_scrambled = install_scrambled
        self.installed_korp = installed_korp
        self.installed_strix = installed_strix
        self.priority = priority
        self.warnings = warnings
        self.errors = errors
        self.sparv_output = sparv_output
        self.progress_output = int(progress.strip("%")) if progress else 0
        self.started = started
        self.ended = ended
        self.duration = duration

        self.sparv_user = settings.SPARV_USER
        self.sparv_server = settings.SPARV_HOST
        self.remote_corpus_dir = sparv_utils.get_corpus_dir(self.id)
        self.remote_corpus_dir_esc = shlex.quote(str(self.remote_corpus_dir))
        self.nohupfile = shlex.quote(str(self.remote_corpus_dir / settings.SPARV_NOHUP_FILE))
        self.runscript = shlex.quote(str(self.remote_corpus_dir / settings.SPARV_TMP_RUN_SCRIPT))

    def __str__(self) -> str:
        """Return a string representation of the serialized object."""
        return str(self.serialize())

    def serialize(self) -> dict:
        """Convert class data into dict.

        Returns:
            Dictionary representation of the job.
        """
        return {
            "status": self.status,
            "current_process": self.current_process,
            "pid": self.pid,
            "sparv_exports": self.sparv_exports,
            "current_files": self.current_files,
            "install_scrambled": self.install_scrambled,
            "installed_korp": self.installed_korp,
            "installed_strix": self.installed_strix,
            "priority": self.priority,
            "warnings": self.warnings,
            "errors": self.errors,
            "sparv_output": self.sparv_output,
            "started": self.started,
            "ended": self.ended,
            "duration": self.duration,
            "progress": self.progress,
        }

    def update_job_info(self) -> None:
        """Update job info: queue priority, Sparv output and process time taken."""
        self.priority = registry.get_priority(self) if registry.get_priority(self) != -1 else ""
        self.warnings, self.errors, self.sparv_output, sparv_ended = self.get_output()
        self.ended, self.duration = self.calculate_ended_timeinfo(sparv_ended)
        self.parent.update()

    def calculate_ended_timeinfo(self, sparv_ended: str) -> tuple[str, int]:
        """Calculate value for 'duration' and timestamp for 'ended'.

        Calculate the time it took to process the corpus until it ended or until now. When a Sparv job has ended (with
        success or error) it reads the time Sparv took (from the nohup file) and compensates for extra time the backend
        may have taken (e.g. because it was waiting for advance-queue or file syncing).
        """
        ended = ""
        duration = self.duration or 0

        # Job was aborted successfully ('self.ended' has been set during abort), calculate 'duration'
        if self.status.is_aborted(self.current_process) and self.ended:
            ended = self.ended
            time_elapsed = self.get_timedelta(ended)
            duration = max(self.duration, time_elapsed)
        # Job has not started, is waiting or has been aborted with some error
        elif (
            not self.started
            or self.status.is_none(self.current_process)
            or self.status.is_waiting(self.current_process)
            or self.status.is_aborted(self.current_process)
        ):
            duration = 0
        # Job is running, just calculate time elapsed since it started (don't set 'ended')
        elif self.status.is_running(self.current_process):
            duration = self.get_timedelta()
        # Job has ended (done or error), read time taken from Sparv output or 'duration' if it is larger.
        elif sparv_ended or self.status.is_error(self.current_process):
            time_elapsed = self.get_timedelta(sparv_ended)
            duration = max(self.duration, time_elapsed)
            ended = self.get_ended_timestamp(duration)
        # This should never happen!
        else:
            logger.error(
                "Something went wrong while calculating time taken. Job status: %s; "
                "Current process: %s; Job started: %s; Job ended: %s",
                self.status,
                self.current_process,
                self.started,
                sparv_ended,
            )

        return ended, duration

    def set_parent(self, parent: "Info") -> None:
        """Save reference to parent class.

        Args:
            parent: Parent class instance.
        """
        self.parent = parent

    def set_attribute(self, attribute: str, value: Any) -> None:
        """Set attribute to new value and save if changed.

        Args:
            attribute: Attribute.
            value: New value for the attribute.
        """
        # Check if value has changed before updating
        if getattr(self, attribute) != value:
            setattr(self, attribute, value)
            self.parent.update()

    def set_status(self, status: Status, process: ProcessName | None = None) -> None:
        """Change the status of a job.

        Args:
            status: New status.
            process: Process name.
        """
        process_name = self.current_process if process is None else process.name
        if self.status[process_name] != status:
            self.status[process_name] = status
            if self.status.is_active():
                self.current_process = process_name
            self.parent.update()

    def get_timedelta(self, end_time: str | None = None) -> int:
        """Get the time elapsed in seconds since 'self.started' until 'end_time' (ISO 8601) or now."""
        if end_time is None:
            end_time = utils.get_current_time()
        return int((dateutil.parser.isoparse(end_time) - dateutil.parser.isoparse(self.started)).total_seconds())

    def get_ended_timestamp(self, duration: float | int) -> str:
        """Get the timestamp (ISO 8601) for when the job ended based on 'self.started' and 'duration' (in seconds)."""
        return (dateutil.parser.isoparse(self.started) + datetime.timedelta(seconds=duration)).isoformat(
            timespec="seconds"
        )

    def reset_time(self, reset_started: bool = True) -> None:
        """Reset the processing time for a job (e.g. when queuing a new one)."""
        if reset_started:
            self.started = ""
        self.ended = ""
        self.duration = 0
        self.parent.update()

    def check_requirements(self) -> None:
        """Check if required corpus contents (config file and at least one input file) are present.

        Raises:
            exceptions.PrerequisiteError: If no config file or input files are provided.
        """
        exclude = [settings.SPARV_EXPORT_DIR, settings.SPARV_WORK_DIR, settings.SPARV_LOG_DIR]
        corpus_contents = storage.list_contents(storage.get_corpus_dir(self.id), exclude_dirs=False, blacklist=exclude)
        if settings.SPARV_CORPUS_CONFIG not in [i.get("name") for i in corpus_contents]:
            self.set_status(Status.error)
            raise exceptions.PrerequisiteError(f"No config file provided for '{self.id}'")
        if not [i for i in corpus_contents if i.get("path").startswith(settings.SPARV_SOURCE_DIR)]:
            self.set_status(Status.error)
            raise exceptions.PrerequisiteError(f"No input files provided for '{self.id}'")

    def sync_to_sparv(self) -> None:
        """Sync corpus files from storage server to the Sparv server.

        Raises:
            exceptions.WriteError: If writing to the Sparv server fails.
            exceptions.ReadError: If downloading from storage server or uploading to Sparv server fails.
        """
        self.set_status(Status.running, ProcessName.sync2sparv)

        # Create user and corpus dir on Sparv server
        p = utils.ssh_run(f"mkdir -p {self.remote_corpus_dir_esc} && rm -f {self.nohupfile} {self.runscript}")
        if p.stderr:
            self.set_status(Status.error)
            raise exceptions.WriteError(self.remote_corpus_dir_esc, f"Failed to create corpus dir: {p.stderr.decode()}")

        # Download from storage server to local tmp dir
        # TODO: do this async?
        try:
            local_user_dir = utils.get_resources_dir(mkdir=True)
            storage.download_dir(storage.get_corpus_dir(self.id), local_user_dir, self.id)
        except Exception as e:
            self.set_status(Status.error)
            raise exceptions.ReadError(self.id, "Failed to download corpus") from e

        # Sync corpus config to Sparv server
        p = subprocess.run(
            [
                "rsync",
                "-av",
                utils.get_config_file(self.id),
                f"{self.sparv_user}@{self.sparv_server}:~/{self.remote_corpus_dir}/",
            ],
            capture_output=True,
            check=False,
        )
        if p.stderr:
            self.set_status(Status.error)
            config_path = self.remote_corpus_dir / settings.SPARV_CORPUS_CONFIG
            raise exceptions.WriteError(config_path, f"Failed to copy file to Sparv server: {p.stderr.decode()}")

        # Sync corpus files to Sparv server
        # TODO: do this async
        local_source_dir = utils.get_source_dir(self.id)
        p = subprocess.run(
            [
                "rsync",
                "-av",
                "--delete",
                local_source_dir,
                f"{self.sparv_user}@{self.sparv_server}:~/{self.remote_corpus_dir}/",
            ],
            capture_output=True,
            check=False,
        )
        if p.stderr:
            self.set_status(Status.error)
            raise exceptions.WriteError(self.id, f"Failed to copy corpus files to Sparv server: {p.stderr.decode()}")

        self.set_status(Status.done)

    def unlock_snakemake(self) -> None:
        """Unlock a possibly locked corpus dir from Snakemake (e.g. after killing a Sparv process)."""
        p = utils.ssh_run(f"{settings.SPARV_ENVIRON} {settings.SPARV_COMMAND} --dir {self.remote_corpus_dir_esc} "
                          f"{settings.SPARV_RUN} --unlock")

        if p.returncode != 0:
            stderr = p.stderr.decode() if p.stderr else ""
            logger.error("Failed to unlock Snakemake for corpus %s: %s", self.id, stderr)
            raise exceptions.JobError(f"Failed to unlock Snakemake: {stderr}")

    def run_sparv(self) -> None:
        """Start a Sparv annotation process.

        Raises:
            exceptions.JobError: If running Sparv fails.
        """
        sparv_command = (
            f"{settings.SPARV_COMMAND} --dir {self.remote_corpus_dir_esc} {settings.SPARV_RUN} "
            f"{' '.join(self.sparv_exports)}"
        )
        if self.current_files:
            sparv_command += f" --file {' '.join(shlex.quote(f) for f in self.current_files)}"

        script_content = (f"{settings.SPARV_ENVIRON} nohup time -p {sparv_command} >{self.nohupfile} "
                          "2>&1 &\necho $!")

        self.started = utils.get_current_time()
        p = utils.ssh_run(
            f"echo {shlex.quote(script_content)} > {self.runscript} && chmod +x {self.runscript} && {self.runscript}"
        )

        if p.returncode != 0:
            stderr = p.stderr.decode() if p.stderr else ""
            self.reset_time()
            self.set_status(Status.error, ProcessName.sparv)
            raise exceptions.JobError(f"Failed to run Sparv: {stderr}")

        # Get pid from Sparv process and store job info
        try:
            float(p.stdout.decode())
            self.set_attribute("pid", int(p.stdout.decode()))
        except ValueError:
            pass
        self.set_status(Status.running, ProcessName.sparv)

    def install_korp(self) -> None:
        """Install a corpus in Korp.

        Raises:
            exceptions.JobError: If installing corpus in Korp fails.
        """
        # Remove install markers
        sparv_work_dir = shlex.quote(str(sparv_utils.get_work_dir(self.id)))
        p = utils.ssh_run(f"rm -rf {sparv_work_dir}/korp.install_*_marker")
        if p.returncode != 0:
            logger.error("Failed to remove Korp install markers for corpus %s: %s", self.id, p.stderr.decode())

        sparv_installs = settings.SPARV_DEFAULT_KORP_INSTALLS
        if self.install_scrambled:
            sparv_installs.append("cwb:install_corpus_scrambled")
        else:
            sparv_installs.extend(["cwb:install_corpus"])

        sparv_command = shlex.quote(
            f"{settings.SPARV_COMMAND} --dir {self.remote_corpus_dir_esc} "
            f"{settings.SPARV_INSTALL} {' '.join(sparv_installs)}"
        )
        script_content = shlex.quote(
            f"{settings.SPARV_ENVIRON} nohup time -p sh -c {sparv_command} >{self.nohupfile} "
            "2>&1 &\necho $!"
        )
        self.started = utils.get_current_time()
        p = utils.ssh_run(f"echo {script_content} > {self.runscript} && chmod +x {self.runscript} && {self.runscript}")

        if p.returncode != 0:
            stderr = p.stderr.decode() if p.stderr else ""
            self.reset_time()
            self.set_status(Status.error, ProcessName.korp)
            raise exceptions.JobError(f"Failed to install corpus in Korp: {stderr}")

        self.installed_korp = True
        # Get pid from Sparv process and store job info
        try:
            float(p.stdout.decode())
            self.set_attribute("pid", int(p.stdout.decode()))
        except ValueError:
            pass
        self.set_status(Status.running, ProcessName.korp)

    def uninstall_korp(self) -> None:
        """Uninstall corpus from Korp.

        Raises:
            exceptions.JobError: If uninstalling corpus from Korp fails.
        """
        try:
            self.abort_sparv()
        except (exceptions.ProcessNotRunningError, exceptions.ProcessNotFoundError):
            pass
        except Exception:
            raise

        p = utils.ssh_run(
            f"{settings.SPARV_ENVIRON} {settings.SPARV_COMMAND} --dir {self.remote_corpus_dir_esc} "
            f"{settings.SPARV_UNINSTALL} {' '.join(settings.SPARV_DEFAULT_KORP_UNINSTALLS)}"
        )

        if p.returncode != 0:
            stderr = p.stderr.decode() if p.stderr else ""
            logger.error("Failed to uninstall corpus %s from Korp: %s", self.id, stderr)
            raise exceptions.JobError(f"Failed to uninstall corpus from Korp: {stderr}")

        self.set_attribute("installed_korp", False)

    def install_strix(self) -> None:
        """Install a corpus in Strix.

        Raises:
            exceptions.JobError: If installing corpus in Strix fails.
        """
        # Remove install markers
        sparv_work_dir = shlex.quote(str(sparv_utils.get_work_dir(self.id)))
        p = utils.ssh_run(f"rm -rf {sparv_work_dir}/sbx_strix.install_*_marker")
        if p.returncode != 0:
            logger.error("Failed to remove Strix install markers for corpus %s: %s", self.id, p.stderr.decode())

        sparv_installs = settings.SPARV_DEFAULT_STRIX_INSTALLS
        sparv_command = shlex.quote(
            f"{settings.SPARV_COMMAND} --dir {self.remote_corpus_dir_esc} "
            f"{settings.SPARV_INSTALL} {' '.join(sparv_installs)}"
        )
        script_content = shlex.quote(
            f"{settings.SPARV_ENVIRON} nohup time -p sh -c {sparv_command} >{self.nohupfile} "
            "2>&1 &\necho $!"
        )
        self.started = utils.get_current_time()
        p = utils.ssh_run(
            f"echo {script_content} > {self.runscript} && chmod +x {self.runscript} && {self.runscript}"
        )

        if p.returncode != 0:
            stderr = p.stderr.decode() if p.stderr else ""
            self.reset_time()
            self.set_status(Status.error, ProcessName.strix)
            raise exceptions.JobError(f"Failed to install corpus in Strix: {stderr}")

        self.installed_strix = True
        # Get pid from Sparv process and store job info
        try:
            float(p.stdout.decode())
            self.set_attribute("pid", int(p.stdout.decode()))
        except ValueError:
            pass
        self.set_status(Status.running, ProcessName.strix)

    def uninstall_strix(self) -> None:
        """Uninstall corpus from Strix.

        Raises:
            exceptions.JobError: If uninstalling corpus from Strix fails.
        """
        try:
            self.abort_sparv()
        except (exceptions.ProcessNotRunningError, exceptions.ProcessNotFoundError):
            pass
        except Exception:
            raise

        p = utils.ssh_run(
            f"{settings.SPARV_ENVIRON} {settings.SPARV_COMMAND} --dir {self.remote_corpus_dir_esc} "
            f"{settings.SPARV_UNINSTALL} {' '.join(settings.SPARV_DEFAULT_STRIX_UNINSTALLS)}"
        )

        if p.returncode != 0:
            stderr = p.stderr.decode() if p.stderr else ""
            logger.error("Failed to uninstall corpus %s from Strix: %s", self.id, stderr)
            raise exceptions.JobError(f"Failed to uninstall corpus from Strix: {stderr}")

        self.set_attribute("installed_strix", False)

    def abort_sparv(self) -> None:
        """Abort running Sparv process.

        Raises:
            exceptions.ProcessNotRunningError: If Sparv is not running.
            exceptions.JobError: If aborting job fails.
        """
        if self.status.is_waiting(self.current_process):
            registry.pop_from_queue(self)
            self.set_status(Status.aborted)
            return
        if not self.status.is_running():
            raise exceptions.ProcessNotRunningError("Failed to abort job because Sparv was not running")
        if not self.pid:
            logger.debug("Resetting time from abort_sparv due to missing PID (corpus %s)", self.id)
            self.reset_time(reset_started=False)
            self.set_status(Status.aborted)
            return
            # raise exceptions.ProcessNotFound("Failed to abort job because no process ID was found")

        p = utils.ssh_run(f"kill -SIGTERM {self.pid}")
        if p.returncode == 0:
            self.pid = None
            self.set_status(Status.aborted)
            self.ended = utils.get_current_time()
            self.update_job_info()
            self.unlock_snakemake()
        else:
            stderr = p.stderr.decode()
            # Ignore 'no such process' error
            if stderr.endswith(("Processen finns inte\n", "No such process\n")):
                self.pid = None
                logger.debug("Resetting time from abort_sparv due to process not running (corpus %s)", self.id)
                self.reset_time(reset_started=False)
                self.set_status(Status.aborted)
            else:
                raise exceptions.JobError(f"Failed to abort job: {stderr}")

    def process_running(self) -> bool:
        """Check if process with this job's pid is still running on Sparv server.

        Returns:
            True if process is running, False otherwise.
        """
        if self.pid:
            p = utils.ssh_run(f"kill -0 {self.pid}")
            # Process is running, do nothing
            if p.returncode == 0:
                return True
            # Process not running anymore
            logger.debug(
                "Failed to kill process (corpus %s). stderr : '%s'",
                self.id,
                p.stderr.decode().strip() if p.stderr else "",
            )
            self.set_attribute("pid", None)

        _warnings, errors, misc, _sparv_ended = self.get_output()
        if self.progress_output == PROGRESS_DONE:
            if self.status.is_running(self.current_process):
                self.set_status(Status.done)
        else:
            if errors:
                logger.debug("Error in Sparv (corpus %s): %s", self.id, errors)
            if misc:
                logger.debug("Sparv output (corpus %s): %s", self.id, misc)
            logger.debug("Sparv process was not completed successfully (corpus %s).", self.id)
            self.set_status(Status.error)
        return False

    def get_output(self) -> tuple[str, str, str, str]:
        """Check latest Sparv output of this job by reading the nohup file.

        Returns:
            Tuple of warnings, errors, and miscellaneous output.
        """
        if not self.status.has_process_output(self.current_process):
            return "", "", "", ""

        p = utils.ssh_run(f"cat {self.nohupfile}")

        stdout = p.stdout.decode().strip() if p.stdout else ""
        warnings = errors = misc = sparv_ended = ""
        progress = 0
        if stdout:
            warnings = []
            errors = []
            misc = []
            for line in stdout.split("\n"):
                try:
                    json_output = json.loads(line)
                    msg = json_output.get("message")
                    if json_output.get("level") == "FINAL" and msg == "Nothing to be done.":
                        progress = PROGRESS_DONE
                        misc.append(msg)
                    elif json_output.get("level") == "PROGRESS":
                        progress = int(msg[:-1])
                    elif json_output.get("level") == "WARNING":
                        warnings.append("WARNING " + msg)
                    elif json_output.get("level") == "ERROR":
                        errors.append("ERROR " + msg)
                    else:
                        misc.append(msg)
                except json.JSONDecodeError:  # noqa: PERF203
                    # Catch "real" time output
                    if re.match(r"real \d.+", line):
                        real_seconds = float(line[5:].strip())
                        sparv_ended = self.get_ended_timestamp(real_seconds)
                    # Ignore "user" and "sys" time output
                    elif re.match(r"user|sys \d.+", line):
                        pass

            self.progress_output = progress

            warnings = "\n".join(warnings)
            errors = "\n".join(errors)
            misc = "\n".join(misc)

        return warnings, errors, misc, sparv_ended

    @property
    def progress(self) -> str | None:
        """Get the Sparv progress but don't report 100% before the job status has been changed to done.

        Returns:
            Progress percentage as a string.
        """
        if self.status.has_process_output(self.current_process):
            if self.progress_output == PROGRESS_DONE and not self.status.is_done(self.current_process):
                return "99%"
            return f"{self.progress_output}%"
        if self.status.is_active(self.current_process):
            return "0%"
        return ""

    def sync_results(self) -> None:
        """Sync exports from Sparv server to the storage server.

        Returns:
            None if successful, otherwise a tuple with error message and status code.

        Raises:
            exceptions.WriteError: If writing to the storage server fails.
        """
        self.set_status(Status.running, ProcessName.sync2storage)
        remote_corpus_dir = storage.get_corpus_dir(self.id)
        local_corpus_dir = str(utils.get_resource_dir(self.id, mkdir=True))

        # Get exports from Sparv
        remote_export_dir = sparv_utils.get_export_dir(self.id)
        p = subprocess.run(
            ["rsync", "-av", f"{self.sparv_user}@{self.sparv_server}:~/{remote_export_dir}", local_corpus_dir],
            capture_output=True,
            check=False,
        )
        if p.stderr:
            self.set_status(Status.error)
            raise exceptions.MinkHTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                return_code="failed_to_retrieve_sparv_exports",
                message="Failed to retrieve Sparv exports",
                info=p.stderr.decode()
            )

        # Get plain text sources from Sparv
        remote_work_dir = sparv_utils.get_work_dir(self.id)
        p = subprocess.run(
            [
                "rsync",
                "-av",
                "--include=@text",
                "--include=*/",
                "--exclude=*",
                "--prune-empty-dirs",
                f"{self.sparv_user}@{self.sparv_server}:~/{remote_work_dir}",
                local_corpus_dir,
            ],
            capture_output=True,
            check=False,
        )

        # Transfer exports to the storage server
        local_export_dir = utils.get_export_dir(self.id)
        try:
            storage.upload_dir(remote_corpus_dir, local_export_dir, self.id)
        except Exception as e:
            self.set_status(Status.error)
            raise exceptions.WriteError(remote_corpus_dir, "Failed to upload exports") from e

        # Transfer plain text sources to the storage server
        local_work_dir = utils.get_work_dir(self.id)
        try:
            storage.upload_dir(remote_corpus_dir, local_work_dir, self.id)
        except Exception as e:
            self.set_status(Status.error)
            logger.warning(e)
            raise exceptions.WriteError(remote_corpus_dir, "Failed to upload plain text sources") from e

        self.set_status(Status.done)

    def remove_from_sparv(self) -> None:
        """Remove corpus dir from the Sparv server and abort running job if necessary."""
        try:
            self.abort_sparv()
        except (exceptions.ProcessNotRunningError, exceptions.ProcessNotFoundError):
            pass
        except Exception:
            raise

        p = utils.ssh_run(f"rm -rf {self.remote_corpus_dir_esc}")
        if p.stderr:
            logger.error("Failed to remove corpus dir '%s'", self.remote_corpus_dir)

    def clean(self) -> str:
        """Remove annotation and export files from Sparv server by running 'sparv clean --all'.

        Returns:
            Sparv output.
        """
        p = utils.ssh_run(
            f"rm -f {self.nohupfile} {self.runscript} && {settings.SPARV_ENVIRON} "
            f"{settings.SPARV_COMMAND} --dir {self.remote_corpus_dir_esc} clean --all"
        )

        if p.stderr:
            raise exceptions.WriteError(self.remote_corpus_dir_esc, f"Failed to clean corpus dir: {p.stderr.decode()}")

        sparv_output = p.stdout.decode() if p.stdout else ""
        return ", ".join([line for line in sparv_output.split("\n") if line])

    def clean_export(self) -> tuple[bool, str]:
        """Remove export files from Sparv server by running 'sparv clean --export'.

        Returns:
            Tuple indicating success and Sparv output.
        """
        p = utils.ssh_run(f"{settings.SPARV_ENVIRON} {settings.SPARV_COMMAND} "
                          f"--dir {self.remote_corpus_dir_esc} clean --export")
        if p.stderr:
            raise exceptions.WriteError(self.remote_corpus_dir_esc, f"Failed to clean exports: {p.stderr.decode()}")

        sparv_output = p.stdout.decode() if p.stdout else ""
        sparv_output = ", ".join([line for line in sparv_output.split("\n") if line])
        if not ("Nothing to remove" in sparv_output or "'export' directory removed" in sparv_output):
            logger.error(
                "Failed to remove Sparv export dir for corpus '%s': %s",
                self.id,
                sparv_output,
            )
            return False, sparv_output
        return True, sparv_output


class DefaultJob:
    """A default job item for running generic Sparv commands like `sparv run -l`."""

    def __init__(self, language: str = "swe") -> None:
        """Init default job by setting class variables.

        Args:
            language: Language code.
        """
        self.lang = language

        self.sparv_user = settings.SPARV_USER
        self.sparv_server = settings.SPARV_HOST
        self.remote_corpus_dir = sparv_utils.get_corpus_dir(self.lang, default_dir=True)
        self.remote_corpus_dir_esc = shlex.quote(str(self.remote_corpus_dir))
        self.config_file = settings.SPARV_CORPUS_CONFIG

    def list_languages(self) -> list:
        """List the languages available in Sparv."""
        # Create and corpus dir with config file on Sparv server
        p = utils.ssh_run(
            f"mkdir -p {self.remote_corpus_dir_esc} && "
            f"echo 'metadata:\n  language: {self.lang}' > "
            f"{self.remote_corpus_dir_esc + '/' + shlex.quote(self.config_file)}"
        )
        if p.stderr:
            raise exceptions.ReadError(self.remote_corpus_dir, f"Failed to list languages: {p.stderr.decode()}")

        p = utils.ssh_run(f"{settings.SPARV_ENVIRON} {settings.SPARV_COMMAND} "
                          f"--dir {self.remote_corpus_dir_esc} languages")

        if p.returncode != 0:
            stderr = p.stderr.decode() if p.stderr else ""
            raise exceptions.JobError(f"Failed to run Sparv: {stderr}")

        languages = []
        stdout = p.stdout.decode() if p.stdout else ""
        lines = [line.strip() for line in stdout.split("\n") if line.strip()][1:]
        for line in lines:
            if line.startswith("Supported language varieties"):
                break
            matchobj = re.match(r"(.+?)\s+(\S+)$", line)
            if matchobj:
                languages.append({"name": matchobj.group(1), "code": matchobj.group(2)})
        return languages

    def list_exports(self) -> list:
        """List the available exports for the current language."""
        # Create corpus dir with config file on Sparv server
        p = utils.ssh_run(
            f"mkdir -p {self.remote_corpus_dir_esc} && "
            f"echo 'metadata:\n  language: {self.lang}' > "
            f"{self.remote_corpus_dir_esc + '/' + shlex.quote(self.config_file)}"
        )
        if p.stderr:
            raise exceptions.ReadError(self.remote_corpus_dir, f"Failed to list exports: {p.stderr.decode()}")

        # Run Sparv to get available exports
        p = utils.ssh_run(f"{settings.SPARV_ENVIRON} {settings.SPARV_COMMAND} --dir "
                          f"{self.remote_corpus_dir_esc} modules --exporters --json")
        if p.returncode != 0:
            stderr = p.stderr.decode() if p.stderr else ""
            raise exceptions.JobError(f"Failed to run Sparv: {stderr}")

        # Parse stdout as json and extract relevant data
        stdout = p.stdout.decode() if p.stdout else ""
        try:
            json_data = json.loads(stdout.strip())
        except json.JSONDecodeError as e:
            raise exceptions.JobError("Failed to parse Sparv output as JSON") from e
        exports = []
        for exporter, exporter_data in json_data["exporters"].items():
            # Skip exporers blacklisted exporters
            if any(re.match(pattern, exporter) for pattern in settings.SPARV_EXPORT_BLACKLIST):
                continue
            for function, function_data in exporter_data["functions"].items():
                functions_info = {}
                functions_info["export"] = f"{exporter}:{function}"
                functions_info["description"] = function_data["description"]
                export_files = [i.removeprefix("export/") for i in function_data.get("exports", [])]
                functions_info["export_files"] = export_files
                exports.append(functions_info)

        return exports
