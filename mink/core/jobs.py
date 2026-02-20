"""Base job classes used by resource specs."""

import datetime
from typing import Any

from mink.core import utils
from mink.core.status import JobStatuses, Status


class BaseJob:
    """A minimal job object shared by resource types."""

    def __init__(
        self,
        id: str,  # noqa: A002
        processes: list[str],
        status: dict | None = None,
        current_process: str | None = None,
        pid: int | None = None,
        priority: int | str = "",
        warnings: str = "",
        errors: str = "",
        progress: str = "",
        started: str = "",
        ended: str = "",
        duration: int = 0,
        **_obsolete: Any,
    ) -> None:
        """Initialize job by setting class variables.

        Args:
            id: Job ID.
            processes: List of process names to include in the status.
            status: Job status dictionary.
            current_process: Current process (e.g. 'sparv', 'korp', 'strix').
            pid: Process ID.
            priority: Number in queue.
            warnings: Latest warnings.
            errors: Latest errors.
            progress: Progress percentage as a string (e.g. '45%').
            started: Timestamp of when the current process started.
            ended: Timestamp of when the current process ended.
            duration: The time elapsed for the current process (in seconds), until ended or until now.
            **_obsolete: Catch invalid arguments from outdated job items.
        """
        self.id = id
        self.status = JobStatuses(status, processes=processes)
        self.current_process = current_process
        self.pid = pid
        self.priority = priority
        self.warnings = warnings
        self.errors = errors
        self.progress_output = int(progress.strip("%")) if progress else 0
        self.started = started
        self.ended = ended
        self.duration = duration

    def __str__(self) -> str:
        """Return a string representation of the job instance."""
        return f"Job(status={self.status}, current_process={self.current_process}, progress={self.progress}%)"

    def serialize(self, depth: int | None = None) -> dict:
        """Return a serialized dict representation of the job instance."""
        raw = {
            "status": self.status,
            "current_process": self.current_process,
            "pid": self.pid,
            "priority": self.priority,
            "warnings": self.warnings,
            "errors": self.errors,
            "started": self.started,
            "ended": self.ended,
            "duration": self.duration,
            "progress": self.progress,
        }
        return utils.serialize_obj(raw, depth=depth)

    @property
    def progress(self) -> str:
        """Return progress as percentage string."""
        return f"{self.progress_output}%"

    def abort(self) -> None:
        """Abort the job if it is running."""
        if self.status.is_running():
            self.set_status(Status.aborted)

    def update_job_info(self) -> None:
        """Refresh job-specific info (not needed for base jobs)."""

    # ------------------------------------------------------------------------------
    # Setters and getters
    # ------------------------------------------------------------------------------
    def set_parent(self, parent: Any) -> None:
        """Save reference to parent class."""
        self.parent = parent

    def set_attribute(self, attribute: str, value: Any) -> None:
        """Set attribute to new value and save if changed."""
        if getattr(self, attribute) != value:
            setattr(self, attribute, value)
            self.parent.update()

    def set_status(self, status: Status, process: str | Any | None = None) -> None:
        """Change the status of a job."""
        process_name = self.current_process if process is None else getattr(process, "name", process)
        if self.status[process_name] != status:
            self.status[process_name] = status
            if self.status.is_active():
                self.current_process = process_name
            self.parent.update()

    # ------------------------------------------------------------------------------
    # Time handling methods
    # ------------------------------------------------------------------------------
    def get_timedelta(self, end_time: str | None = None) -> int:
        """Get the time elapsed in seconds since 'self.started' until 'end_time' (ISO 8601) or now."""
        if not end_time:
            end_time = utils.get_current_time()
        if not self.started:
            return 0
        end = datetime.datetime.fromisoformat(end_time)
        start = datetime.datetime.fromisoformat(self.started)
        return int((end - start).total_seconds())

    def get_ended_timestamp(self, duration: int) -> str:
        """Get timestamp (ISO 8601) for 'ended' based on 'started' and 'duration' (in seconds)."""
        if not self.started:
            return ""
        start = datetime.datetime.fromisoformat(self.started)
        ended = start + datetime.timedelta(seconds=duration)
        return ended.isoformat(timespec="seconds")

    def reset_time(self, reset_started: bool = True) -> None:
        """Reset timestamp fields (e.g. when queuing a new job)."""
        if reset_started:
            self.started = ""
        self.ended = ""
        self.duration = 0
        if hasattr(self, "parent"):
            self.parent.update()
