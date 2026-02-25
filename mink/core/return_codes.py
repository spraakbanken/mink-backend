"""Return codes for the Mink routes."""

from dataclasses import dataclass, field

from fastapi import status


@dataclass(frozen=True)
class ReturnCode:
    """Structured return code for API responses."""

    code: str
    message: str
    status_code: int = status.HTTP_200_OK
    tag: str = field(default="Other")


# ------------------------------------------------------------------------------
# Tag names
# ------------------------------------------------------------------------------
ERRORS = "Common errors"
AUTH = "Authentication and authorization"
ADMIN = "Admin mode"
RESOURCE = "Resource handling"
CONTENT = "File/content handling"
JOB = "Job handling"

# ------------------------------------------------------------------------------
# Common error codes
# ------------------------------------------------------------------------------
UNKNOWN_ERROR = ReturnCode(
    "unexpected_error",
    message="An unexpected error occurred",
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    tag=ERRORS,
)
PAGE_NOT_FOUND = ReturnCode(
    "page_not_found", message="Page not found", status_code=status.HTTP_404_NOT_FOUND, tag=ERRORS
)
BAD_REQUEST = ReturnCode("bad_request", message="Bad request", status_code=status.HTTP_400_BAD_REQUEST, tag=ERRORS)
METHOD_NOT_ALLOWED = ReturnCode(
    "method_not_allowed", message="Method not allowed", status_code=status.HTTP_405_METHOD_NOT_ALLOWED, tag=ERRORS
)
INTERNAL_SERVER_ERROR = ReturnCode(
    "internal_server_error",
    message="Internal server error",
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    tag=ERRORS,
)
VALIDATION_ERROR = ReturnCode(
    "validation_error", message="Validation Error", status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, tag=ERRORS
)
CONTENT_TOO_LARGE = ReturnCode(
    "content_too_large",
    message="Request data too large",
    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
    tag=ERRORS,
)

# ------------------------------------------------------------------------------
# Authentication and authorization
# ------------------------------------------------------------------------------
FAILED_AUTH = ReturnCode(
    "failed_authenticating", "Failed to authenticate", status_code=status.HTTP_401_UNAUTHORIZED, tag=AUTH
)
MISSING_LOGIN_CREDENTIALS = ReturnCode(
    "missing_login_credentials",
    message="No login credentials provided",
    status_code=status.HTTP_401_UNAUTHORIZED,
    tag=AUTH,
)
API_KEY_CHECK_FAILED = ReturnCode(
    "apikey_check_failed",
    message="API key check failed",
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    tag=AUTH,
)
API_KEY_ERROR = ReturnCode(
    "apikey_error",
    message="API key authentication failed",
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    tag=AUTH,
)
API_KEY_EXPIRED = ReturnCode(
    "apikey_expired", message="API key expired", status_code=status.HTTP_401_UNAUTHORIZED, tag=AUTH
)
API_KEY_NOT_FOUND = ReturnCode(
    "apikey_not_found", message="API key not recognized", status_code=status.HTTP_401_UNAUTHORIZED, tag=AUTH
)
JWT_EXPIRED = ReturnCode(
    "jwt_expired", message="The provided JWT has expired", status_code=status.HTTP_401_UNAUTHORIZED, tag=AUTH
)
INVALID_SECRET_KEY = ReturnCode(
    "invalid_secret_key",
    message="Failed to confirm secret key for protected route",
    status_code=status.HTTP_401_UNAUTHORIZED,
    tag=AUTH,
)

# ------------------------------------------------------------------------------
# Admin mode
# ------------------------------------------------------------------------------
ADMIN_OFF = ReturnCode("admin_off", message="Admin mode turned off", status_code=status.HTTP_200_OK, tag=ADMIN)
ADMIN_ON = ReturnCode("admin_on", message="Admin mode turned on", status_code=status.HTTP_200_OK, tag=ADMIN)
ADMIN_STATUS = ReturnCode(
    "admin_status", message="Returning status of admin mode", status_code=status.HTTP_200_OK, tag=ADMIN
)
NOT_ADMIN = ReturnCode(
    "not_admin",
    message="Mink admin status could not be confirmed",
    status_code=status.HTTP_401_UNAUTHORIZED,
    tag=ADMIN,
)
MISSING_SESSION_ID = ReturnCode(
    "missing_session_id",
    message="Failed to set admin mode: no session ID found",
    status_code=status.HTTP_400_BAD_REQUEST,
    tag=ADMIN,
)

