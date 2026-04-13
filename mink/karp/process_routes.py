"""Routes related to processing lexicons with Karp Pipeline."""

import time
from typing import cast

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from mink.core import exceptions, models, registry, return_codes, route_utils, utils
from mink.core.logging import logger
from mink.core.resource_specs import get_spec
from mink.core.status import Status
from mink.karp.jobs import KarpJob
from mink.karp.spec import LEXICON, ProcessName
from mink.karp.storage import storage
from mink.sb_auth import login

router = APIRouter(tags=["Manage Lexicons"], prefix="/lexicon")
SBAUTH_LEXICON = get_spec(LEXICON).sbauth_resource_type
AUTH_LEXICON_WRITE = login.AuthDependency(min_level="WRITE", sbauth_resource_type=SBAUTH_LEXICON)


def _require_job(job: object) -> KarpJob:
    """Ensure that 'job' is a Karp job, raise an error if not."""
    if not isinstance(job, KarpJob):
        raise exceptions.MinkHTTPException(
            return_code=return_codes.INVALID_RESOURCE_TYPE, info="Expected a lexicon resource"
        )
    return cast(KarpJob, job)


@router.put(
    "/job/run/{resource_id}",
    operation_id="run-lexicon-job",
    response_model=models.StatusResponse,
    responses={
        **models.common_auth_error_responses,
        status.HTTP_400_BAD_REQUEST: {
            "model": models.BaseErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.INVALID_CONFIG.message,
                        "return_code": return_codes.INVALID_CONFIG.code,
                        "info": "The importer in your config file is incompatible with your source files",
                        "current_importer": "text_import",
                        "expected_importer": "xml_import",
                    }
                }
            },
        },
        status.HTTP_404_NOT_FOUND: {
            "model": models.ErrorResponse404File,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.FILE_NOT_FOUND.message,
                        "return_code": return_codes.FILE_NOT_FOUND.code,
                        "info": "No source files found for this resource"
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
                        "message": return_codes.FAILED_QUEUING.message,
                        "return_code": return_codes.FAILED_QUEUING.code,
                        "info": "BaseException",
                    }
                }
            },
        },
    },
)
async def run_karp_pipeline(
    auth_data: dict = Depends(AUTH_LEXICON_WRITE),
) -> JSONResponse:
    """Add a Karp Pipeline job to the queue.

    There can only be one active job ('run' or 'install') for each resource at a time. A job must finish or be
    aborted before a new one can be started.

    ### Example

    ```bash
    curl -X PUT '{{host}}/lexicon/job/run/<resource_id>' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    resource_id = auth_data["resource_id"]

    # Get info item, check for changes and remove exports if necessary
    source_changed = config_changed = False
    try:
        info_item = route_utils.get_info_from_auth(auth_data)
        source_changed, config_changed = storage.get_file_changes(resource_id, info_item)
    except exceptions.JobNotFoundError:
        pass
    except Exception as e:
        raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_RUNNING, info=str(e)) from e
    if source_changed or config_changed:
        try:
            job = _require_job(info_item.job)
            karp_output = job.clean()
            logger.debug(f"Removed outdated Karp output before running Karp Pipeline. Output: {karp_output}")
        except Exception as e:
            raise exceptions.MinkHTTPException(
                return_code=return_codes.FAILED_RUNNING,
                info=f"Failed to remove outdated export files before running Karp Pipeline: {e}",
            ) from e

    # Check that all required files are present
    job = _require_job(info_item.job)
    job.check_requirements()

    # Queue job
    try:
        job = registry.add_to_queue(job)
    except Exception as e:
        raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_QUEUING, info=str(e)) from e

    job.set_status(Status.waiting, ProcessName.karp_pipeline)

    # Wait a few seconds to check whether anything terminated early
    time.sleep(2)
    return utils.response(return_code=return_codes.CHECKED_STATUS, **route_utils.make_status_response(info_item))


@router.post(
    "/job/abort/{resource_id}",
    operation_id="abort-lexicon-job",
    response_model=models.BaseResponse,
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
        **models.common_auth_error_responses,
        status.HTTP_404_NOT_FOUND: {
            "model": models.ErrorResponse404File,
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
async def abort_job(auth_data: dict = Depends(AUTH_LEXICON_WRITE)) -> JSONResponse:
    """Abort the currently running job for the resource.

    If the job is in the queue but not yet running, it will be removed from the queue. If the job is running, it will be
    stopped.

    ### Example

    ```bash
    curl -X POST '{{host}}/lexicon/job/abort/<resource_id>' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    resource_id = auth_data["resource_id"]
    job = _require_job(registry.get(resource_id).job)
    # Waiting
    if job.status.is_waiting():
        try:
            registry.pop_from_queue(job)
            job.set_status(Status.aborted)
            return utils.response(return_code=return_codes.ABORTED_JOB, job_status=job.status.serialize())
        except Exception as e:
            raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_UNQUEUING, info=str(e)) from e
    # No running job
    if not job.status.is_running():
        raise exceptions.MinkHTTPException(return_code=return_codes.NO_RUNNING_JOB)
    # Running job, try to abort
    try:
        job = _require_job(job)
        job.abort()
    except exceptions.ProcessNotRunningError as e:
        raise exceptions.MinkHTTPException(return_code=return_codes.NO_RUNNING_JOB) from e
    except Exception as e:
        raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_ABORTING, info=str(e)) from e
    return utils.response(return_code=return_codes.ABORTED_JOB, job_status=job.status.serialize())


@router.delete(
    "/output/remove/{resource_id}",
    operation_id="remove-lexicon-output",
    response_model=models.BaseResponse,
    responses={
        status.HTTP_200_OK: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": return_codes.REMOVED_CONTENT.message,
                        "return_code": return_codes.REMOVED_CONTENT.code,
                        "info": "Removed output",
                        "karp_output": "Karp Pipeline output removed"
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
                        "info": "Failed to remove output",
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
                        "info": "Cannot remove output while a job is running",
                    }
                }
            },
        },
    },
)
async def remove_output(auth_data: dict = Depends(AUTH_LEXICON_WRITE)) -> JSONResponse:
    """Remove all output files for the resource from the Karp Pipeline server.

    This action cannot be performed while a job is running.

    ### Example

    ```bash
    curl -X DELETE '{{host}}/lexicon/output/remove/<resource_id>' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    resource_id = auth_data["resource_id"]
    # Check if there is an active job
    job = _require_job(registry.get(resource_id).job)
    if job.status.is_running():
        raise exceptions.MinkHTTPException(
            return_code=return_codes.PROCESS_RUNNING, info="Cannot remove output while a job is running"
        )

    try:
        karp_output = job.clean()
        return utils.response(
            return_code=return_codes.REMOVED_CONTENT, info="Removed output", karp_output=karp_output
        )
    except Exception as e:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.FAILED_REMOVING_CONTENT, info=f"Failed to remove output: {e}"
        ) from e


