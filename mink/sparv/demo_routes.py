"""Routes for unauthenticated Sparv usage (demo mode)."""

import time

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import FileResponse, JSONResponse

import mink.sparv.models as sparv_models
from mink.core import exceptions, models, return_codes, route_utils, utils
from mink.core.config import settings
from mink.core.logging import logger
from mink.sb_auth.login import secret_key_or_admin_mode
from mink.sparv import demo, processing
from mink.sparv.config import sparv_settings
from mink.sparv.storage import storage

router = APIRouter(tags=["Sparv Demo"], prefix="/demo/corpus")


@router.post(
    "/run",
    operation_id="run-demo-corpus-job",
    response_model=models.StatusResponse,
    responses={
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": models.ErrorResponse422},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": models.ErrorResponse500,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.FAILED_QUEUING.message,
                        "return_code": return_codes.FAILED_QUEUING.code,
                        "info": "BaseException",
                    }
                }
            },
        },
    },
)
def run_sparv_demo(
    text: str = Query(..., description="The text to be processed"),
    config: str | None = Query(None, description="The config file as plain text"),
) -> JSONResponse:
    """Run a Sparv annotation job for the current input.

    ### Example

    ```bash
    curl -X POST --get '{{host}}/demo/corpus/run' --data-urlencode 'text=Detta är en text.'
    ```
    """
    # Reject if input text is empty or only whitespace
    text = text.strip()
    if not text:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.VALIDATION_ERROR,
            info="Input text must not be empty or only whitespace",
        )
    # Reject if input text is too long
    size = len(text.encode("UTF-8"))
    if size > settings.MAX_FILE_LENGTH:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.VALIDATION_ERROR,
            info=f"Input text is too long (max {settings.MAX_FILE_LENGTH} bytes)",
        )

    # Get existing demo resource or create a new one
    info_item, queued = demo.get_and_queue_demo_resource(text, config)

    if queued:
        # Wait a few seconds to check whether anything terminated early
        time.sleep(3)
    return utils.response(return_code=return_codes.CHECKED_STATUS, **route_utils.make_status_response(info_item))


@router.post(
    "/job/abort/{resource_id}",
    operation_id="abort-demo-corpus-job",
    response_model=models.StatusResponse,
    responses={
        status.HTTP_200_OK: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": return_codes.ABORTED_JOB.message,
                        "return_code": return_codes.ABORTED_JOB.code,
                    }
                }
            }
        },
        status.HTTP_404_NOT_FOUND: {
            "model": models.ErrorResponse404Resource,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.NO_RUNNING_JOB.message,
                        "return_code": return_codes.NO_RUNNING_JOB.code,
                    }
                }
            },
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": models.ErrorResponse422},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": models.ErrorResponse500,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.FAILED_ABORTING.message,
                        "return_code": return_codes.FAILED_ABORTING.code,
                        "info": "BaseException",
                    }
                }
            },
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": models.BaseErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.PROCESS_RUNNING.message,
                        "return_code": return_codes.PROCESS_RUNNING.code,
                        "info": "Cannot abort job while syncing files",
                    }
                }
            },
        },
    },
)
async def abort_demo_corpus_job(resource_id: str) -> JSONResponse:
    """Abort the current job for a demo corpus resource."""
    # Validate demo access and refresh the resource expiry timestamp
    info_item = demo.get_demo_resource_by_id(resource_id)
    job = processing.abort_job(info_item)
    return utils.response(return_code=return_codes.ABORTED_JOB, job_status=job.status.serialize())


@router.get(
    "/status/get/{resource_id}",
    operation_id="get-demo-corpus-status",
    response_model=models.StatusResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": models.ErrorResponse404Resource,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.RESOURCE_NOT_FOUND.message,
                        "return_code": return_codes.RESOURCE_NOT_FOUND.code,
                        "info": "Error getting job info for resource",
                    }
                }
            },
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": models.ErrorResponse422},
    },
)
async def get_demo_corpus_status(resource_id: str) -> JSONResponse:
    """Get the status of a demo corpus resource."""
    # Validate demo access and refresh the resource expiry timestamp
    info_item = demo.get_demo_resource_by_id(resource_id)
    return utils.response(return_code=return_codes.CHECKED_STATUS, **route_utils.make_status_response(info_item))


