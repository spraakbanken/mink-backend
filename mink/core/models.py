"""Response data models for the Mink API core (used for documentation purposes and data validation)."""

from typing import ClassVar, Generic, TypeVar

from fastapi import File, status
from pydantic import BaseModel, Field

from mink.core import return_codes

# ------------------------------------------------------------------------------
# Reusable base response models
# ------------------------------------------------------------------------------


class BaseResponse(BaseModel):
    """Base response model with common fields."""
    status: str = Field(default="success", description="Response status, usually 'success' or 'error'")
    message: str = Field(default="", description="Short message describing the response")
    return_code: str = Field(
        default="",
        description="Return code indicating the status of the request, mostly used for frontend error handling"
    )
    info: str | None = Field(default=None, description="More detailed information about the response")
    warnings: list[str] | None = Field(default=None, description="List of warnings, if any")


class CreateResourceResponse(BaseResponse):
    """Model for the response to a resource creation request."""
    resource_id: str = Field(default="", description="The ID of the created resource")
    model_config: ClassVar[dict] = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "success",
                    "message": return_codes.CREATED_RESOURCE.message,
                    "return_code": return_codes.CREATED_RESOURCE.code,
                    "resource_id": "mink-dxh6e6wtff",
                }
            ]
        }
    }


class StatusCodeModel(BaseModel):
    """Status codes for job processes."""
    name: str = Field(default="", description="Name of the status code")
    description: str = Field(default="", description="Description of the status code")


file_model_examples = [
    {
        "name": "dokument1.xml",
        "type": "application/xml",
        "last_modified": "2022-06-10T17:05:18+02:00",
        "size": 1397,
        "path": "dokument1.xml",
    },
    {
        "name": "dokument2.xml",
        "type": "application/xml",
        "last_modified": "2022-06-10T17:05:16+02:00",
        "size": 116,
        "path": "dokument2.xml",
    },
]


class FileModel(BaseModel):
    """Model for file list."""
    name: str = Field(default="", description="Name of the file")
    file_type: str = Field(default="", alias="type", description="MIME type of the file")
    last_modified: str = Field(default="", description="Last modified date of the file")
    size: int = Field(default=0, description="Size of the file in bytes")
    path: str = Field(default="", description="Path to the file in the storage system")

    model_config = {
        "json_schema_extra": {
            "examples": [*file_model_examples]
        }
    }


class ListingFilesResponse(BaseResponse):
    """Model for responses with file contents field."""
    contents: list[FileModel] = Field(
        default=[FileModel()], description="List of contents, each containing information about a file"
    )


class ListResourcesResponse(BaseResponse):
    """Model for responses listing resource IDs."""
    resources: list[str] = Field(default=[], description="List of resource IDs")
    model_config: ClassVar[dict] = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "success",
                    "message": return_codes.LISTING_CONTENT.message,
                    "return_code": return_codes.LISTING_CONTENT.code,
                    "info": "Listing available resources",
                    "resources": ["mink-dxh6e6wtff", "mink-j86tfreaf9", "mink-3qbh7tra6g"],
                }
            ]
        }
    }


class FileResponse(BaseModel):
    """Model for file response."""
    filename: str = Field(default="", description="Name of the file")
    content_type: str = Field(default="application/octet-stream", description="MIME type of the file")
    content: str  # Base64-encoded file content

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "filename": "file1.txt",
                    "content_type": "application/octet-stream",
                    "content": "base64_encoded_content_here",
                }
            ]
        }
    }


user_model_example = {
        "id": "example-idp-abc123",
        "name": "Anna Andersson",
        "email": "anna.andersson@example.com",
        "idp": "example-idp",
        "sub": "abc123",
    }


class UserModel(BaseModel):
    """Model for the user object."""
    user_id: str = Field(default="", alias="id", description="User ID")
    name: str = Field(default="", description="Name of the user")
    email: str = Field(default="", description="Email address of the user")
    idp: str | None = Field(default=None, description="Identity provider of the user")
    sub: str | None = Field(default=None, description="Subject identifier from the identity provider")

    model_config = {
        "json_schema_extra": {"examples": [user_model_example]}  # type: ignore
    }


