"""Classes defining job statuses."""

from collections import UserDict
from collections.abc import Container, Iterable
from enum import StrEnum


class Status(StrEnum):
    """Class for representing the status of a job."""

    none = "none"
    waiting = "waiting"
    running = "running"
    done = "done"
    error = "error"
    aborted = "aborted"

    @property
    def description(self) -> str:
        """Return the description for the status."""
        docs = {
                "none": "Process does not exist",
                "waiting": "Waiting to be processed",
                "running": "Process is running",
                "done": "Process has finished",
                "error": "An error occurred in the process",
                "aborted": "Process was aborted by the user"
        }
        return docs[self.value]

    def __str__(self) -> str:
        """Convert class data into a string."""
        return self.name

    def serialize(self) -> str:
        """Convert class data into a string."""
        return self.name


class JobStatuses(UserDict):
    """Class for representing the statuses of the different job processes.

    Maps process names to their respective Status values and provides helper methods for status checks.
    """

    def __init__(self, status: dict | None, processes: list[str]) -> None:
        """Init the status for the different processes, default to none.

        Args:
            status: A dictionary containing the status of each process.
            processes: List of process names to include.
        """
        # Override the old status format
        if not isinstance(status, dict):
            status = {}

        if processes is None:
            raise ValueError("processes must be provided")
        mapping = [(name, getattr(Status, status.get(name, ""), Status.none)) for name in processes]
        super().__init__(mapping)

    def __str__(self) -> str:
        """Return a string representation of the serialized object."""
        return str(self.serialize())

    def serialize(self) -> dict:
        """Convert class data into dict."""
        return {k: v.name for k, v in self.items()}

    def is_active(self, process_name: str | None = None) -> bool:
        """Check if status for the given process is active."""
        if process_name:
            return self.get(process_name) in {Status.waiting, Status.running}
        return any(status in {Status.waiting, Status.running} for status in self.values())

    def is_inactive(self) -> bool:
        """Check if status for all processes is inactive."""
        return all(status in {Status.none, Status.done, Status.error, Status.aborted} for status in self.values())

    def is_syncing(self, sync_processes: Iterable[str]) -> bool:
        """Check if status for the given processes is syncing ."""
        return any(self.get(name) == Status.running for name in sync_processes)

    def is_none(self, process_name: str | None = None) -> bool:
        """Check if status for the given process is none."""
        if process_name:
            return self.get(process_name) == Status.none
        return all(status == Status.none for status in self.values())

    def is_waiting(self, process_name: str | None = None) -> bool:
        """Check if status for the given process is waiting."""
        if process_name:
            return self.get(process_name) == Status.waiting
        return any(status == Status.waiting for status in self.values())

    def is_running(self, process_name: str | None = None) -> bool:
        """Check if status for the given process is running."""
        if process_name:
            return self.get(process_name) == Status.running
        return any(status == Status.running for status in self.values())

    def is_done(self, process_name: str | None) -> bool:
        """Check if status for the given process is done processing."""
        if process_name is None:
            return False
        return self.get(process_name) == Status.done

    def is_error(self, process_name: str | None) -> bool:
        """Check if status for the given process is error."""
        if process_name is None:
            return False
        return self.get(process_name) == Status.error

    def is_aborted(self, process_name: str | None) -> bool:
        """Check if status for the given process is aborted."""
        if process_name is None:
            return False
        return self.get(process_name) == Status.aborted

    def has_process_output(self, process_name: str | None, no_output_processes: Container[str]) -> bool:
        """Check if process is expected to have process output.

        Args:
            process_name: The name of the process.
            no_output_processes: Process names that do not produce output.
        """
        if process_name is None:
            return False
        if process_name in no_output_processes:
            return False
        return self.get(process_name) in {Status.running, Status.done, Status.error}
