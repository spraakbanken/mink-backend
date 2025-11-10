"""Response data models for the Mink API core (used for documentation purposes and data validation)."""

from typing import Generic, TypeVar

from fastapi import File, status
from pydantic import BaseModel, Field

from mink.core.status import Status

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


class BaseResponseWithWarnings(BaseResponse):
    """Model for responses with warnings."""
    warnings: list[str] | None = Field(default=None, description="List of warnings, if any")


class BaseResponseWithInfo(BaseResponse):
    """Model for responses with info field."""
    info: str = Field(default="", description="More detailed information about the response")


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


class BaseResponseWithContents(BaseResponse):
    """Model for responses with file contents field."""
    contents: list[FileModel] = Field(
        default=[FileModel()], description="List of contents, each containing information about a file"
    )


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


class StatusModel(BaseModel):
    """Dictionary containing the status of the different processes."""
    sync2sparv: Status = Field(default=Status.none, description="Status of the sync2sparv process")
    sync2storage: Status = Field(default=Status.none, description="Status of the sync2storage process")
    sparv: Status = Field(default=Status.none, description="Status of the Sparv process")
    korp: Status = Field(default=Status.none, description="Status of the Korp process")
    strix: Status = Field(default=Status.none, description="Status of the Strix process")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "sync2sparv": "done",
                    "sync2storage": "running",
                    "sparv": "waiting",
                    "korp": "error",
                    "strix": "none",
                }
            ]
        }
    }


class JobModel(BaseModel):
    """Model for job."""
    status: StatusModel = Field(
        default=StatusModel(), description="Dictionary containing the status of the different processes"
    )
    current_process: str = Field(default="", description="The current process being executed")
    pid: int | None = Field(default=None, description="The process ID of the current job")
    sparv_exports: list[str] = Field(default=[], description="List of the Sparv export formats requested in the job")
    current_files: list[str] = Field(default=[], description="List of the files currently being processed")
    install_scrambled: bool = Field(default=False, description="Indicates if the installation is scrambled")
    installed_korp: bool = Field(default=False, description="Indicates if the resource is installed in Korp")
    installed_strix: bool = Field(default=False, description="Indicates if the resource is installed in Strix")
    priority: int = Field(default=0, description="The priority of the job in the queue")
    warnings: str = Field(default="", description="Warnings generated during the job")
    errors: str = Field(default="", description="Errors generated during the job")
    sparv_output: str = Field(default="", description="Output from the Sparv process")
    started: str = Field(default="", description="Timestamp of when the current Sparv process started")
    ended: str = Field(default="", description="Timestamp of when the current Sparv process ended")
    duration: int = Field(
        default=0, description="The time elapsed for the current Sparv process (in seconds), until ended or until now."
    )
    progress: str = Field(default="0%", description="Progress of the job in percentage")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": {
                        "sync2sparv": "done",
                        "sync2storage": "running",
                        "sparv": "waiting",
                        "korp": "error",
                        "strix": "none",
                    },
                    "current_process": "sparv",
                    "pid": None,
                    "sparv_exports": ["csv_export:csv", "stats_export:freq_list", "xml_export:pretty"],
                    "current_files": ["dokument1", "dokument2"],
                    "install_scrambled": True,
                    "installed_korp": True,
                    "installed_strix": True,
                    "priority": 1,
                    "warnings": "",
                    "errors": "",
                    "sparv_output": "Nothing to be done.",
                    "started": "2024-01-02T14:31:26+01:00",
                    "ended": "",
                    "duration": 10,
                    "progress": "0%",
                },
                {
                    "status": {
                        "sync2sparv": "none",
                        "sync2storage": "none",
                        "sparv": "done",
                        "korp": "aborted",
                        "strix": "done",
                    },
                    "current_process": "sparv",
                    "pid": None,
                    "sparv_exports": ["xml_export:pretty", "csv_export:csv", "stats_export:sbx_freq_list"],
                    "current_files": [],
                    "install_scrambled": True,
                    "installed_korp": True,
                    "installed_strix": True,
                    "priority": "",
                    "warnings": "",
                    "errors": "",
                    "sparv_output": "The exported files can be found in the following locations:\n • export"
                    "/csv_export/\n • export/stats_export.frequency_list_sbx/\n • export/"
                    "xml_export.pretty/",
                    "started": "2023-12-11T13:24:09+01:00",
                    "ended": "",
                    "duration": 20,
                    "progress": "100%",
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


class ErrorResponse401(BaseErrorResponse):
    """Model for 401 error responses."""
    info: str | None = Field(default=None, description="Additional information about the error")
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "error",
                    "message": "The provided JWT has expired",
                    "return_code": "jwt_expired"
                },
                {
                    "status": "error",
                    "message": "Invalid credentials provided",
                    "return_code": "invalid_credentials",
                    "info": "Signature verification failed"
                },
            ]
        }
    }