@router.get(
    "/input/get/{resource_id}",
    operation_id="get-demo-corpus-input",
    response_model=sparv_models.InputResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": models.ErrorResponse404Resource,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.RESOURCE_NOT_FOUND.message,
                        "return_code": return_codes.RESOURCE_NOT_FOUND.code,
                        "info": "Error getting job info for resource",
                    }
                }
            },
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": models.ErrorResponse422},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": models.ErrorResponse500,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.FAILED_RETRIEVING_CONTENT.message,
                        "return_code": return_codes.FAILED_RETRIEVING_CONTENT.code,
                        "info": "BaseException",
                    }
                }
            },
        },
    },
)
async def get_demo_corpus_input(resource_id: str) -> JSONResponse:
    """Get the input text and config of a demo corpus resource.

    ### Example

    ```bash
    curl -X GET '{{host}}/demo/corpus/input/get/{resource_id}'
    ```
    """
    # Validate demo access and refresh the resource expiry timestamp
    _info_item = demo.get_demo_resource_by_id(resource_id)

    # Get input text
    input_text = ""
    try:
        input_file_path = storage.get_source_dir(resource_id) / sparv_settings.SPARV_DEMO_INPUT_FILENAME
        input_text = storage.get_file_contents(input_file_path)
    except Exception as e:
        logger.exception(f"Failed to retrieve input text for resource {resource_id}: {e}")

    # Get config
    config_text = ""
    try:
        config_file_path = storage.get_config_file(resource_id)
        config_text = storage.get_file_contents(config_file_path)
    except Exception as e:
        logger.exception(f"Failed to retrieve config for resource {resource_id}: {e}")

    if not input_text and not config_text:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.FAILED_RETRIEVING_CONTENT, info="Failed to retrieve input text and config"
        )

    return utils.response(return_code=return_codes.RETRIEVED_CONTENT, input_text=input_text, config=config_text)


@router.get(
    "/export/get/{resource_id}",
    operation_id="get-demo-corpus-output",
    response_model=sparv_models.OutputResponse,
    responses={
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": models.ErrorResponse422},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": models.ErrorResponse500,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.FAILED_RETRIEVING_CONTENT.message,
                        "return_code": return_codes.FAILED_RETRIEVING_CONTENT.code,
                        "info": "BaseException",
                    }
                }
            },
        },
    },
)
async def get_demo_corpus_output(resource_id: str) -> JSONResponse:
    """Get the output of a demo corpus resource.

    ### Example

    ```bash
    curl -X GET '{{host}}/demo/corpus/export/get/{resource_id}'
    ```
    """
    # Make sure the resource exists and is a demo resource, and update its last_accessed timestamp
    _info_item = demo.get_demo_resource_by_id(resource_id)

    output = ""
    try:
        export_dir = storage.get_export_dir(resource_id)
        export_contents = storage.list_contents(export_dir)
        assert any(item["path"] == sparv_settings.SPARV_DEMO_DEFAULT_EXPORT_FILE for item in export_contents)
        xml_file_path = export_dir / sparv_settings.SPARV_DEMO_DEFAULT_EXPORT_FILE
        output = storage.get_file_contents(xml_file_path)
    except Exception as e:
        logger.exception(f"Failed to retrieve output for resource {resource_id}: {e}")

    if not output:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.FAILED_RETRIEVING_CONTENT, info="Failed to retrieve output"
        )

    return utils.response(return_code=return_codes.RETRIEVED_CONTENT, output=output)


@router.get(
    "/exports/list/{resource_id}",
    operation_id="list-demo-corpus-exports",
    response_model=models.ListingFilesResponse,
    responses={
        status.HTTP_200_OK: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": return_codes.LISTING_CONTENT.message,
                        "return_code": return_codes.LISTING_CONTENT.code,
                        "info": "Listing export files",
                        "contents": [
                            {
                                "name": "dokument1.csv",
                                "type": "text/csv",
                                "last_modified": "2022-06-10T17:55:37+02:00",
                                "size": 4876,
                                "path": "csv_export/dokument1.csv",
                            },
                            {
                                "name": "dokument1_export.xml",
                                "type": "application/xml",
                                "last_modified": "2022-06-10T17:55:38+02:00",
                                "size": 13429,
                                "path": "xml_export.pretty/dokument1_export.xml",
                            },
                        ],
                    }
                }
            },
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": models.ErrorResponse500,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.FAILED_LISTING_CONTENT.message,
                        "return_code": return_codes.FAILED_LISTING_CONTENT.code,
                        "info": "Failed to list export files",
                    }
                }
            },
        },
    },
)
async def list_demo_corpus_exports(resource_id: str) -> JSONResponse:
    """List the available export files for the demo corpus created by Sparv.

    ### Example

    ```bash
    curl '{{host}}/demo/corpus/exports/list/<resource_id>'
    ```
    """
    # Make sure the resource exists and is a demo resource, and update its last_accessed timestamp
    _info_item = demo.get_demo_resource_by_id(resource_id)

    try:
        exports = storage.list_contents(
            storage.get_export_dir(resource_id), blacklist=sparv_settings.SPARV_EXPORT_BLACKLIST
        )
        # Filter exports by SPARV_DEMO_ALLOWED_EXPORT_PATHS
        exports = [
            item
            for item in exports
            if any(
                item["path"] == allowed_path or item["path"].startswith(f"{allowed_path}/")
                for allowed_path in sparv_settings.SPARV_DEMO_ALLOWED_EXPORT_PATHS
            )
        ]

        return utils.response(return_code=return_codes.LISTING_CONTENT, info="Listing export files", contents=exports)
    except Exception as e:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.FAILED_LISTING_CONTENT, info=f"Failed to list export files: {e}"
        ) from e


