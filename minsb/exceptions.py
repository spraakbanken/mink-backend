"""Exceptions for Min Språkbank."""


class JobError(Exception):
    """Exception used for when something is wrong with a Sparv job."""

    pass


class ProcessNotRunning(JobError):
    """Exception used for when a process is not running although it should be."""

    pass


class ProcessNotFound(JobError):
    """Exception used for when a process could not be found."""

    pass