# ------------------------------------------------------------------------------
# Resource handling
# ------------------------------------------------------------------------------
MISSING_RESOURCE_ID = ReturnCode(
    "missing_resource_id", message="No resource ID provided", status_code=status.HTTP_400_BAD_REQUEST, tag=RESOURCE
)
CREATED_RESOURCE = ReturnCode(
    "created_resource", message="Resource created successfully", status_code=status.HTTP_201_CREATED, tag=RESOURCE
)
FAILED_CREATING_RESOURCE = ReturnCode(
    "failed_creating_resource",
    message="Failed to create resource",
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    tag=RESOURCE,
)
RESOURCE_NOT_FOUND = ReturnCode(
    "resource_not_found",
    message="Resource does not exist or you do not have access to it",
    status_code=status.HTTP_404_NOT_FOUND,
    tag=RESOURCE,
)
RESOURCE_NOT_PROCESSED = ReturnCode(
    "resource_not_processed",
    message="Resource has not been processed yet",
    status_code=status.HTTP_404_NOT_FOUND,
    tag=RESOURCE,
)
INVALID_RESOURCE_TYPE = ReturnCode(
    "invalid_resource_type", message="Invalid resource type", status_code=status.HTTP_400_BAD_REQUEST, tag=RESOURCE
)
REMOVED_RESOURCE = ReturnCode(
    "removed_resource", message="Resource successfully removed", status_code=status.HTTP_200_OK, tag=RESOURCE
)
INVALID_CONFIG = ReturnCode(
    "invalid_config",
    message="The config file is invalid or incompatible with your resource",
    status_code=status.HTTP_400_BAD_REQUEST,
    tag=RESOURCE,
)
UNINSTALLED = ReturnCode(
    "uninstalled", message="Resource uninstalled successfully", status_code=status.HTTP_200_OK, tag=RESOURCE
)
FAILED_UNINSTALLING = ReturnCode(
    "failed_uninstalling",
    message="Failed to uninstall resource",
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    tag=RESOURCE,
)

# ------------------------------------------------------------------------------
# File/content handling
# ------------------------------------------------------------------------------
FAILED_DOWNLOADING = ReturnCode(
    "failed_downloading_file",
    message="Failed to download file(s)",
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    tag=CONTENT,
)
FILE_NOT_FOUND = ReturnCode(
    "file_not_found", message="File(s) not found", status_code=status.HTTP_404_NOT_FOUND, tag=CONTENT
)
FILE_UPLOADED = ReturnCode(
    "uploaded_file", message="File(s) successfully uploaded", status_code=status.HTTP_201_CREATED, tag=CONTENT
)
FAILED_UPLOADING = ReturnCode(
    "failed_uploading_file",
    message="Failed to upload file(s)",
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    tag=CONTENT,
)
MISSING_FILE_UPLOAD = ReturnCode(
    "missing_file_upload",
    message="No file(s) provided for upload",
    status_code=status.HTTP_400_BAD_REQUEST,
    tag=CONTENT,
)
INVALID_FILE = ReturnCode(
    "invalid_file", message="Invalid file format", status_code=status.HTTP_400_BAD_REQUEST, tag=CONTENT
)
REMOVED_CONTENT = ReturnCode(
    "removed_content", message="Content successfully removed", status_code=status.HTTP_200_OK, tag=CONTENT
)
FAILED_REMOVING_CONTENT = ReturnCode(
    "failed_removing_content",
    message="Failed to remove content",
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    tag=CONTENT,
)
FAILED_SYNCING = ReturnCode(
    "failed_syncing", message="Failed to sync files", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, tag=CONTENT
)
LISTING_CONTENT = ReturnCode("listing_content", message="Listing contents", status_code=status.HTTP_200_OK, tag=CONTENT)
FAILED_LISTING_CONTENT = ReturnCode(
    "failed_listing_content",
    message="Failed to list contents",
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    tag=CONTENT,
)

# ------------------------------------------------------------------------------
# Job handling
# ------------------------------------------------------------------------------
QUEUE_ADVANCED = ReturnCode(
    "advanced_queue", message="Queue advancing completed", status_code=status.HTTP_200_OK, tag=JOB
)
NO_RUNNING_JOB = ReturnCode(
    "no_running_job",
    message="No running job found for this resource",
    status_code=status.HTTP_404_NOT_FOUND,
    tag=JOB,
)
FAILED_QUEUING = ReturnCode(
    "failed_queuing", message="Failed to queue job", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, tag=JOB
)
FAILED_UNQUEUING = ReturnCode(
    "failed_unqueuing", message="Failed to unqueue job", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, tag=JOB
)
FAILED_RUNNING = ReturnCode(
    "failed_running", message="Failed to run job", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, tag=JOB
)
ABORTED_JOB = ReturnCode("aborted_job", message="Successfully aborted job", status_code=status.HTTP_200_OK, tag=JOB)
FAILED_ABORTING = ReturnCode(
    "failed_aborting", message="Failed to abort job", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, tag=JOB
)
FAILED_GETTING_JOB = ReturnCode(
    "failed_getting_job",
    message="Failed to get job for resource",
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    tag=JOB,
)
CHECKED_STATUS = ReturnCode("checked_status", message="Checked status of job", status_code=status.HTTP_200_OK, tag=JOB)
FAILED_CHECKING_STATUS = ReturnCode(
    "failed_checking_status",
    message="Failed to check status of job",
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    tag=JOB,
)
PROCESS_RUNNING = ReturnCode(
    "process_running",
    message="Failed to perform operation, process is currently running",
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    tag=JOB,
)


# ------------------------------------------------------------------------------


def get_all_return_codes() -> list[ReturnCode]:
    """Get all declared return code constants in this module."""
    # Keep only module-level constants (UPPER_CASE) that are ReturnCode instances.
    return [value for name, value in globals().items() if name.isupper() and isinstance(value, ReturnCode)]
