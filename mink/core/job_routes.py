"""Routes related to jobs status and information."""

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse

from mink.core import exceptions, models, registry, route_utils, utils
from mink.core.config import settings
from mink.core.logging import logger
from mink.core.resource_specs import get_spec
from mink.core.status import JobStatuses
from mink.sb_auth import login

router = APIRouter()


@router.put("/advance-queue", tags=["Process Corpus"], response_model=models.BaseResponse, include_in_schema=False)
async def advance_queue(
    secret_key: str = Query(..., alias="secret_key", description="Secret key for authentication"),
) -> JSONResponse:
    """Check the job queue and attempt to advance it.

    1. Unqueue jobs that are done, aborted or erroneous
    2. For running jobs, check if process is still running
    3. Run the next job in the queue if there are fewer running jobs than allowed

    For Mink internal use only!
    """
    if secret_key != settings.MINK_SECRET_KEY:
        raise exceptions.MinkHTTPException(
            status.HTTP_401_UNAUTHORIZED,
            message="Failed to confirm secret key for protected route",
            return_code="failed_confirming_secret_key",
        )

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

    return utils.response(message="Queue advancing completed", return_code="advanced_queue")


@router.get(
    "/resource-info",
    tags=["Process Corpus"],
    response_model=models.StatusResponse | models.StatusesResponse,
    responses={
        **models.common_auth_error_responses,
        status.HTTP_404_NOT_FOUND: {
            "model": models.ErrorResponse404,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": "Resource does not exist or you do not have access to it",
                        "return_code": "resource_not_found",
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
                        "message": "Failed to get job status for resource",
                        "return_code": "failed_getting_job_status",
                        "info": "BaseException",
                    }
                }
            },
        },
    },
)
async def resource_info(
    # Parameter is defined again here to allow for None (since it is optional in this route)
    resource_id: str | None = Query(None, description="Resource ID"),
    auth_data: dict = Depends(login.AuthDependency(require_resource_id=False)),
) -> JSONResponse:
    """Return the status of the current job for a resourace or all resources belonging to the user.

    If the resource ID is provided, the status of the specific resource is returned. Otherwise, the statuses of all
    resources are returned.

    If admin mode is turned on, the owner information is included for each resource.

    ### Example

    ```bash
    curl -X GET '{{host}}/resource-info?resource_id=some_resource_id' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    resource_id = auth_data.get("resource_id")
    resources = auth_data.get("resources", [])
    admin_mode = auth_data.get("admin_mode", False)

    if resource_id:
        # Check if resource exists
        if resource_id not in resources:
            raise exceptions.MinkHTTPException(
                status.HTTP_404_NOT_FOUND,
                message="Resource does not exist or you do not have access to it",
                return_code="resource_not_found",
            )
        try:
            info = registry.get(resource_id)
        except Exception as e:
            raise exceptions.MinkHTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                message="Failed to get job status for resource",
                return_code="failed_getting_job_status",
                info=str(e),
            ) from e
        if not info:
            return utils.response(
                message="There is no active job for this resource",
                return_code="no_active_job",
                job_status=JobStatuses(
                    status=None,
                    processes=list(get_spec(info.resource.type).process_names),
                ).serialize(),
            )
        return utils.response(**route_utils.make_status_response(info, admin=admin_mode))

    try:
        # Get all job statuses for this user's resources
        res_list = []
        resources = registry.filter_resources(resources)
        for res in resources:
            resp_dict = route_utils.make_status_response(res, admin=admin_mode)
            res_list.append(resp_dict)
        return utils.response(message="Listing resource infos", resources=res_list, return_code="listing_jobs")
    except Exception as e:
        raise exceptions.MinkHTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to get job statuses",
            return_code="failed_getting_job_statuses",
            info=str(e),
        ) from e
