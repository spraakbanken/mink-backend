"""Exceptions for Mink."""


class JobError(Exception):
    """Exception used for when something is wrong with a Sparv job."""


class ProcessNotRunningError(JobError):
    """Exception used for when a process is not running although it should be."""


class ProcessNotFoundError(JobError):
    """Exception used for when a process could not be found."""


class JobNotFoundError(JobError):
    """Exception used for when a job could not be found."""


class JwtExpired(Exception):
    pass

class ApikeyCheckFailed(Exception):
    pass

class ApikeyExpired(Exception):
    pass

class ApikeyNotFound(Exception):
    pass


class CorpusExistsError(Exception):
    """Exception used for when a corpus ID already exists."""


class CouldNotListSourcesError(Exception):
    """Exception used for when listing of source files failed."""
