"""Exceptions for Mink."""


class JobError(Exception):
    """Exception used for when something is wrong with a Sparv job."""


class ProcessNotRunningError(JobError):
    """Exception used for when a process is not running although it should be."""


class ProcessNotFoundError(JobError):
    """Exception used for when a process could not be found."""


class JobNotFoundError(JobError):
    """Exception used for when a job could not be found."""


class JwtExpiredError(Exception):
    """Exception used for when a JWT has expired."""


class ApikeyCheckFailedError(Exception):
    """Exception used for when an API key fails to validate."""


class ApikeyExpiredError(Exception):
    """Exception used for when an API key has expired."""


class ApikeyNotFoundError(Exception):
    """Exception used for when an API key was not found."""


class CorpusExistsError(Exception):
    """Exception used for when a corpus ID already exists."""


class CouldNotListSourcesError(Exception):
    """Exception used for when listing of source files failed."""