resource_model_example = {
    "id": "mink-dxh6e6wtff",
    "public_id": "mink-dxh6e6wtff",
    "name": {"swe": "Min testkorpus", "eng": ""},
    "type": "corpus",
    "custom_config": False,
    "source_files": [*file_model_examples],
}

job_model_example = {
    "status": {},
    "current_process": "",
    "pid": None,
    "priority": "",
    "warnings": "",
    "errors": "",
    "queued": "",
    "started": "",
    "ended": "",
    "duration": 0,
    "progress": "0%",
}


class JobModel(BaseModel):
    """Model for a generic job."""
    status: dict[str, str] = Field(default_factory=dict, description="Statuses for the job's processes")
    current_process: str | None = Field(default=None, description="The current process being executed")
    pid: int | None = Field(default=None, description="The process ID of the current job")
    priority: int | str = Field(default="", description="Queue priority")
    warnings: str = Field(default="", description="Warnings from the job")
    errors: str = Field(default="", description="Errors from the job")
    queued: str = Field(default="", description="Timestamp of when the job was queued")
    started: str = Field(default="", description="Timestamp of when the job started")
    ended: str = Field(default="", description="Timestamp of when the job ended")
    duration: int = Field(default=0, description="Duration of the job in seconds")
    progress: str = Field(default="0%", description="Progress percentage as a string")

    model_config: ClassVar[dict] = {
        "json_schema_extra": {"examples": [job_model_example]}
    }


class ResourceModel(BaseModel):
    """Model for the resource object."""
    resource_id: str = Field(default="", alias="id", description="Mink resource ID")
    public_id: str = Field(default="", description="Public resource ID")
    name: dict[str, str] = Field(
        default={},
        description="Name of the resource in different languages",
    )
    resource_type: str = Field(
        default="", alias="type", description="Type of the resource (e.g., 'corpus', 'metadata')"
    )
    custom_config: bool = Field(
        default=False,
        description="Whether the current resource config was uploaded as a custom config",
    )
    source_files: list[FileModel] = Field(
        default=[],
        description="List of source files associated with the resource",
    )

    model_config = {"json_schema_extra": {"examples": [resource_model_example]}}


class QueueHealthJobModel(BaseModel):
    """Model for one active queue entry."""
    resource_id: str = Field(default="", description="Mink resource ID")
    resource_type: str = Field(default="", description="Resource type")
    current_process: str | None = Field(default=None, description="Current queue process")
    job_status: str = Field(default="none", description="Current status for the queue process")
    priority: int | str = Field(default="", description="Queue priority")
    queued: str = Field(default="", description="Timestamp of when the job was queued")
    started: str = Field(default="", description="Timestamp of when the current process started")
    age_reference: str = Field(default="queued", description="Whether age_seconds is measured from queued or started")
    age_seconds: int = Field(default=0, description="Seconds since the age_reference timestamp")