class ErrorResponse404(BaseErrorResponse):
    """Model for 404 error responses."""
    model_config = {
        "json_schema_extra": {
            "examples": [
                    {
                        "status": "error",
                        "message": "Failed to authenticate",
                        "return_code": "failed_authenticating",
                    },
                    {
                        "status": "error",
                        "message": "API key not recognized",
                        "return_code": "apikey_not_found",
                    },
                    {
                        "status": "error",
                        "message": "API key has expired",
                        "return_code": "apikey_expired",
                    },
                    {
                        "status": "error",
                        "message": "No login credentials provided",
                        "return_code": "missing_login_credentials",
                    },
                    {
                        "status": "error",
                        "message": "Mink admin status could not be confirmed",
                        "return_code": "admin_status_not_confirmed",
                    },
            ]
        }
    }


class ErrorResponse413(BaseErrorResponse):
    """Model for 413 error responses."""

    return_code: str = Field(default="data_too_large", description="Short code describing the error")
    message: str = Field(
        default="Request data too large (max 100 MB per upload)", description="Short message describing the error"
    )
    max_size_mb: int = Field(default=100, description="Max allowed size in MB")
    info: str | None = Field(default=None, description="Additional information about the error")
    file: str | None = Field(default=None, description="Name of the file that was too large")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "error",
                    "message": "Request data too large",
                    "return_code": "data_too_large",
                    "max_size_mb": 100,
                }
            ]
        }
    }


class ErrorResponse422(BaseErrorResponse):
    """Model for 422 error responses."""
    message: str = Field(default="Validation Error", description="Short message describing the error")
    return_code: str = Field(default="validation_error", description="Short code describing the error")
    info: str = Field(default="Could not process the request due to errors in the input (see errors for details).",
                      description="More detailed information about the response")
    errors: list[str]

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "error",
                    "message": "Validation error",
                    "return_code": "validation_error",
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
                    "message": "An unexpected error occurred",
                    "return_code": "internal_error"
                },
                {
                    "status": "error",
                    "message": "API key check failed",
                    "return_code": "apikey_check_failed"
                },
                {
                    "status": "error",
                    "message": "API key authentication failed",
                    "return_code": "apikey_authentication_failed",
                    "info": "Signature verification failed"
                }
            ]
        }
    }


common_auth_error_responses = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse401},
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse404},
    status.HTTP_422_UNPROCESSABLE_ENTITY: {"model": ErrorResponse422},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse500}
}

# ------------------------------------------------------------------------------
# Reusable query parameters
# ------------------------------------------------------------------------------
# Need to use both alias and validation_alias due to a bug: https://github.com/fastapi/fastapi/issues/10286
upload_file_opt_param = File(None, alias="file", validation_alias="file", description="The file to upload")


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
        data: list[T] = Field(default=[], description="List of data items")

    class ImporterModule(BaseModel):
        """Model for importer modules."""
        file_extension: str = Field(default="", description="File extension for the importer module")
        importer: str = Field(default="", description="Name of the importer module")

    class NameDescriptionValue(BaseModel):
        """Model containing name, description, and value."""
        name: str = Field(default="", description="Name of the value")
        description: str = Field(default="", description="Description of the value")
        value: int

    status_codes: InfoDataModel[StatusCodeModel]
    importer_modules: InfoDataModel[ImporterModule]
    file_size_limits: InfoDataModel[NameDescriptionValue]
    recommended_file_size: InfoDataModel[NameDescriptionValue]

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "success",
                "message": "Listing information about data processing",
                "return_code": "listing_info",
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
                "importer_modules": {
                    "info": "Sparv importers that need to be used for different file extensions",
                    "data": [
                        {"file_extension": ".xml", "importer": "xml_import"},
                        {"file_extension": ".txt", "importer": "text_import"},
                        {"file_extension": ".docx", "importer": "docx_import"},
                        {"file_extension": ".odt", "importer": "odt_import"},
                        {"file_extension": ".pdf", "importer": "pdf_import"},
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
                            "name": "max_corpus_length",
                            "description": "max size for one corpus",
                            "value": 524288000,
                        },
                    ],
                },
                "recommended_file_size": {
                    "info": "approximate recommended file sizes (in bytes) when processing many files with Sparv",
                    "data": [
                        {
                            "name": "max_file_length",
                            "description": "recommended min size for one corpus source file",
                            "value": 1048576,
                        },
                        {
                            "name": "min_file_length",
                            "description": "recommended max size for one corpus source file",
                            "value": 5242880,
                        },
                    ],
                },
            },
        }
    }