@router.get(
    "/exports/download/{resource_id}",
    operation_id="download-demo-corpus-exports",
    response_model=models.FileResponse,
    response_class=FileResponse,
    responses={
        status.HTTP_200_OK: {"content": {"application/octet-stream": {}}, "description": "A file download response"},
        status.HTTP_404_NOT_FOUND: {"model": models.ErrorResponse404File},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": models.ErrorResponse500,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.FAILED_DOWNLOADING.message,
                        "return_code": return_codes.FAILED_DOWNLOADING.code,
                        "info": "BaseException",
                    }
                }
            },
        },
    },
)
async def download_demo_corpus_exports(
    resource_id: str,
    download_file: str = Query(..., alias="file", min_length=1, description="The file name or path to download"),
) -> FileResponse:
    """Download an export file created by Sparv.

    Use the `file` parameter to specify the export file you want to download. This parameter must be supplied as a path
    relative to the export directory.

    ### Example

    ```bash
    curl '{{host}}/demo/corpus/exports/download/<resource_id>?file=xml_export.pretty/<input>_export.xml'
    ```
    """
    # Make sure the resource exists and is a demo resource, and update its last_accessed timestamp
    _info_item = demo.get_demo_resource_by_id(resource_id)

    return route_utils.download_exports_response(
        storage=storage,
        resource_id=resource_id,
        remote_dir=storage.get_export_dir(resource_id),
        local_resource_dir=storage.get_local_resource_dir(resource_id, mkdir=True),
        local_exports_dir=storage.get_local_export_dir(resource_id, mkdir=True),
        download_file=download_file,
        zipped=False,
        blacklist=sparv_settings.SPARV_EXPORT_BLACKLIST,
        allowed_paths=sparv_settings.SPARV_DEMO_ALLOWED_EXPORT_PATHS,
    )


@router.delete(
    "/remove/{resource_id}",
    operation_id="remove-demo-corpus",
    response_model=models.BaseResponse,
    responses={
        status.HTTP_200_OK: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": return_codes.REMOVED_RESOURCE.message,
                        "return_code": return_codes.REMOVED_RESOURCE.code,
                    }
                }
            }
        },
        **models.common_auth_error_responses,
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": models.ErrorResponse500,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.FAILED_REMOVING_CONTENT.message,
                        "return_code": return_codes.FAILED_REMOVING_CONTENT.code,
                        "info": "Failed to remove resource from storage",
                    }
                }
            },
        },
    },
)
async def remove_demo_corpus(resource_id: str, _access: dict = Depends(secret_key_or_admin_mode)) -> JSONResponse:
    """Remove a demo corpus resource (for admin use only).

    Will abort any running job for the resource and remove it from storage and the registry.

    ### Example

    ```bash
    curl -X DELETE '{{host}}/demo/corpus/remove/{resource_id}' -H 'Authorization: Bearer YOUR_JWT' -H 'cookie: \
session_id=MY_SESSION_ID'
    ```
    """
    # Validate demo access
    info_item = demo.get_demo_resource_by_id(resource_id)

    # Remove from storage
    try:
        storage.remove_dir(storage.get_corpus_dir(resource_id), resource_id)
    except Exception as e:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.FAILED_REMOVING_CONTENT,
            info=f"Failed to remove resource from storage: {e}",
        ) from e

    # Remove from registry and abort job if running
    try:
        info_item.remove(abort_job=True)
    except Exception:
        logger.exception("Failed to remove resource '%s' from registry.", resource_id)

    return utils.response(return_code=return_codes.REMOVED_RESOURCE)


@router.delete(
    "/remove-expired",
    operation_id="remove-expired-demo-corpora",
    response_model=sparv_models.RemovedResourcesResponse,
    responses={
        **models.common_auth_error_responses,
    },
)
async def remove_expired_demo_corpora(_access: dict = Depends(secret_key_or_admin_mode)) -> JSONResponse:
    """Remove all expired demo corpus resources (for admin use only).

    ### Example

    ```bash
    curl -X DELETE '{{host}}/demo/corpus/remove-expired' -H 'Authorization: Bearer YOUR_JWT' -H 'cookie: \
session_id=MY_SESSION_ID'
    ```
    """
    expired_resources = demo.get_expired_demo_resources()
    removed_resources = []
    failed_removals = []
    for expired_info_item in expired_resources:
        resource_id = expired_info_item.resource.id
        try:
            if demo.remove_expired_demo_resource(resource_id):
                removed_resources.append(resource_id)
        except Exception:
            failed_removals.append(resource_id)
            logger.exception("Failed to remove expired demo resource '%s'.", resource_id)

    return utils.response(
        return_code=return_codes.REMOVED_RESOURCES,
        removed_resources=removed_resources,
        failed_removals=failed_removals,
    )