class QueueHealthResponse(BaseResponse):
    """Model for queue health responses."""
    healthy: bool = Field(default=True, description="Whether the queue is considered healthy")
    warning_threshold_seconds: int = Field(
        default=3600, description="Threshold used for warning on old queued or running jobs"
    )
    queue_size: int = Field(default=0, description="Number of active jobs in the queue")
    running_jobs: int = Field(default=0, description="Number of running jobs")
    waiting_jobs: int = Field(default=0, description="Number of waiting jobs")
    max_workers: int = Field(default=1, description="Configured maximum number of simultaneous workers")
    last_started: str | None = Field(default=None, description="Timestamp of the most recently started active job")
    seconds_since_last_start: int | None = Field(
        default=None, description="Seconds since the most recently started active job"
    )
    oldest_running_started: str | None = Field(default=None, description="Start timestamp for the oldest running job")
    oldest_running_seconds: int = Field(default=0, description="Seconds since the oldest running job started")
    oldest_waiting_queued: str | None = Field(default=None, description="Queue timestamp for the oldest waiting job")
    oldest_waiting_seconds: int = Field(default=0, description="Seconds since the oldest waiting job was queued")
    queue_jobs: list[QueueHealthJobModel] = Field(
        default_factory=list, description="Active jobs currently in the queue"
    )

    model_config: ClassVar[dict] = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "success",
                    "message": return_codes.QUEUE_HEALTHY.message,
                    "return_code": return_codes.QUEUE_HEALTHY.code,
                    "healthy": True,
                    "warning_threshold_seconds": 3600,
                    "queue_size": 1,
                    "running_jobs": 1,
                    "waiting_jobs": 0,
                    "max_workers": 1,
                    "last_started": "2026-04-13T09:00:00+02:00",
                    "seconds_since_last_start": 120,
                    "oldest_running_started": "2026-04-13T09:00:00+02:00",
                    "oldest_running_seconds": 120,
                    "oldest_waiting_queued": None,
                    "oldest_waiting_seconds": 0,
                    "queue_jobs": [
                        {
                            "resource_id": "mink-dxh6e6wtff",
                            "resource_type": "corpus",
                            "current_process": "sparv",
                            "job_status": "running",
                            "priority": "",
                            "queued": "2026-04-13T08:59:55+02:00",
                            "started": "2026-04-13T09:00:00+02:00",
                            "age_reference": "started",
                            "age_seconds": 120,
                        }
                    ],
                },
                {
                    "status": "error",
                    "message": return_codes.QUEUE_DEGRADED.message,
                    "return_code": return_codes.QUEUE_DEGRADED.code,
                    "healthy": False,
                    "warning_threshold_seconds": 3600,
                    "warnings": ["Oldest running job has been active for 7260 seconds"],
                    "queue_size": 1,
                    "running_jobs": 1,
                    "waiting_jobs": 0,
                    "max_workers": 1,
                    "last_started": "2026-04-13T07:00:00+02:00",
                    "seconds_since_last_start": 7260,
                    "oldest_running_started": "2026-04-13T07:00:00+02:00",
                    "oldest_running_seconds": 7260,
                    "oldest_waiting_queued": None,
                    "oldest_waiting_seconds": 0,
                    "queue_jobs": [
                        {
                            "resource_id": "mink-dxh6e6wtff",
                            "resource_type": "corpus",
                            "current_process": "sparv",
                            "job_status": "running",
                            "priority": "",
                            "queued": "2026-04-13T06:59:55+02:00",
                            "started": "2026-04-13T07:00:00+02:00",
                            "age_reference": "started",
                            "age_seconds": 7260,
                        }
                    ],
                },
            ]
        }
    }


# ----------------------------------------------------
# Error response models
# ----------------------------------------------------

class BaseErrorResponse(BaseResponse):
    """Abstract base model for error responses."""
    status: str = Field(default="error", description="Response status, usually 'success' or 'error'")
    info: str | None = Field(default=None, description="Additional information about the error")


class ErrorResponse400(BaseErrorResponse):
    """Model for 400 error responses."""
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "error",
                    "message": return_codes.MISSING_RESOURCE_ID.message,
                    "return_code": return_codes.MISSING_RESOURCE_ID.code,
                }
            ]
        }
    }


class ErrorResponse401(BaseErrorResponse):
    """Model for 401 error responses."""
    info: str | None = Field(default=None, description="Additional information about the error")
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "error",
                    "message": return_codes.FAILED_AUTH.message,
                    "return_code": return_codes.FAILED_AUTH.code,
                },
                {
                    "status": "error",
                    "message": return_codes.JWT_EXPIRED.message,
                    "return_code": return_codes.JWT_EXPIRED.code,
                },
                {
                    "status": "error",
                    "message": return_codes.API_KEY_NOT_FOUND.message,
                    "return_code": return_codes.API_KEY_NOT_FOUND.code,
                },
                {
                    "status": "error",
                    "message": return_codes.API_KEY_EXPIRED.message,
                    "return_code": return_codes.API_KEY_EXPIRED.code,
                },
                {
                    "status": "error",
                    "message": return_codes.MISSING_LOGIN_CREDENTIALS.message,
                    "return_code": return_codes.MISSING_LOGIN_CREDENTIALS.code,
                },
                {
                    "status": "error",
                    "message": return_codes.NOT_ADMIN.message,
                    "return_code": return_codes.NOT_ADMIN.code,
                },
            ]
        }
    }


class ErrorResponse404Resource(BaseErrorResponse):
    """Model for 404 resource not found error responses."""
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "error",
                    "message": return_codes.RESOURCE_NOT_FOUND.message,
                    "return_code": return_codes.RESOURCE_NOT_FOUND.code,
                }
            ]
        }
    }