@router.put(
    "/karps/install/{resource_id}",
    operation_id="install-karps",
    response_model=models.StatusResponse,
    responses={
        **models.common_auth_error_responses,
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
async def install_karps(auth_data: dict = Depends(AUTH_LEXICON_WRITE)) -> JSONResponse:
    """Install the resource in KarpS.

    ### Example

    ```bash
    curl -X PUT '{{host}}/lexicon/karps/install/<resource_id>' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    resource_id = auth_data["resource_id"]

    # Get info_item, check for changes and remove exports if necessary
    sources_changed = config_changed = False
    try:
        info_item = route_utils.get_info_from_auth(auth_data)
        sources_changed, config_changed = storage.get_file_changes(resource_id, info_item)
    except exceptions.JobNotFoundError:
        pass
    except Exception as e:
        raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_RUNNING, info=str(e)) from e
    if sources_changed or config_changed:
        try:
            job = _require_job(info_item.job)
            success, karp_output = job.clean()
            assert success
        except Exception as e:
            raise exceptions.MinkHTTPException(
                return_code=return_codes.FAILED_RUNNING,
                info=f"Failed to remove outdated export files before running Karp Pipeline: {e}",
                karp_message=karp_output,
            ) from e

    # Queue job
    job = _require_job(info_item.job)
    try:
        job = registry.add_to_queue(job)
    except Exception as e:
        raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_QUEUING, info=str(e)) from e

    job.set_status(Status.waiting, ProcessName.karps)

    # Wait a few seconds to check whether anything terminated early
    time.sleep(2)
    return utils.response(return_code=return_codes.CHECKED_STATUS, **route_utils.make_status_response(info_item))


@router.delete(
    "/karps/uninstall/{resource_id}",
    operation_id="uninstall-karps",
    response_model=models.BaseResponse,
    responses={
        status.HTTP_200_OK: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": return_codes.UNINSTALLED.message,
                        "return_code": return_codes.UNINSTALLED.code,
                        "info": "Uninstalled from KarpS",
                    }
                }
            }
        },
        **models.common_auth_error_responses,
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": models.BaseErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.PROCESS_RUNNING.message,
                        "return_code": return_codes.PROCESS_RUNNING.code,
                        "info": "Cannot uninstall while a job is running",
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
                        "message": return_codes.FAILED_UNINSTALLING.message,
                        "return_code": return_codes.FAILED_UNINSTALLING.code,
                        "info": "Error when uninstalling from KarpS",
                    }
                }
            },
        },
    },
)
async def uninstall_karps(auth_data: dict = Depends(AUTH_LEXICON_WRITE)) -> JSONResponse:
    """Uninstall the lexicon from KarpS.

    ### Example

    ```bash
    curl -X DELETE '{{host}}/lexicon/karps/uninstall/<resource_id>' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    resource_id = auth_data["resource_id"]
    # Check if there is an active job
    job = _require_job(registry.get(resource_id).job)
    if job.status.is_running():
        raise exceptions.MinkHTTPException(
            return_code=return_codes.PROCESS_RUNNING, info="Cannot uninstall while a job is running"
        )

    try:
        job = _require_job(job)
        warnings, output = job.uninstall_karps()
        return utils.response(
            return_code=return_codes.UNINSTALLED, info="Uninstalled from KarpS", output=output, warnings=warnings
        )
    except Exception as e:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.FAILED_UNINSTALLING, info=f"Error when uninstalling from KarpS: {e}"
        ) from e
