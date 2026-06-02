"""Karp job implementations."""

import shlex

from mink.core import exceptions, registry, utils
from mink.core.jobs import BaseJob
from mink.core.logging import logger
from mink.core.resource_specs import get_spec
from mink.core.status import Status
from mink.karp import cache
from mink.karp.config import karp_settings
from mink.karp.spec import LEXICON, ProcessName
from mink.karp.storage import storage

PROGRESS_DONE = 100


class KarpJob(BaseJob):
    """A job item holding information about a Karp job."""

    def __init__(
        self,
        id: str,  # noqa: A002
        processes: list[str] | None = None,
        status: dict | None = None,
        current_process: str | None = None,
        pid: int | None = None,
        installed_karps: bool = False,
        priority: int | str = "",
        warnings: str = "",
        errors: str = "",
        output: str = "",
        progress: str = "",
        queued: str = "",
        started: str = "",
        ended: str = "",
        duration: int = 0,
        **_obsolete: dict[str, object],  # catch invalid arguments from outdated job items (avoids crashes)
    ) -> None:
        """Initialize job by setting class variables.

        Args:
            id: Job ID.
            processes: List of process names to include in the status.
            status: Job status dictionary.
            current_process: Current process (e.g. 'karp-pipeline', 'karps').
            pid: Process ID in the Karp server.
            installed_karps: Whether resource is installed in KarpS.
            priority: Number in queue.
            warnings: Latest Karp warnings.
            errors: Latest Karp errors.
            output: Latest Karp misc output.
            progress: Progress percentage as a string (e.g. '45%').
            queued: Timestamp of when the current job was queued.
            started: Timestamp of when the current process started.
            ended: Timestamp of when the current process ended.
            duration: The time elapsed for the current process (in seconds), until ended or until now.
            **_obsolete: Catch invalid arguments from outdated job items.
        """
        if not karp_settings.KARP_ENABLED:
            raise exceptions.ConfigurationError("Karp is not enabled in the configuration")

        # Set processes based on resource spec (used for the JobStatuses mapping and status checks in BaseJob)
        if processes is None:
            processes = list(get_spec(LEXICON).process_names)

        super().__init__(
            id=id,
            processes=processes,
            status=status,
            current_process=current_process,
            pid=pid,
            priority=priority,
            warnings=warnings,
            errors=errors,
            progress=progress,
            queued=queued,
            started=started,
            ended=ended,
            duration=duration,
        )
        self.installed_karps = installed_karps
        self.output = output

        self.karp_user = karp_settings.KARP_USER
        self.karp_server = karp_settings.KARP_HOST
        self.remote_resource_dir = storage.get_resource_dir(self.id)
        self.remote_resource_dir_esc = shlex.quote(str(self.remote_resource_dir))
        self.nohupfile = shlex.quote(str(self.remote_resource_dir / karp_settings.KARP_NOHUP_FILE))
        self.runscript = shlex.quote(str(self.remote_resource_dir / karp_settings.KARP_TMP_RUN_SCRIPT))

    def __str__(self) -> str:
        """Return a string representation of the job instance."""
        return f"Job(status={self.status}, current_process={self.current_process}, progress={self.progress}%)"

    def serialize(self, depth: int | None = None) -> dict:
        """Return a serialized dict representation of the job instance."""
        raw = {
            "status": self.status,
            "current_process": self.current_process,
            "pid": self.pid,
            "installed_karps": self.installed_karps,
            "priority": self.priority,
            "warnings": self.warnings,
            "errors": self.errors,
            "output": self.output,
            "queued": self.queued,
            "started": self.started,
            "ended": self.ended,
            "duration": self.duration,
            "progress": self.progress,
        }
        return utils.serialize_obj(raw, depth=depth)

    def update_job_info(self) -> None:
        """Update job info: queue priority, Karp Pipeline output and process time taken."""
        self.priority = registry.get_priority(self) if registry.get_priority(self) != -1 else ""
        self.warnings, self.errors, self.output, karp_ended = self.get_output()
        self.ended, self.duration = self.calculate_ended_timeinfo(karp_ended)
        self.parent.update()

    def calculate_ended_timeinfo(self, karp_ended: str) -> tuple[str, int]:
        """Calculate value for 'duration' and timestamp for 'ended'.

        Calculate the time it took to process the resource until it ended or until now. When a Karp job has ended (with
        success or error) it reads the time Karp took (from the nohup file) and compensates for extra time the backend
        may have taken (e.g. because it was waiting for queue advance or file syncing).
        """
        ended = ""
        duration = self.duration or 0

        # self.ended is set and job was aborted or no Karp output is available for other reasons, calculate 'duration'
        if self.ended and (self.status.is_aborted(self.current_process) or not karp_ended):
            ended = self.ended
            time_elapsed = self.get_timedelta(ended)
            duration = max(self.duration, time_elapsed)
        # Job has not started, is waiting or has been aborted
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
        # Job has ended (done or error), read time taken from Karp output or 'duration' if it is larger.
        elif karp_ended or self.status.is_error(self.current_process):
            time_elapsed = self.get_timedelta(karp_ended)
            duration = max(self.duration, time_elapsed)
            ended = self.get_ended_timestamp(duration)
        # This should never happen!
        else:
            logger.error(
                "Something went wrong while calculating time taken for resource '%s'. "
                "Process: %s; Status: %s; Started: %s; Karp ended: %s; self.ended: %s",
                self.id,
                self.current_process,
                self.status[self.current_process],
                self.started,
                karp_ended,
                self.ended,
            )

        return ended, duration

    def check_requirements(self) -> None:
        """Check if required resource contents (config file and one input file) are present.

        Raises:
            exceptions.PrerequisiteError: If no config file or input files are provided.
        """
        exclude = [karp_settings.KARP_OUTPUT_DIR]
        resource_contents = storage.list_contents(
            storage.get_resource_dir(self.id), exclude_dirs=False, blacklist=exclude
        )
        if karp_settings.KARP_CONFIG not in [i.get("name") for i in resource_contents]:
            self.set_status(Status.error)
            raise exceptions.PrerequisiteError(f"No config file provided for '{self.id}'")
        if not [i for i in resource_contents if i.get("path").startswith(karp_settings.KARP_SOURCE_DIR)]:
            self.set_status(Status.error)
            raise exceptions.PrerequisiteError(f"No input file provided for '{self.id}'")

    def run_karp_pipeline(self) -> None:
        """Run the Karp Pipeline.

        Raises:
            exceptions.JobError: If running Karp Pipeline fails.
        """
        # Run Karp Pipeline and capture the exit code and the time it took to run
        script_content = (
            f'nohup bash -c "time -p {karp_settings.KARP_COMMAND} {karp_settings.KARP_RUN}; rc=\\$?; '
            f'printf \'{{\\"exit_code\\":\\"%s\\"}}\\n\' \\"\\$rc\\"" >{self.nohupfile} 2>&1 &\necho $!'
        )

        self.started = utils.get_current_time()
        p = storage.ssh_run(
            f"cd {self.remote_resource_dir_esc} && "
            f"echo {shlex.quote(script_content)} > {self.runscript} && chmod +x {self.runscript} && {self.runscript}"
        )

        if p.returncode != 0:
            stderr = p.stderr.decode() if p.stderr else ""
            self.reset_time()
            self.set_status(Status.error, ProcessName.karp_pipeline)
            raise exceptions.JobError(f"Failed to run Karp Pipeline: {stderr}")

        # Get pid from process and store job info
        try:
            float(p.stdout.decode())
            self.set_attribute("pid", int(p.stdout.decode()))
        except ValueError:
            pass
        self.set_status(Status.running, ProcessName.karp_pipeline)

    def install_karps(self) -> None:
        """Install a lexicon in KarpS.

        Raises:
            exceptions.JobError: If installing lexicon in KarpS fails.
        """
        script_content = (
            f'nohup bash -c "time -p {karp_settings.KARP_COMMAND} {karp_settings.KARP_INSTALL}; rc=\\$?; '
            f'printf \'{{\\"exit_code\\":\\"%s\\"}}\\n\' \\"\\$rc\\"" >{self.nohupfile} 2>&1 &\necho $!'
        )

        self.started = utils.get_current_time()
        p = storage.ssh_run(
            f"cd {self.remote_resource_dir_esc} && "
            f"echo {shlex.quote(script_content)} > {self.runscript} && chmod +x {self.runscript} && {self.runscript}"
        )

        if p.returncode != 0:
            stderr = p.stderr.decode() if p.stderr else ""
            self.reset_time()
            self.set_status(Status.error, ProcessName.karps)
            raise exceptions.JobError(f"Failed to install resource in KarpS: {stderr}")

        # Get pid from process and store job info
        try:
            float(p.stdout.decode())
            self.set_attribute("pid", int(p.stdout.decode()))
        except ValueError:
            pass
        self.set_status(Status.running, ProcessName.karps)
        # Set 'installed_karps' flag to True when setting job status to 'done' (in process_running)

    def uninstall_karps(self) -> tuple[str, str]:
        """Uninstall resource from KarpS.

        Raises:
            exceptions.JobError: If uninstalling resource from KarpS fails.
        """
        try:
            self.abort()
        except (exceptions.ProcessNotRunningError, exceptions.ProcessNotFoundError):
            pass
        except Exception:
            raise

        p = storage.ssh_run(
            f"cd {self.remote_resource_dir_esc} && {karp_settings.KARP_COMMAND} {karp_settings.KARP_UNINSTALL}"
        )

        if p.returncode != 0:
            stderr = p.stderr.decode() if p.stderr else ""
            logger.error("Failed to uninstall resource %s from KarpS: %s", self.id, stderr)
            raise exceptions.JobError(f"Failed to uninstall resource from KarpS: {stderr}")

        self.set_attribute("installed_karps", False)

        # Get output from uninstall command
        parsed_output = self.parse_jsonl_output(p.stdout.decode() if p.stdout else "")
        warnings = "\n".join(parsed_output["warnings"])
        output = "\n".join(parsed_output["misc"])

        return warnings, output

    def abort(self) -> None:
        """Abort running Karp Pipeline.

        Raises:
            exceptions.ProcessNotRunningError: If Karp Pipeline is not running.
            exceptions.JobError: If aborting job fails.
        """
        if self.status.is_waiting(self.current_process):
            registry.pop_from_queue(self)
            self.set_status(Status.aborted)
            return
        if not self.status.is_running():
            raise exceptions.ProcessNotRunningError("Failed to abort job because Karp Pipeline was not running")
        if not self.pid:
            logger.debug("Resetting time during abort due to missing PID (resource %s)", self.id)
            self.reset_time(reset_started=False)
            self.set_status(Status.aborted)
            return

        p = storage.ssh_run(f"kill -SIGTERM {self.pid}")
        if p.returncode == 0:
            self.pid = None
            self.set_status(Status.aborted)
            self.ended = utils.get_current_time()
            self.update_job_info()
        else:
            stderr = p.stderr.decode()
            # Ignore 'no such process' error
            if stderr.endswith(("Processen finns inte\n", "No such process\n")):
                self.pid = None
                logger.debug("Resetting time during abort due to process not running (resource %s)", self.id)
                self.reset_time(reset_started=False)
                self.set_status(Status.aborted)
            else:
                raise exceptions.JobError(f"Failed to abort job: {stderr}")

    def process_running(self) -> bool:
        """Check if process with this job's pid is still running on Karp server.

        Returns:
            True if process is running, False otherwise.
        """
        if self.pid:
            p = storage.ssh_run(f"kill -0 {self.pid}")
            # Process is running, do nothing
            if p.returncode == 0:
                return True
            # Process not running anymore
            logger.debug(
                "Failed to kill process (resource %s). stderr : '%s'",
                self.id,
                p.stderr.decode().strip() if p.stderr else "",
            )
            self.set_attribute("pid", None)

        _warnings, errors, misc, _karp_ended = self.get_output()
        if self.current_process == ProcessName.karp_pipeline:
            cache.remove_lexicon_output_contents(self.id)
        if self.progress_output == PROGRESS_DONE:
            if self.status.is_running(self.current_process):
                # Set 'installed_karps' to True if current process is 'karps'
                if self.current_process == ProcessName.karps:
                    self.installed_karps = True
                self.set_status(Status.done)
        else:
            if errors:
                logger.debug("Error in Karp Pipeline (resource %s): %s", self.id, errors)
            if misc:
                logger.debug("Karp Pipeline output (resource %s): %s", self.id, misc)
            logger.debug("Karp Pipeline process was not completed successfully (resource %s).", self.id)
            self.set_status(Status.error)
        return False

    def get_output(self) -> tuple[str, str, str, str]:
        """Check latest Karp Pipeline output of this job by reading the nohup file.

        Returns:
            Tuple of warnings, errors, and miscellaneous output.
        """
        warnings = errors = misc = karp_ended = ""
        progress = 0

        p = storage.ssh_run(f"cat {self.nohupfile}")
        stdout = p.stdout.decode().strip() if p.stdout else ""
        if stdout:
            parsed_output = self.parse_jsonl_output(stdout)
            warnings = "\n".join(parsed_output["warnings"])
            errors = "\n".join(parsed_output["errors"])
            misc = "\n".join(parsed_output["misc"])

            real_seconds = parsed_output.get("real_seconds")
            if real_seconds is not None:
                karp_ended = self.get_ended_timestamp(real_seconds)

            exit_code = parsed_output.get("exit_code")
            if exit_code is not None:
                if exit_code == "0":
                    progress = PROGRESS_DONE
                else:
                    if errors:
                        errors += "\n"
                    errors += f"Karp Pipeline exited with code {exit_code}"

            self.progress_output = progress

        return warnings, errors, misc, karp_ended

    @property
    def progress(self) -> str | None:
        """Get the Karp Pipeline progress but don't report 100% before the job status has been changed to done.

        Returns:
            Progress percentage as a string.
        """
        if self.status.has_process_output(self.current_process, get_spec(LEXICON).no_output_processes):
            if self.progress_output == PROGRESS_DONE and not self.status.is_done(self.current_process):
                return "99%"
            return f"{self.progress_output}%"
        if self.status.is_active(self.current_process):
            return "0%"
        return ""

    def remove_from_karp(self) -> None:
        """Remove resource dir from the Karp server and abort running job if necessary."""
        try:
            self.abort()
        except (exceptions.ProcessNotRunningError, exceptions.ProcessNotFoundError):
            pass
        except Exception:
            raise

        p = storage.ssh_run(f"rm -rf {self.remote_resource_dir_esc}")
        if p.stderr:
            logger.error("Failed to remove resource dir '%s'", self.remote_resource_dir)

    def clean(self) -> str:
        """Remove output files from Karp server by running 'karp-pipeline clean'.

        Returns:
            Karp Pipeline output.
        """
        p = storage.ssh_run(
            f"cd {self.remote_resource_dir_esc} && "
            f"rm -f {self.nohupfile} {self.runscript} && {karp_settings.KARP_COMMAND} clean"
        )

        if p.stderr:
            raise exceptions.WriteError(
                self.remote_resource_dir_esc, f"Failed to clean resource dir: {p.stderr.decode()}"
            )

        karp_output = p.stdout.decode() if p.stdout else ""
        cache.set_lexicon_output_contents(self.id, [])
        return ", ".join([line for line in karp_output.split("\n") if line])
