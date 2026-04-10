"""Routes related to jobs status and information."""

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse

from mink.core import exceptions, models, registry, return_codes, route_utils, utils
from mink.core.config import settings
from mink.core.info import Info
from mink.core.jobs import BaseJob
from mink.core.logging import logger
from mink.core.resource_specs import get_spec
from mink.core.status import Status
from mink.sb_auth import login

router = APIRouter()


@router.put(
    "/advance-queue",
    deprecated=True,
    name="advance-queue-deprecated",
    include_in_schema=False,
)
@router.put(
    "/queue/advance",
    operation_id="advance-queue",
    tags=["Manage Resources"],
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

    def mark_stale_active_processes(job: BaseJob, info_obj: Info, active_processes: list[str], reason: str) -> None:
        """Mark stale active process states as error and unqueue the job."""
        if active_processes:
            logger.warning(
                "Marking stale active processes as error for job '%s' (%s): %s",
                job.id,
                reason,
                active_processes,
            )
        for name in active_processes:
            job.status[name] = Status.error
        info_obj.update()
        registry.pop_from_queue(job)

    def has_consistent_active_process(job: BaseJob, info_obj: Info, expected_status: Status, reason: str) -> bool:
        """Validate active process invariants; mark stale state as error if invalid."""
        active_processes = [name for name, state in job.status.items() if state in {Status.waiting, Status.running}]
        process_name = job.current_process

        # Must have exactly one active process and it must match current_process.
        if len(active_processes) != 1 or process_name != active_processes[0]:
            mark_stale_active_processes(job, info_obj, active_processes, reason=reason)
            return False

        # Must also match the expected active status for this queue phase.
        if expected_status == Status.running:
            is_expected_active = job.status.is_running(process_name)
        elif expected_status == Status.waiting:
            is_expected_active = job.status.is_waiting(process_name)
        else:
            raise ValueError(f"Unsupported expected_status '{expected_status}' in queue consistency check")
        if not is_expected_active:
            mark_stale_active_processes(job, info_obj, active_processes, reason=reason)
            return False

        return True

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
            if not has_consistent_active_process(job, info_obj, Status.running, reason="inconsistent running state"):
                continue
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
        for job in list(waiting_jobs):
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

            if not has_consistent_active_process(job, info_obj, Status.waiting, reason="inconsistent waiting state"):
                if job in waiting_jobs:
                    waiting_jobs.remove(job)
                continue

            # Skip if there is no queue handler for the current process
            process_name = job.current_process or ""
            handler = spec.queue_handlers.get(process_name)
            if handler is None:
                logger.warning("No queue handler for process '%s' (job '%s')", process_name, job.id)
                continue

            if job in waiting_jobs:
                waiting_jobs.remove(job)
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
    tags=["Manage Corpora"],
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
    "/resource/list",
    operation_id="list-resources",
    tags=["Manage Resources"],
    response_model=models.ListResourcesResponse,
    responses={**models.common_auth_error_responses},
)
async def list_resources(auth_data: dict = Depends(login.AuthDependencyNoResourceId())) -> JSONResponse:
    """List all resources available to the authenticated user, regardless of resource type.

    ### Example

    ```bash
    curl -X GET '{{host}}/resource/list' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    return utils.response(
        return_code=return_codes.LISTING_CONTENT,
        info="Listing available resources",
        resources=auth_data["resources"],
    )


@router.get(
    "/resource/status/list",
    operation_id="list-resource-statuses",
    tags=["Manage Resources"],
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
    operation_id="get-resource-status",
    tags=["Manage Resources", "Manage Corpora"],
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
