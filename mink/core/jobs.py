"""Utilities related to Sparv jobs."""

import datetime
import json
import re
import shlex
import subprocess
from typing import TYPE_CHECKING, Optional

import dateutil
from flask import Response
from flask import current_app as app

from mink.core import exceptions, registry, utils
from mink.core.status import JobStatuses, ProcessName, Status
from mink.sparv import storage
from mink.sparv import utils as sparv_utils

if TYPE_CHECKING:
    from mink.core.info import Info


class Job:
    """A job item holding information about a Sparv job."""

    def __init__(
        self,
        id: str,  # noqa: A002
        status: Optional[str] = None,
        current_process: Optional[str] = None,
        pid: Optional[int] = None,
        started: Optional[str] = None,
        done: Optional[str] = None,
        sparv_exports: Optional[list] = None,
        current_files: Optional[list] = None,
        source_files: Optional[list] = None,
        install_scrambled: Optional[bool] = None,
        installed_korp: bool = False,
        installed_strix: bool = False,
        latest_seconds_taken: int = 0,
        **_obsolete,  # needed to catch invalid arguments from outdated job items (avoids crashes)  # noqa: ANN003
    ) -> None:
        """Initialize job by setting class variables.

        Args:
            id: Job ID.
            status: Job status.
            current_process: Current process name.
            pid: Process ID.
            started: Start time.
            done: End time.
            sparv_exports: List of Sparv exports.
            current_files: List of current files.
            source_files: List of source files.
            install_scrambled: Whether to install scrambled.
            installed_korp: Whether Korp is installed.
            installed_strix: Whether Strix is installed.
            latest_seconds_taken: Latest seconds taken.
            **_obsolete: Catch invalid arguments from outdated job items.
        """
        self.id = id
        self.status = JobStatuses(status)
        self.current_process = current_process
        self.pid = pid
        self.started = started
        self.done = done
        self.sparv_done = None
        self.sparv_exports = sparv_exports or []
        self.current_files = current_files or []
        self.source_files = source_files or []
        self.install_scrambled = install_scrambled
        self.installed_korp = installed_korp
        self.installed_strix = installed_strix
        self.latest_seconds_taken = latest_seconds_taken
        self.progress_output = 0

        self.sparv_user = app.config.get("SPARV_USER")
        self.sparv_server = app.config.get("SPARV_HOST")
        self.remote_corpus_dir = sparv_utils.get_corpus_dir(self.id)
        self.remote_corpus_dir_esc = shlex.quote(str(self.remote_corpus_dir))
        self.nohupfile = shlex.quote(str(self.remote_corpus_dir / app.config.get("SPARV_NOHUP_FILE")))
        self.runscript = shlex.quote(str(self.remote_corpus_dir / app.config.get("SPARV_TMP_RUN_SCRIPT")))

    def __str__(self) -> str:
        """Return a string representation of the serialized object."""
        return str(self.serialize())

    def serialize(self) -> dict:
        """Convert class data into dict.

        Returns:
            Dictionary representation of the job.
        """
        warnings, errors, misc_output = self.get_output()
        priority = registry.get_priority(self) if registry.get_priority(self) != -1 else ""
        return {
            "status": self.status,
            "current_process": self.current_process,
            "pid": self.pid,
            "started": self.started,
            "done": self.done,
            "sparv_exports": self.sparv_exports,
            "current_files": self.current_files,
            "install_scrambled": self.install_scrambled,
            "installed_korp": self.installed_korp,
            "installed_strix": self.installed_strix,
            "latest_seconds_taken": self.latest_seconds_taken,
            "priority": priority,
            "warnings": warnings,
            "errors": errors,
            "sparv_output": misc_output,
            "last_run_started": self.started or "",
            "last_run_ended": self.done or "",
            "progress": self.progress or "",
        }

    def set_parent(self, parent: "Info") -> None:
        """Save reference to parent class.

        Args:
            parent: Parent class instance.
        """
        self.parent = parent

    def set_status(self, status: Status, process: Optional[ProcessName] = None) -> None:
        """Change the status of a job.

        Args:
            status: New status.
            process: Process name.
        """
        process = self.current_process if process is None else process.name
        if self.status[process] != status:
            self.status[process] = status
            if self.status.is_active():
                self.current_process = process
            self.parent.update()

    def set_pid(self, pid: int) -> None:
        """Set pid of job and save.

        Args:
            pid: Process ID.
        """
        self.pid = pid
        self.parent.update()

    def set_install_scrambled(self, scramble: bool) -> None:
        """Set status of 'install_scrambled' and save.

        Args:
            scramble: Scramble status.
        """
        self.install_scrambled = scramble
        self.parent.update()

    def set_sparv_exports(self, sparv_exports: list) -> None:
        """Set the Sparv exports to be created during the next run.

        Args:
            sparv_exports: List of Sparv exports.
        """
        self.sparv_exports = sparv_exports
        self.parent.update()

    def set_current_files(self, current_files: list) -> None:
        """Set the input files to be processed during the next run.

        Args:
            current_files: List of current files.
        """
        self.current_files = current_files
        self.parent.update()

    def set_latest_seconds_taken(self, seconds_taken: int) -> None:
        """Set 'latest_seconds_taken' and save.

        Args:
            seconds_taken: Seconds taken.
        """
        if self.latest_seconds_taken != seconds_taken:
            self.latest_seconds_taken = seconds_taken
            self.parent.update()

    def reset_time(self) -> None:
        """Reset the processing time for a job (e.g. when starting a new one)."""
        self.latest_seconds_taken = 0
        # self.started = None
        self.done = None
        self.sparv_done = None
        self.parent.update()

    def check_requirements(self) -> None:
        """Check if required corpus contents are present.

        Raises:
            Exception: If no config file or input files are provided.
        """
        corpus_contents = storage.list_contents(storage.get_corpus_dir(self.id), exclude_dirs=False)
        if app.config.get("SPARV_CORPUS_CONFIG") not in [i.get("name") for i in corpus_contents]:
            self.set_status(Status.error)
            raise Exception(f"No config file provided for '{self.id}'!")
        if not [i for i in corpus_contents if i.get("path").startswith(app.config.get("SPARV_SOURCE_DIR"))]:
            self.set_status(Status.error)
            raise Exception(f"No input files provided for '{self.id}'!")

    def sync_to_sparv(self) -> None:
        """Sync corpus files from storage server to the Sparv server.

        Raises:
            Exception: If syncing fails.
        """
        self.set_status(Status.running, ProcessName.sync2sparv)

        # Create user and corpus dir on Sparv server
        p = utils.ssh_run(f"mkdir -p {self.remote_corpus_dir_esc} && rm -f {self.nohupfile} {self.runscript}")
        if p.stderr:
            self.set_status(Status.error)
            raise Exception(f"Failed to create corpus dir on Sparv server! {p.stderr.decode()}")

        # Download from storage server to local tmp dir
        # TODO: do this async?
        try:
            local_user_dir = utils.get_resources_dir(mkdir=True)
            storage.download_dir(storage.get_corpus_dir(self.id), local_user_dir, self.id)
        except Exception as e:
            self.set_status(Status.error)
            raise Exception(f"Failed to download corpus '{self.id}' from the storage server! {e}") from e

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
            raise Exception(f"Failed to copy corpus config file to Sparv server! {p.stderr.decode()}")

        # Sync corpus files to Sparv server
        # TODO: do this async!
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
            raise Exception(f"Failed to copy corpus files to Sparv server! {p.stderr.decode()}")

        self.set_status(Status.done)

    def run_sparv(self) -> None:
        """Start a Sparv annotation process.

        Raises:
            exceptions.JobError: If running Sparv fails.
        """
        sparv_command = (
            f"{app.config.get('SPARV_COMMAND')} --dir {self.remote_corpus_dir_esc} {app.config.get('SPARV_RUN')} "
            f"{' '.join(self.sparv_exports)}"
        )
        if self.current_files:
            sparv_command += f" --file {' '.join(shlex.quote(f) for f in self.current_files)}"

        script_content = (f"{app.config.get('SPARV_ENVIRON')} nohup time -p {sparv_command} >{self.nohupfile} "
                          "2>&1 &\necho $!")

        self.started = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        p = utils.ssh_run(
            f"echo {shlex.quote(script_content)} > {self.runscript} && chmod +x {self.runscript} && {self.runscript}"
        )

        if p.returncode != 0:
            stderr = p.stderr.decode() if p.stderr else ""
            self.reset_time()
            self.set_status(Status.error, ProcessName.sparv)
            raise exceptions.JobError(f"Failed to run Sparv! {stderr}")

        # Get pid from Sparv process and store job info
        try:
            float(p.stdout.decode())
            self.set_pid(int(p.stdout.decode()))
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
            app.logger.error("Failed to remove Korp install markers for corpus %s: %s", self.id, p.stderr.decode())

        sparv_installs = app.config.get("SPARV_DEFAULT_KORP_INSTALLS")
        if self.install_scrambled:
            sparv_installs.append("cwb:install_corpus_scrambled")
        else:
            sparv_installs.extend(["cwb:install_corpus"])

        sparv_command = shlex.quote(
            f"{app.config.get('SPARV_COMMAND')} --dir {self.remote_corpus_dir_esc} "
            f"{app.config.get('SPARV_INSTALL')} {' '.join(sparv_installs)}"
        )
        script_content = shlex.quote(
            f"{app.config.get('SPARV_ENVIRON')} nohup time -p sh -c {sparv_command} >{self.nohupfile} "
            "2>&1 &\necho $!"
        )
        self.started = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        p = utils.ssh_run(f"echo {script_content} > {self.runscript} && chmod +x {self.runscript} && {self.runscript}")

        if p.returncode != 0:
            stderr = p.stderr.decode() if p.stderr else ""
            self.reset_time()
            self.set_status(Status.error, ProcessName.korp)
            raise exceptions.JobError(f"Failed to install corpus in Korp. {stderr}")

        self.installed_korp = True
        # Get pid from Sparv process and store job info
        try:
            float(p.stdout.decode())
            self.set_pid(int(p.stdout.decode()))
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
        except Exception as e:
            raise e

        p = utils.ssh_run(
            f"{app.config.get('SPARV_ENVIRON')} {app.config.get('SPARV_COMMAND')} --dir {self.remote_corpus_dir_esc} "
            f"{app.config.get('SPARV_UNINSTALL')} {' '.join(app.config.get('SPARV_DEFAULT_KORP_UNINSTALLS'))}"
        )

        if p.returncode != 0:
            stderr = p.stderr.decode() if p.stderr else ""
            app.logger.error("Failed to uninstall corpus %s from Korp: %s", self.id, stderr)
            raise exceptions.JobError(f"Failed to uninstall corpus from Korp: {stderr}")

        self.installed_korp = False

    def install_strix(self) -> None:
        """Install a corpus in Strix.

        Raises:
            exceptions.JobError: If installing corpus in Strix fails.
        """
        # Remove install markers
        sparv_work_dir = shlex.quote(str(sparv_utils.get_work_dir(self.id)))
        p = utils.ssh_run(f"rm -rf {sparv_work_dir}/sbx_strix.install_*_marker")
        if p.returncode != 0:
            app.logger.error("Failed to remove Strix install markers for corpus %s: %s", self.id, p.stderr.decode())

        sparv_installs = app.config.get("SPARV_DEFAULT_STRIX_INSTALLS")
        sparv_command = shlex.quote(
            f"{app.config.get('SPARV_COMMAND')} --dir {self.remote_corpus_dir_esc} "
            f"{app.config.get('SPARV_INSTALL')} {' '.join(sparv_installs)}"
        )
        script_content = shlex.quote(
            f"{app.config.get('SPARV_ENVIRON')} nohup time -p sh -c {sparv_command} >{self.nohupfile} "
            "2>&1 &\necho $!"
        )
        self.started = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        p = utils.ssh_run(
            f"echo {script_content} > {self.runscript} && chmod +x {self.runscript} && {self.runscript}"
        )

        if p.returncode != 0:
            stderr = p.stderr.decode() if p.stderr else ""
            self.reset_time()
            self.set_status(Status.error, ProcessName.strix)
            raise exceptions.JobError(f"Failed to install corpus in Strix. {stderr}")

        self.installed_strix = True
        # Get pid from Sparv process and store job info
        try:
            float(p.stdout.decode())
            self.set_pid(int(p.stdout.decode()))
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
        except Exception as e:
            raise e

        p = utils.ssh_run(
            f"{app.config.get('SPARV_ENVIRON')} {app.config.get('SPARV_COMMAND')} --dir {self.remote_corpus_dir_esc} "
            f"{app.config.get('SPARV_UNINSTALL')} {' '.join(app.config.get('SPARV_DEFAULT_STRIX_UNINSTALLS'))}"
        )

        if p.returncode != 0:
            stderr = p.stderr.decode() if p.stderr else ""
            app.logger.error("Failed to uninstall corpus %s from Strix: %s", self.id, stderr)
            raise exceptions.JobError(f"Failed to uninstall corpus from Strix: {stderr}")

        self.installed_strix = False

    def abort_sparv(self) -> None:
        """Abort running Sparv process.

        Raises:
            exceptions.ProcessNotRunningError: If Sparv is not running.
            exceptions.JobError: If aborting job fails.
        """
        if self.status.is_waiting(self.current_process):
            registry.pop_queue(self)
            self.set_status(Status.aborted)
            return
        if not self.status.is_running():
            raise exceptions.ProcessNotRunningError("Failed to abort job because Sparv was not running!")
        if not self.pid:
            self.set_status(Status.aborted)
            return
            # raise exceptions.ProcessNotFound("Failed to abort job because no process ID was found!")

        p = utils.ssh_run(f"kill -SIGTERM {self.pid}")
        if p.returncode == 0:
            self.set_pid(None)
            self.set_status(Status.aborted)
        else:
            stderr = p.stderr.decode()
            # Ignore 'no such process' error
            if stderr.endswith(("Processen finns inte\n", "No such process\n")):
                self.set_pid(None)
                self.set_status(Status.aborted)
            else:
                raise exceptions.JobError(f"Failed to abort job! Error: '{stderr}'")

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
            app.logger.debug("stderr: '%s'", p.stderr.decode())
            self.set_pid(None)

        _warnings, errors, misc = self.get_output()
        if self.progress_output == 100:  # noqa: PLR2004
            if self.status.is_running(self.current_process):
                self.set_status(Status.done)
        else:
            if errors:
                app.logger.debug("Error in Sparv: %s", errors)
            if misc:
                app.logger.debug("Sparv output: %s", misc)
            app.logger.debug("Sparv process was not completed successfully.")
            self.set_status(Status.error)
        return False

    def get_output(self) -> tuple[str, str, str]:
        """Check latest Sparv output of this job by reading the nohup file.

        Returns:
            Tuple of warnings, errors, and miscellaneous output.
        """
        if not self.status.has_process_output(self.current_process):
            return "", "", ""

        p = utils.ssh_run(f"cat {self.nohupfile}")

        stdout = p.stdout.decode().strip() if p.stdout else ""
        warnings = errors = misc = ""
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
                        progress = 100
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
                        self.sparv_done = (
                            dateutil.parser.isoparse(self.started) + datetime.timedelta(seconds=real_seconds)
                        ).isoformat()
                    # Ignore "user" and "sys" time output
                    elif re.match(r"user|sys \d.+", line):
                        pass

            self.progress_output = progress

            warnings = "\n".join(warnings)
            errors = "\n".join(errors)
            misc = "\n".join(misc)

        return warnings, errors, misc

    @property
    def seconds_taken(self) -> int:
        """Calculate the time it took to process the corpus until it finished, aborted or until now.

        When a Sparv job is finished it reads the time Sparv took and compensates for extra time the backend
        may take.
        """
        if (
            self.started is None
            or self.status.is_waiting(self.current_process)
            or self.status.is_none(self.current_process)
            or self.status.is_aborted(self.current_process)
        ):
            seconds_taken = 0
        elif self.status.is_running(self.current_process):
            now = datetime.datetime.now(datetime.timezone.utc)
            delta = now - dateutil.parser.isoparse(self.started)
            seconds_taken = max(self.latest_seconds_taken, delta.total_seconds())
        elif self.sparv_done or self.status.is_error(self.current_process):
            delta = dateutil.parser.isoparse(self.sparv_done) - dateutil.parser.isoparse(self.started)
            seconds_taken = max(self.latest_seconds_taken, delta.total_seconds())
            self.done = (dateutil.parser.isoparse(self.started) + datetime.timedelta(seconds=seconds_taken)).isoformat()
        else:
            # TODO: This should never happen!
            app.logger.error(
                "Something went wrong while calculating time taken. Job status: %s; "
                "Current process: %s; Job started: %s",
                self.status,
                self.current_process,
                self.started,
            )
            seconds_taken = 0

        self.set_latest_seconds_taken(seconds_taken)
        return seconds_taken

    @property
    def progress(self) -> Optional[str]:
        """Get the Sparv progress but don't report 100% before the job status has been changed to done.

        Returns:
            Progress percentage as a string.
        """
        if self.status.has_process_output(self.current_process):
            if self.progress_output == 100 and not self.status.is_done(self.current_process):  # noqa: PLR2004
                return "99%"
            return f"{self.progress_output}%"
        if self.status.is_active(self.current_process):
            return "0%"
        return None

    def sync_results(self) -> Optional[tuple[Response, int]]:
        """Sync exports from Sparv server to the storage server.

        Returns:
            None if successful, otherwise a tuple with error message and status code.
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
            return utils.response("Failed to retrieve Sparv exports", err=True, info=p.stderr.decode()), 500

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
            raise Exception(f"Failed to upload exports to the storage server! {e}") from e

        # Transfer plain text sources to the storage server
        local_work_dir = utils.get_work_dir(self.id)
        try:
            app.logger.warning(local_work_dir)
            storage.upload_dir(remote_corpus_dir, local_work_dir, self.id)
        except Exception as e:
            self.set_status(Status.error)
            app.logger.warning(e)
            raise Exception(f"Failed to upload plain text sources to the storage server! {e}") from e

        self.set_status(Status.done)
        return None

    def remove_from_sparv(self) -> None:
        """Remove corpus dir from the Sparv server and abort running job if necessary."""
        try:
            self.abort_sparv()
        except (exceptions.ProcessNotRunningError, exceptions.ProcessNotFoundError):
            pass
        except Exception as e:
            raise e

        p = utils.ssh_run(f"rm -rf {self.remote_corpus_dir_esc}")
        if p.stderr:
            app.logger.error("Failed to remove corpus dir '%s'!", self.remote_corpus_dir)

    def clean(self) -> str:
        """Remove annotation and export files from Sparv server by running 'sparv clean --all'.

        Returns:
            Sparv output.
        """
        p = utils.ssh_run(
            f"rm -f {self.nohupfile} {self.runscript} && {app.config.get('SPARV_ENVIRON')} "
            f"{app.config.get('SPARV_COMMAND')} --dir {self.remote_corpus_dir_esc} clean --all"
        )

        if p.stderr:
            raise Exception(p.stderr.decode())

        sparv_output = p.stdout.decode() if p.stdout else ""
        return ", ".join([line for line in sparv_output.split("\n") if line])

    def clean_export(self) -> tuple[bool, str]:
        """Remove export files from Sparv server by running 'sparv clean --export'.

        Returns:
            Tuple indicating success and Sparv output.
        """
        p = utils.ssh_run(f"{app.config.get('SPARV_ENVIRON')} {app.config.get('SPARV_COMMAND')} "
                          f"--dir {self.remote_corpus_dir_esc} clean --export")
        if p.stderr:
            raise Exception(p.stderr.decode())

        sparv_output = p.stdout.decode() if p.stdout else ""
        sparv_output = ", ".join([line for line in sparv_output.split("\n") if line])
        if not ("Nothing to remove" in sparv_output or "'export' directory removed" in sparv_output):
            app.logger.error(
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

        self.sparv_user = app.config.get("SPARV_USER")
        self.sparv_server = app.config.get("SPARV_HOST")
        self.remote_corpus_dir = str(sparv_utils.get_corpus_dir(self.lang, default_dir=True))
        self.config_file = app.config.get("SPARV_CORPUS_CONFIG")

    def list_languages(self) -> list:
        """List the languages available in Sparv."""
        # Create and corpus dir with config file on Sparv server
        p = utils.ssh_run(
            f"mkdir -p {self.remote_corpus_dir_esc} && "
            f"echo 'metadata:\n  language: {self.lang}' > "
            f"{shlex.quote(self.remote_corpus_dir + '/' + self.config_file)}"
        )
        if p.stderr:
            raise Exception(f"Failed to list languages! {p.stderr.decode()}")

        p = utils.ssh_run(f"{app.config.get('SPARV_ENVIRON')} {app.config.get('SPARV_COMMAND')} "
                          f"--dir {self.remote_corpus_dir_esc} languages")

        if p.returncode != 0:
            stderr = p.stderr.decode() if p.stderr else ""
            raise exceptions.JobError(f"Failed to run Sparv! {stderr}")

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
            f"{shlex.quote(self.remote_corpus_dir + '/' + self.config_file)}"
        )
        if p.stderr:
            raise Exception(f"Failed to list exports! {p.stderr.decode()}")

        # Run Sparv to get available exports
        p = utils.ssh_run(f"{app.config.get('SPARV_ENVIRON')} {app.config.get('SPARV_COMMAND')} --dir "
                          f"{self.remote_corpus_dir_esc} modules --exporters --json")
        if p.returncode != 0:
            stderr = p.stderr.decode() if p.stderr else ""
            raise exceptions.JobError(f"Failed to run Sparv! {stderr}")

        # Parse stdout as json and extract relevant data
        stdout = p.stdout.decode() if p.stdout else ""
        try:
            json_data = json.loads(stdout.strip())
        except json.JSONDecodeError as e:
            raise exceptions.JobError(f"Failed to parse Sparv output as JSON! {e}") from e
        exports = []
        for exporter, exporter_data in json_data["exporters"].items():
            # Skip exporers blacklisted exporters
            if any(re.match(pattern, exporter) for pattern in app.config.get("SPARV_EXPORT_BLACKLIST")):
                continue
            for function, function_data in exporter_data["functions"].items():
                functions_info = {}
                functions_info["export"] = f"{exporter}:{function}"
                functions_info["description"] = function_data["description"]
                export_files = [i.removeprefix("export/") for i in function_data.get("exports", [])]
                functions_info["export_files"] = export_files
                exports.append(functions_info)

        return exports
