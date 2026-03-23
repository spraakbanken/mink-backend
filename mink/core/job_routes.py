"""Routes related to jobs status and information."""

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse

from mink.core import exceptions, models, registry, return_codes, route_utils, utils
from mink.core.config import settings
from mink.core.logging import logger
from mink.core.resource_specs import get_spec
from mink.sb_auth import login

router = APIRouter()


@router.put(
    "/advance-queue",
    tags=["Process Corpus"],
    deprecated=True,
    name="advance-queue-deprecated",
    include_in_schema=False,
)
@router.put(
    "/queue/advance",
    tags=["Process Corpus"],
    response_model=models.BaseResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.INVALID_SECRET_KEY.message,
                        "return_code": return_codes.INVALID_SECRET_KEY.code,
                    }
                }
            }
        },
    },
)
async def advance_queue(
    secret_key: str = Query(..., alias="secret_key", description="Secret key for authentication"),
) -> JSONResponse:
    """Check the job queue and attempt to advance it.

    For Mink internal use only!

    1. Unqueue jobs that are done, aborted or erroneous
    2. For running jobs, check if process is still running
    3. Run the next job in the queue if there are fewer running jobs than allowed
    """
    if secret_key != settings.MINK_SECRET_KEY:
        raise exceptions.MinkHTTPException(return_code=return_codes.INVALID_SECRET_KEY)

    # Unqueue jobs that are done, aborted or erroneous
    registry.unqueue_inactive()

    # For running jobs, check if process is still running
    running_jobs, waiting_jobs = registry.get_running_waiting()
    logger.debug("Running jobs: %d  Waiting jobs: %d", len(running_jobs), len(waiting_jobs))
    for job in running_jobs:
        info_obj = getattr(job, "parent", None)
        if not info_obj:
            logger.warning("Job '%s' missing parent info, skipping running check", job.id)
            continue
        try:
            spec = get_spec(info_obj.resource.type)
            if spec.process_running and not spec.process_running(job):
                try:
                    job.abort()
                except exceptions.ProcessNotRunningError:
                    pass
                registry.pop_from_queue(job)
        except Exception:
            logger.exception("Failed to check if process is running for '%s'", job.id)

    # Get running jobs again in case jobs were unqueued in the previous step
    running_jobs, waiting_jobs = registry.get_running_waiting()

    # Start waiting jobs when global capacity is available
    while waiting_jobs and len(running_jobs) < settings.MAX_WORKERS:
        started_any = False
        for n, job in enumerate(waiting_jobs):
            # Get info object and spec for this job, to check process names and max workers
            info_obj = getattr(job, "parent", None)
            if not info_obj:
                logger.warning("Job '%s' missing parent info, skipping", job.id)
                continue
            try:
                spec = get_spec(info_obj.resource.type)
            except Exception:
                logger.exception("Failed to load spec for job '%s'", job.id)
                continue
            # Skip if job is not waiting
            if not job.status.is_waiting():
                continue

            # Skip if there is no queue handler for the current process
            handler = spec.queue_handlers.get(job.current_process or "")
            if handler is None:
                logger.warning("No queue handler for process '%s' (job '%s')", job.current_process, job.id)
                continue

            waiting_jobs.pop(n)
            try:
                handler(job)
                running_jobs.append(job)
            except Exception:
                logger.exception("Failed to start job '%s'", job.id)
            started_any = True
            break

        if not started_any:
            break

    return utils.response(return_code=return_codes.QUEUE_ADVANCED)


def _resource_status_for_id(resource_id: str, resources: list[str], admin_mode: bool) -> JSONResponse:
    """Get status for one resource."""
    # Check if resource exists
    if resource_id not in resources:
        raise exceptions.MinkHTTPException(return_code=return_codes.RESOURCE_NOT_FOUND)
    try:
        info = registry.get(resource_id)
    except Exception as e:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.FAILED_GETTING_JOB, info=f"Error getting job info for resource: {e}"
        ) from e
    if not info:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.FAILED_GETTING_JOB, info="No job info found for resource"
        )
    return utils.response(
        return_code=return_codes.CHECKED_STATUS, **route_utils.make_status_response(info, admin=admin_mode)
    )


def _resource_status_list(resource_ids: list[str], admin_mode: bool) -> JSONResponse:
    """Get statuses for all available resources."""
    try:
        # Get all job statuses for this user's resources
        res_list = []
        resource_infos = registry.filter_resources(resource_ids)
        for info_obj in resource_infos:
            resp_dict = route_utils.make_status_response(info_obj, admin=admin_mode)
            res_list.append(resp_dict)
        return utils.response(
            return_code=return_codes.LISTING_CONTENT, info="Listing resource infos", resources=res_list
        )
    except Exception as e:
        raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_LISTING_CONTENT, info=str(e)) from e


@router.get(
    "/resource-info",
    tags=["Process Corpus"],
    deprecated=True,
    name="resource-info-deprecated",
    response_model=models.StatusResponse | models.StatusesResponse,
    responses={
        **models.common_auth_error_responses,
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": models.ErrorResponse500,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.FAILED_GETTING_JOB.message,
                        "return_code": return_codes.FAILED_GETTING_JOB.code,
                        "info": "Error getting job info for resource",
                    }
                }
            },
        },
    },
)
async def resource_status_deprecated(
    auth_data: dict = Depends(login.AuthDependency(require_resource_id=False)),
) -> JSONResponse:
    """Return resource status for a specific resource or for all resources available to the authenticated user.

    If admin mode is turned on, the owner information is included for each resource.

    ### Example

    ```bash
    curl -X GET '{{host}}/resource-info' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    resource_id = auth_data["resource_id"]
    resources = auth_data["resources"]
    admin_mode = auth_data["admin_mode"]
    if resource_id:
        return _resource_status_for_id(resource_id, resources, admin_mode)
    return _resource_status_list(resources, admin_mode)


@router.get(
    "/resource/status/list",
    tags=["Process Corpus"],
    response_model=models.StatusesResponse,
    responses={**models.common_auth_error_responses},
)
async def list_resource_statuses(auth_data: dict = Depends(login.AuthDependencyNoResourceId())) -> JSONResponse:
    """Return statuses for all resources available to the authenticated user.

    If admin mode is turned on, the owner information is included for each resource.

    ### Example

    ```bash
    curl -X GET '{{host}}/resource/status/list' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    return _resource_status_list(auth_data["resources"], auth_data["admin_mode"])


@router.get(
    "/resource/status/get/{resource_id}",
    tags=["Process Corpus"],
    response_model=models.StatusResponse,
    responses={
        **models.common_auth_error_responses,
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": models.ErrorResponse500,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.FAILED_GETTING_JOB.message,
                        "return_code": return_codes.FAILED_GETTING_JOB.code,
                        "info": "Error getting job info for resource",
                    }
                }
            },
        },
    },
)
async def get_resource_status(
    resource_id: str,
    auth_data: dict = Depends(login.AuthDependencyNoResourceId()),
) -> JSONResponse:
    """Return the status for one resource.

    ### Example

    ```bash
    curl -X GET '{{host}}/resource/status/get/<resource_id>' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    return _resource_status_for_id(resource_id, auth_data["resources"], auth_data["admin_mode"])
