"""Exceptions for Mink."""


class JobError(Exception):
    """Exception used for when something is wrong with a Sparv job."""

    pass


class ProcessNotRunning(JobError):
    """Exception used for when a process is not running although it should be."""

    pass


class ProcessNotFound(JobError):
    """Exception used for when a process could not be found."""

    pass


class JobNotFound(JobError):
    """Exception used for when a job could not be found."""

    pass

class JwtExpired(Exception):
    pass

class ApikeyCheckFailed(Exception):
    pass

class ApikeyExpired(Exception):
    pass

class ApikeyNotFound(Exception):
    pass


class CorpusExists(Exception):
    """Exception used for when a corpus ID already exists."""

    pass


class CouldNotListSources(Exception):
    """Exception used for when listing of source files failed."""

    pass
