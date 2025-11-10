"""Exceptions for Mink."""

import traceback
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from mink.core import models, utils
from mink.core.logging import logger


class MinkHTTPException(HTTPException):
    """Custom HTTP exception class."""
    def __init__(self, status_code: int, return_code: str, message: str, **kwargs: Any) -> None:
        """Create a custom HTTP exception."""
        super().__init__(
            status_code=status_code,
            detail={"message": message, "return_code": return_code, **kwargs},
        )


# ------------------------------------------------------------------------------
# Custom exception handlers
# ------------------------------------------------------------------------------

def custom_http_exception_handler(_request: Request, exc: MinkHTTPException) -> JSONResponse:
    """Handle custom HTTP exceptions."""
    # Make sure exc.detail is a mapping with string keys and serializable values
    detail = jsonable_encoder(exc.detail)
    return utils.response(status_code=exc.status_code, **detail)


def validation_exception_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle validation exceptions."""
    exc_errors = jsonable_encoder(exc.errors())

    # Parse pydantic errors into a list of readable strings
    errors = []
    for pydantic_error in exc_errors:
        loc = pydantic_error["loc"]
        # Format loc into a string, e.g. "body: field.subfield" or "query: param"
        field_string = loc[0] + ": " + ".".join(loc[1:]) if loc[0] in {"body", "query", "path"} else str(loc)
        errors.append(field_string + f" ({pydantic_error['msg']})")

    return utils.response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, **models.ErrorResponse422(errors=errors).model_dump()
    )


def starlette_exceptions_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle most other uncaught exceptions."""
    if exc.status_code == status.HTTP_400_BAD_REQUEST:
        return utils.response(
            status_code=status.HTTP_400_BAD_REQUEST,
            **models.BaseErrorResponse(message="Bad request", return_code="bad_request").model_dump(),
        )
    if exc.status_code == status.HTTP_404_NOT_FOUND:
        return utils.response(
            status_code=status.HTTP_404_NOT_FOUND,
            **models.BaseErrorResponse(message="Resource not found", return_code="resource_not_found").model_dump(),
        )
    if exc.status_code == status.HTTP_405_METHOD_NOT_ALLOWED:
        return utils.response(
            status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
            **models.BaseErrorResponse(message="Method not allowed", return_code="method_not_allowed").model_dump(),
        )
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    logger.error("Unexpected error: %s\n%s", exc, tb)
    return utils.response(
        status_code=exc.status_code,
        **models.BaseErrorResponse(
            message="Unknown error", return_code="unknown_error", info=exc.detail
        ).model_dump(),
    )


def internal_server_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Handle uncaught exceptions."""
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    logger.error("Internal server error: %s\n%s", exc, tb)
    return utils.response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        **models.BaseErrorResponse(
            message="Internal server error", return_code="internal_server_error", info=str(exc)
        ).model_dump(),
    )


# ------------------------------------------------------------------------------
# Custom exceptions
# ------------------------------------------------------------------------------

# Job related exceptions

class JobError(Exception):
    """Exception used for when something is wrong with a Sparv job."""


class ProcessStillRunningError(JobError):
    """Exception used for when a process is still running although it should not be."""


class ProcessNotRunningError(JobError):
    """Exception used for when a process is not running although it should be."""


class ProcessNotFoundError(JobError):
    """Exception used for when a process could not be found."""


class JobNotFoundError(JobError):
    """Exception used for when a job could not be found."""
    def __init__(self, resource_id: str) -> None:
        """Initialize the exception with a message."""
        super().__init__(f"No resource found with ID '{resource_id}'")


# Authentication/authorization related exceptions

class ApikeyCheckFailedError(Exception):
    """Exception used for when an API key fails to validate."""


class ApikeyExpiredError(Exception):
    """Exception used for when an API key has expired."""


class ApikeyNotFoundError(Exception):
    """Exception used for when an API key was not found."""


class CreateResourceError(Exception):
    """Exception used for when a resource could not be created."""
    def __init__(self, resource_id: str, message: str) -> None:
        """Initialize the exception with a message."""
        super().__init__(f"Failed to create resource '{resource_id}': {message}")


class RemoveResourceError(Exception):
    """Exception used for when a resource could not be removed."""
    def __init__(self, resource_id: str, message: str) -> None:
        """Initialize the exception with a message."""
        super().__init__(f"Failed to remove resource '{resource_id}': {message}")


# Storage related exceptions

class ReadError(Exception):
    """Exception used for when reading/downloading from the storage server fails."""
    def __init__(self, path: Path | str, error: str) -> None:
        """Initialize the exception with the path and error message."""
        super().__init__(f"Failed to read or download '{path}': {error}")


class WriteError(Exception):
    """Exception used for when writing to the storage server fails."""
    def __init__(self, path: Path | str, error: str) -> None:
        """Initialize the exception with the path and error message."""
        super().__init__(f"Failed to write to '{path}': {error}")


# Misc exceptions

class CacheConnectionError(Exception):
    """Exception used for when the cache client could not connect."""
    def __init__(self, server: str, error: str) -> None:
        """Initialize the exception with a message."""
        super().__init__(f"Could not connect to cache server at {server}: {error}")


class ConfigVariableNotSetError(ValueError):
    """Exception used for when a config variable is not set."""
    def __init__(self, config_variable: str) -> None:
        """Initialize the exception with the config variable name."""
        super().__init__(f"Config variable '{config_variable}' is not set.")


class CorpusExistsError(Exception):
    """Exception used for when a corpus ID already exists."""
    def __init__(self, resource_id: str) -> None:
        """Initialize the exception with the resource ID."""
        super().__init__(f"Resource {resource_id} already exists")


class CouldNotListSourcesError(Exception):
    """Exception used for when listing of source files failed."""


class InvalidResourceTypeError(TypeError):
    """Exception used for when a resource type is invalid."""
    def __init__(self, resource_type: str) -> None:
        """Initialize the exception with the resource type."""
        super().__init__(f"Invalid resource type: {resource_type}")


class ParameterError(ValueError):
    """Exception used for when parameters are used incorrectly."""


class PrerequisiteError(Exception):
    """Exception used for when a prerequisite is not met."""


class RequestIDNotSetError(Exception):
    """Exception used for when a request ID is not set although it should be."""