class ErrorResponse404File(BaseErrorResponse):
    """Model for 404 file not found error responses."""
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "error",
                    "message": return_codes.FILE_NOT_FOUND.message,
                    "return_code": return_codes.FILE_NOT_FOUND.code,
                }
            ]
        }
    }


class ErrorResponse413(BaseErrorResponse):
    """Model for 413 error responses."""
    return_code: str = Field(default=return_codes.CONTENT_TOO_LARGE.code, description="Short code describing the error")
    message: str = Field(
        default=return_codes.CONTENT_TOO_LARGE.message, description="Short message describing the error"
    )
    max_size_mb: int = Field(default=100, description="Max allowed size in MB")
    info: str | None = Field(default=None, description="Additional information about the error")
    file: str | None = Field(default=None, description="Name of the file that was too large")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "error",
                    "message": return_codes.CONTENT_TOO_LARGE.message,
                    "return_code": return_codes.CONTENT_TOO_LARGE.code,
                    "max_size_mb": 100,
                }
            ]
        }
    }


class ErrorResponse422(BaseErrorResponse):
    """Model for 422 error responses."""
    message: str = Field(
        default=return_codes.VALIDATION_ERROR.message, description="Short message describing the error"
    )
    return_code: str = Field(default=return_codes.VALIDATION_ERROR.code, description="Short code describing the error")
    info: str = Field(default="Could not process the request due to errors in the input (see errors for details).",
                      description="More detailed information about the response")
    errors: list[str]

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "error",
                    "message": return_codes.VALIDATION_ERROR.message,
                    "return_code": return_codes.VALIDATION_ERROR.code,
                    "info": "Could not process the request due to errors in the input (see errors for details).",
                    "errors": ["query: q (Field required)"],
                }
            ]
        }
    }


class ErrorResponse500(BaseErrorResponse):
    """Model for 500 error responses."""
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "error",
                    "message": return_codes.INTERNAL_SERVER_ERROR.message,
                    "return_code": return_codes.INTERNAL_SERVER_ERROR.code
                },
                {
                    "status": "error",
                    "message": return_codes.API_KEY_CHECK_FAILED.message,
                    "return_code": return_codes.API_KEY_CHECK_FAILED.code,
                },
                {
                    "status": "error",
                    "message": return_codes.API_KEY_ERROR.message,
                    "return_code": return_codes.API_KEY_ERROR.code,
                    "info": "Signature verification failed"
                }
            ]
        }
    }


common_auth_error_responses = {
    status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse400},
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse401},
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse404Resource},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse422},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse500}
}

# ------------------------------------------------------------------------------
# Reusable query parameters
# ------------------------------------------------------------------------------
upload_file_opt_param = File(None, alias="file", description="The file to upload")


# ------------------------------------------------------------------------------
# Specific response models used in the Mink API core
# ------------------------------------------------------------------------------

# Generic type for the data field
T = TypeVar("T")


class InfoResponse(BaseResponse):
    """Model for the /info response."""

    class InfoDataModel(BaseModel, Generic[T]):
        """Abstract base model for models with 'info' and 'data' fields."""
        info: str = Field(default="", description="Description of the data")
        data: list[T] = Field(default_factory=list, description="List of data items")

    class NameDescriptionValue(BaseModel):
        """Model containing name, description, and value."""
        name: str = Field(default="", description="Name of the value")
        description: str = Field(default="", description="Description of the value")
        value: int

    status_codes: InfoDataModel[StatusCodeModel]
    file_size_limits: InfoDataModel[NameDescriptionValue]
    resource_info: dict[str, dict] = Field(
        default_factory=dict,
        description="Resource-type specific information keyed by resource type",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "success",
                "message": return_codes.LISTING_CONTENT.message,
                "return_code": return_codes.LISTING_CONTENT.code,
                "info": "Listing Mink API information",
                "status_codes": {
                    "info": "job status codes",
                    "data": [
                        {"name": "none", "description": "Process does not exist"},
                        {"name": "waiting", "description": "Waiting to be processed"},
                        {"name": "running", "description": "Process is running"},
                        {"name": "done", "description": "Process has finished"},
                        {"name": "error", "description": "An error occurred in the process"},
                        {"name": "aborted", "description": "Process was aborted by the user"},
                    ],
                },
                "file_size_limits": {
                    "info": "size limits (in bytes) for uploaded files",
                    "data": [
                        {
                            "name": "max_content_length",
                            "description": "max size for one request (which may contain multiple files)",
                            "value": 104857600,
                        },
                        {
                            "name": "max_file_length",
                            "description": "max size for one corpus source file",
                            "value": 10485760,
                        },
                        {
                            "name": "max_resource_length",
                            "description": "max size for one resource (total of all source files)",
                            "value": 524288000,
                        },
                    ],
                },
                "resource_info": {"<resource_type>": {"description": "...", "<section>": {"info": "...", "data": []}}},
            },
        }
    }


