"""Exceptions for Mink."""

import traceback
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from mink.core import return_codes, utils
from mink.core.logging import logger


class MinkHTTPException(HTTPException):
    """Custom HTTP exception class."""

    def __init__(
        self,
        return_code: return_codes.ReturnCode | str = "",
        status_code: int | None = None,
        message: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Create a custom HTTP exception.

        Args:
            return_code: The return code (should not be empty).
            status_code: The HTTP status code.
            message: The response message.
            **kwargs: Additional key-value pairs to include in the response.
        """
        if isinstance(return_code, return_codes.ReturnCode):
            resolved_status = return_code.status_code if status_code is None else status_code
            resolved_msg = message if message is not None else return_code.message
            resolved_code = return_code.code
        else:
            resolved_status = status_code if status_code is not None else status.HTTP_500_INTERNAL_SERVER_ERROR
            resolved_msg = message or return_codes.UNKNOWN_ERROR.message
            resolved_code = return_code

        super().__init__(
            status_code=resolved_status,
            detail={"message": resolved_msg, "return_code": resolved_code, **kwargs},
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
        return_code=return_codes.VALIDATION_ERROR,
        info="Could not process the request due to errors in the input (see errors for details).",
        errors=errors,
    )


def starlette_exceptions_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle most other uncaught exceptions."""
    code_map = {
        status.HTTP_400_BAD_REQUEST: return_codes.BAD_REQUEST,
        status.HTTP_404_NOT_FOUND: return_codes.PAGE_NOT_FOUND,
        status.HTTP_405_METHOD_NOT_ALLOWED: return_codes.METHOD_NOT_ALLOWED,
    }

    return_code = code_map.get(exc.status_code)
    if return_code is not None:
        return utils.response(return_code=return_code)

    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    logger.error("Unexpected error: %s\n%s", exc, tb)
    return utils.response(
        return_code=return_codes.UNKNOWN_ERROR,
        status_code=exc.status_code,
        info=exc.detail,
    )


def internal_server_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Handle uncaught exceptions."""
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    logger.error("Internal server error: %s\n%s", exc, tb)
    return utils.response(return_code=return_codes.INTERNAL_SERVER_ERROR, info=str(exc))


# ------------------------------------------------------------------------------
# Custom exceptions
# ------------------------------------------------------------------------------

# Job related exceptions

class JobError(Exception):
    """Exception used for when something is wrong with a job."""


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
    def __init__(self, server: str, error: Exception) -> None:
        """Initialize the exception with a message."""
        super().__init__(f"Could not connect to cache server at {server}: {error}")


class ConfigVariableNotSetError(ValueError):
    """Exception used for when a config variable is not set."""
    def __init__(self, config_variable: str) -> None:
        """Initialize the exception with the config variable name."""
        super().__init__(f"Config variable '{config_variable}' is not set.")


class ConfigurationError(Exception):
    """Exception used for when there is a configuration error."""
    def __init__(self, message: str) -> None:
        """Initialize the exception with a message."""
        super().__init__(f"Configuration error: {message}")


class ResourceExistsError(Exception):
    """Exception used for when a resource ID already exists."""
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
