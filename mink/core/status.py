"""Classes defining job statuses."""

from collections import UserDict
from enum import Enum


class Status(str, Enum):
    """Class for representing the status of a Sparv job."""

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
                self.none: "Process does not exist",
                self.waiting: "Waiting to be processed",
                self.running: "Process is running",
                self.done: "Process has finished",
                self.error: "An error occurred in the process",
                self.aborted: "Process was aborted by the user"
        }
        return docs[self.value]

    def __str__(self) -> str:
        """Convert class data into a string."""
        return self.name

    def serialize(self) -> str:
        """Convert class data into a string."""
        return self.name


class ProcessName(str, Enum):
    """Enum class for process names."""

    sync2sparv = "sync2sparv"
    sync2storage = "sync2storage"
    sparv = "sparv"
    korp = "korp"
    strix = "strix"


class JobStatuses(UserDict):
    """Class for representing the statuses of the different job processes."""

    def __init__(self, status: dict | None = None) -> None:
        """Init the status for the different processes, default to none.

        Args:
            status: A dictionary containing the status of each process.
        """
        # Override the old status format
        if not isinstance(status, dict):
            status = {}

        mapping = [(pn.name, getattr(Status, status.get(pn.name, ""), Status.none)) for pn in ProcessName]
        super().__init__(mapping)

    def __str__(self) -> str:
        """Return a string representation of the serialized object.

        Returns:
            str: The serialized object as a string.
        """
        return str(self.serialize())

    def serialize(self) -> dict:
        """Convert class data into dict.

        Returns:
            The serialized statuses as a dictionary.
        """
        return {k: v.name for k, v in self.items()}

    def is_active(self, process_name: str | None = None) -> bool:
        """Check if status is active.

        Args:
            process_name: The name of the process.

        Returns:
            True if the status is active, False otherwise.
        """
        if process_name:
            return self.get(process_name) in {Status.waiting, Status.running}
        return any(status in {Status.waiting, Status.running} for status in self.values())

    def is_inactive(self) -> bool:
        """Check if status is inactive.

        Returns:
            True if the status is inactive, False otherwise.
        """
        return all(status in {Status.none, Status.done, Status.error, Status.aborted} for status in self.values())

    def is_syncing(self) -> bool:
        """Check if status is syncing.

        Returns:
            True if the status is syncing, False otherwise.
        """
        return (
            self.get(ProcessName.sync2sparv) == Status.running or self.get(ProcessName.sync2storage) == Status.running
        )

    def is_none(self, process_name: str | None = None) -> bool:
        """Check if status is none.

        Args:
            process_name: The name of the process.

        Returns:
            True if the status is none, False otherwise.
        """
        if process_name:
            return self.get(process_name) == Status.none
        return all(status == Status.none for status in self.values())

    def is_waiting(self, process_name: str | None = None) -> bool:
        """Check if status is waiting.

        Args:
            process_name: The name of the process.

        Returns:
            True if the status is waiting, False otherwise.
        """
        if process_name:
            return self.get(process_name) == Status.waiting
        return any(status == Status.waiting for status in self.values())

    def is_running(self, process_name: str | None = None) -> bool:
        """Check if status is running.

        Args:
            process_name: The name of the process.

        Returns:
            True if the status is running, False otherwise.
        """
        if process_name:
            return self.get(process_name) == Status.running
        return any(status == Status.running for status in self.values())

    def is_done(self, process_name: str | None) -> bool:
        """Check if status is done processing.

        Args:
            process_name: The name of the process.

        Returns:
            True if the status is done, False otherwise.
        """
        if process_name is None:
            return False
        return self.get(process_name) == Status.done

    def is_error(self, process_name: str | None) -> bool:
        """Check if status is error.

        Args:
            process_name: The name of the process.

        Returns:
            True if the status is error, False otherwise.
        """
        if process_name is None:
            return False
        return self.get(process_name) == Status.error

    def is_aborted(self, process_name: str | None) -> bool:
        """Check if status is aborted.

        Args:
            process_name: The name of the process.

        Returns:
            True if the status is aborted, False otherwise.
        """
        if process_name is None:
            return False
        return self.get(process_name) == Status.aborted

    def has_process_output(self, process_name: str | None) -> bool:
        """Check if process is expected to have process output.

        Args:
            process_name: The name of the process.

        Returns:
            True if the process is expected to have output, False otherwise.
        """
        if process_name is None:
            return False
        if process_name not in {ProcessName.sync2sparv, ProcessName.sync2storage}:
            return self.get(process_name) in {Status.running, Status.done, Status.error}
        return False