class ReturnCodesResponse(BaseResponse):
    """Model for the /return-codes response."""
    data: dict[str, list[dict[str, str]]] = Field(
        default_factory=dict,
        description="Dictionary containing lists of return codes keyed by tag",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "success",
                "message": "Listing contents",
                "return_code": "listing_content",
                "info": "Listing all return codes",
                "data": {
                    "Common errors": [
                        {"code": "unexpected_error", "message": "An unexpected error occurred", "status_code": 500},
                        {"code": "page_not_found", "message": "Page not found", "status_code": 404},
                    ],
                    "Authentication and authorization": [
                        {"code": "failed_authenticating", "message": "Failed to authenticate", "status_code": 200},
                        {
                            "code": "missing_login_credentials",
                            "message": "No login credentials provided",
                            "status_code": 200,
                        },
                    ],
                },
            }
        }
    }


class JobStatusModel(BaseModel):
    """Model for the status of a resource (used as base for StatusResponse and StatusesResponse)."""
    job_status: str = Field(default="", description="Status of the current job for the resource")
    info: str = Field(default="", description="Info about the job status")
    resource: ResourceModel = Field(
        default=ResourceModel(),
        description="Object containing information about the resource",
    )
    owner: UserModel = Field(
        default=UserModel(), description="User object containing information about the resource owner"
    )
    job: JobModel = Field(
        default_factory=JobModel,
        description="Job object containing information about the job status",
    )

    model_config: ClassVar[dict] = {
        "json_schema_extra": {
            "examples": [
                    {
                "job_status": "waiting",
                "info": "Job has been queued",
                "resource": resource_model_example,
                "owner": user_model_example,
                "job": job_model_example,
            }
            ]
        }
    }


class StatusResponse(BaseResponse, JobStatusModel):
    """Model for job status responses."""
    model_config: ClassVar[dict] = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "success",
                    "message": return_codes.CHECKED_STATUS.message,
                    "return_code": return_codes.CHECKED_STATUS.code,
                    "job_status": "waiting",
                    "info": "Job has been queued",
                    "resource": resource_model_example,
                    "job": job_model_example,
                }
            ]
        }
    }


class StatusesResponse(BaseResponse):
    """Model for multiple job statuses responses."""
    resources: list[JobStatusModel] = Field(
        default=[], description="List of resource objects containing information about the corpus"
    )

    model_config: ClassVar[dict] = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "success",
                    "message": return_codes.LISTING_CONTENT.message,
                    "return_code": return_codes.LISTING_CONTENT.code,
                    "info": "Listing resource infos",
                    "resources": [
                        {
                            "job_status": "done",
                            "info": "Job was completed successfully",
                            "resource": resource_model_example,
                            "job": job_model_example,
                        },
                        {
                            "job_status": "done",
                            "info": "Job was completed successfully",
                            "resource": {
                                "id": "mink-ezodmp4wxm",
                                "public_id": "mink-ezodmp4wxm",
                                "name": {"swe": "txt-korpus", "eng": "txt-korpus"},
                                "type": "corpus",
                                "custom_config": False,
                                "source_files": [
                                    {
                                        "name": "text1.txt",
                                        "type": "text/plain",
                                        "last_modified": "2023-05-15T10:40:44+02:00",
                                        "size": 825,
                                        "path": "text1.txt",
                                    },
                                    {
                                        "name": "text2.txt",
                                        "type": "text/plain",
                                        "last_modified": "2023-05-15T10:40:45+02:00",
                                        "size": 1169,
                                        "path": "text2.txt",
                                    },
                                ],
                            },
                            "job": job_model_example,
                        }
                    ]
                }
            ]
        }
    }
