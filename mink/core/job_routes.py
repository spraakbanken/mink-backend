"""Routes related to jobs status and information."""

from datetime import datetime

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


@router.get(
    "/queue/health",
    operation_id="queue-health",
    tags=["Manage Resources"],
    response_model=models.QueueHealthResponse,
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
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": models.QueueHealthResponse,
            "content": {
                "application/json": {
                    "example": models.QueueHealthResponse.model_config["json_schema_extra"]["examples"][1]
                }
            },
        },
    },
)
async def queue_health(_access: dict = Depends(login.secret_key_or_admin_mode)) -> JSONResponse:
    """Return monitorable queue health statistics for internal checks and for admins.

    ### Example

    ```bash
    curl -X GET '{{host}}/queue/health' -H 'Authorization: Bearer YOUR_JWT' -H 'cookie: session_id=MY_SESSION_ID'
    ```
    """
    warning_threshold_seconds = settings.QUEUE_HEALTH_WARNING_SECONDS
    queue_jobs = []
    last_started: str | None = None
    seconds_since_last_start: int | None = None
    oldest_running_started: str | None = None
    oldest_running_seconds = 0
    oldest_waiting_queued: str | None = None
    oldest_waiting_seconds = 0

    # Only active queued jobs should contribute to this health summary.
    running_queue, waiting_queue = registry.get_running_waiting()
    running_jobs = len(running_queue)
    waiting_jobs = len(waiting_queue)

    def seconds_since(timestamp: str) -> int | None:
        """Return elapsed seconds since an ISO timestamp, or None if unavailable."""
        if not timestamp:
            return None
        try:
            parsed = datetime.fromisoformat(timestamp)
        except ValueError:
            logger.warning("Invalid timestamp in queue health data: %s", timestamp)
            return None
        return max(int((datetime.now().astimezone() - parsed).total_seconds()), 0)

    def add_queue_job(job: BaseJob, current_status: Status) -> None:
        """Calculate relevant time-based statistics for a job and add it to the queue health response."""
        nonlocal \
            last_started, \
            seconds_since_last_start, \
            oldest_running_started, \
            oldest_running_seconds, \
            oldest_waiting_queued, \
            oldest_waiting_seconds

        info_obj = getattr(job, "parent", None)
        if info_obj is None:
            logger.warning("Job '%s' missing parent info, skipping queue health entry", job.id)
            return

        priority = registry.get_priority(job)
        priority = priority if priority != -1 else ""
        queued_seconds = seconds_since(job.queued) or 0
        started_seconds = seconds_since(job.started)

        # Track the most recently started active job
        if started_seconds is not None and (
            seconds_since_last_start is None or started_seconds < seconds_since_last_start
        ):
            last_started = job.started
            seconds_since_last_start = started_seconds

        if current_status == Status.running:
            # Running jobs are aged from process start when available
            age_reference = "started"
            age_seconds = started_seconds or job.duration
            if age_seconds >= oldest_running_seconds:
                oldest_running_started = job.started or None
                oldest_running_seconds = age_seconds
        else:
            # Waiting jobs have not started yet, so queue age is the useful signal.
            age_reference = "queued"
            age_seconds = queued_seconds
            if age_seconds >= oldest_waiting_seconds:
                oldest_waiting_queued = job.queued or None
                oldest_waiting_seconds = age_seconds

        queue_jobs.append(
            {
                "resource_id": info_obj.id,
                "resource_type": info_obj.resource.type.value,
                "current_process": job.current_process,
                "job_status": current_status.name,
                "priority": priority,
                "queued": job.queued,
                "started": job.started,
                "age_reference": age_reference,
                "age_seconds": age_seconds,
            }
        )

    for job in running_queue:
        add_queue_job(job, Status.running)
    for job in waiting_queue:
        add_queue_job(job, Status.waiting)

    # Report degraded health when either the oldest running job or the oldest
    # queued job exceeds the configured threshold
    warnings = []
    if oldest_running_seconds >= warning_threshold_seconds:
        warnings.append(f"Oldest running job has been active for {oldest_running_seconds} seconds")
    if oldest_waiting_seconds >= warning_threshold_seconds:
        warnings.append(f"Oldest waiting job has been queued for {oldest_waiting_seconds} seconds")

    healthy = not warnings
    return utils.response(
        return_code=return_codes.QUEUE_HEALTHY if healthy else return_codes.QUEUE_DEGRADED,
        info="Queue health summary",
        warnings=warnings or None,
        healthy=healthy,
        warning_threshold_seconds=warning_threshold_seconds,
        queue_size=len(queue_jobs),
        running_jobs=running_jobs,
        waiting_jobs=waiting_jobs,
        max_workers=settings.MAX_WORKERS,
        last_started=last_started,
        seconds_since_last_start=seconds_since_last_start,
        oldest_running_started=oldest_running_started,
        oldest_running_seconds=oldest_running_seconds,
        oldest_waiting_queued=oldest_waiting_queued,
        oldest_waiting_seconds=oldest_waiting_seconds,
        queue_jobs=queue_jobs,
    )


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

    ### Example

    ```bash
    curl -X GET '{{host}}/resource/status/list' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    try:
        # Get all job statuses for this user's resources
        res_list = []
        resource_infos = registry.filter_resources(auth_data["resources"])
        for info_obj in resource_infos:
            resp_dict = route_utils.make_status_response(info_obj, admin=auth_data["admin_mode"])
            res_list.append(resp_dict)
        return utils.response(
            return_code=return_codes.LISTING_CONTENT, info="Listing resource infos", resources=res_list
        )
    except Exception as e:
        raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_LISTING_CONTENT, info=str(e)) from e


@router.get(
    "/resource/status/get/{resource_id}",
    operation_id="get-resource-status",
    tags=["Manage Resources"],
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
    # Check if resource exists
    if resource_id not in auth_data["resources"]:
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
        return_code=return_codes.CHECKED_STATUS, **route_utils.make_status_response(info, admin=auth_data["admin_mode"])
    )
