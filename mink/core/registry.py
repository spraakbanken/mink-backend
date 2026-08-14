"""Utilities related to the resource registry and job queue.

The registry and job queue live in the cache and also on the local file system (as backup).
"""

import json
from collections.abc import Callable
from functools import wraps
from pathlib import Path

from mink.cache import jobs_cache
from mink.core import exceptions, info, jobs, utils
from mink.core.config import settings
from mink.core.logging import logger

_INITIALIZING_STATE = {"in_progress": False}


def initialize_if_needed() -> None:
    """Initialize the registry if the cache was cleared."""
    if _INITIALIZING_STATE["in_progress"]:
        return
    if not jobs_cache.get_queue_initialized():
        _INITIALIZING_STATE["in_progress"] = True
        try:
            initialize()
        except Exception:
            logger.exception("Failed to initialize registry")
            raise
        finally:
            _INITIALIZING_STATE["in_progress"] = False


def ensure_initialized(func: Callable) -> Callable:
    """Ensure the registry is initialized before calling a function."""

    @wraps(func)
    def wrapper(*args, **kwargs):  # ruff: ignore[missing-return-type-private-function, missing-type-args, missing-type-kwargs]
        initialize_if_needed()
        return func(*args, **kwargs)

    return wrapper


def initialize() -> None:
    """Initialize the registry and job queue from the filesystem."""
    logger.info("Initializing queue")
    all_resources = []  # Storage for all resource IDs
    registry_dir = Path(settings.INSTANCE_PATH) / settings.REGISTRY_DIR
    registry_dir.mkdir(exist_ok=True)

    # Load queue priorities
    queue_file = registry_dir / settings.QUEUE_FILE
    if queue_file.is_file():
        with queue_file.open() as p:
            jsonstr = p.read()
            queue = json.loads(jsonstr) or []
    else:
        queue = []
    jobs_cache.set_queue_initialized(True)

    # Load info instances into memory, append to queue if necessary
    for f in sorted(registry_dir.glob("*/*"), key=lambda x: x.stat().st_mtime):
        if f == queue_file:
            continue
        if f.is_file():
            with f.open() as fobj:
                infoobj = info.load_from_str(fobj.read())
                infoobj.update()  # Update resource in file system and add to cache
                all_resources.append(infoobj.id)
                logger.debug("Job '%s' in cache: '%s...'", f.name, str(jobs_cache.get_job(infoobj.id))[:50])
            # Queue job unless it is done, aborted or erroneous
            if infoobj.id not in queue and (
                not (infoobj.job.status.is_done(infoobj.job.current_process) or infoobj.job.status.is_inactive())
            ):
                queue.append(infoobj.job.id)
    jobs_cache.set_job_queue(queue)
    jobs_cache.set_all_resources(all_resources)
    logger.info("Queue in cache: %s", jobs_cache.get_job_queue())
    # logger.debug("All jobs in cache: %s", jobs_cache.get_all_resources())
    logger.info("Total resources in cache: %d", len(jobs_cache.get_all_resources()))


@ensure_initialized
def get(resource_id: str) -> info.Info:
    """Get an existing info instance from the cache.

    Args:
        resource_id: The ID of the resource to retrieve.

    Returns:
        An Info instance corresponding to the resource ID.

    Raises:
        exceptions.JobNotFoundError: If no resource is found with the given ID.
    """
    info_obj = jobs_cache.get_job(resource_id)
    logger.debug("Info object from cache: %s", info_obj)
    if info_obj == "null":
        raise exceptions.JobNotFoundError(resource_id)
    return info.load_from_str(info_obj)


@ensure_initialized
def filter_resources(resource_ids: list[str] | None = None) -> list[info.Info]:
    """Get info for all resources listed in 'resource_ids'.

    Args:
        resource_ids: A list of resource IDs to filter by.

    Returns:
        A list of Info instances for the filtered resources.
    """
    filtered_resources = []
    all_resources = jobs_cache.get_all_resources()
    for res_id in all_resources:
        if resource_ids is not None and res_id not in resource_ids:
            continue
        infoobj = info.load_from_str(jobs_cache.get_job(res_id))
        filtered_resources.append(infoobj)
    return filtered_resources


@ensure_initialized
def add_to_queue(job: jobs.BaseJob) -> jobs.BaseJob:
    """Add a job item to the queue.

    Args:
        job: The job to add to the queue.

    Returns:
        The job that was added to the queue.

    Raises:
        exceptions.ProcessStillRunningError: If there is an unfinished job for the resource.
    """
    queue = jobs_cache.get_job_queue()
    # Avoid starting multiple jobs for the same resource simultaneously
    if job.id in queue and job.status.is_active():
        raise exceptions.ProcessStillRunningError
    # Unqueue if old job is queued since before
    if job.id in queue:
        queue.pop(queue.index(job.id))
    # Add job to queue and save priority
    queue.append(job.id)
    jobs_cache.set_job_queue(queue)
    save_priorities()
    # Reset time stamps for the job
    job.reset_time()
    job.set_attribute("queued", utils.get_current_time())
    return job


@ensure_initialized
def pop_from_queue(job: jobs.BaseJob) -> None:
    """Remove job item from queue (but keep in all jobs), e.g. when a job is aborted.

    Args:
        job: The job to remove from the queue.
    """
    queue = jobs_cache.get_job_queue()
    if job.id in queue:
        queue.pop(queue.index(job.id))
        jobs_cache.set_job_queue(queue)
        save_priorities()


@ensure_initialized
def get_priority(job: jobs.BaseJob) -> int:
    """Get the queue priority of the job.

    Args:
        job: The job to get the priority for.

    Returns:
        The priority of the job in the queue.
    """
    _, waiting_jobs = get_running_waiting()
    waiting_jobs = [j.id for j in waiting_jobs]
    try:
        return waiting_jobs.index(job.id) + 1
    except ValueError:
        return -1


@ensure_initialized
def save_priorities() -> None:
    """Save queue order so it can be loaded from disk upon app restart."""
    registry_dir = Path(settings.INSTANCE_PATH) / settings.REGISTRY_DIR
    registry_dir.mkdir(exist_ok=True)
    queue = jobs_cache.get_job_queue()
    queue_file = registry_dir / settings.QUEUE_FILE
    with queue_file.open("w") as f:
        f.write(json.dumps(queue))


@ensure_initialized
def get_running_waiting() -> tuple[list[jobs.BaseJob], list[jobs.BaseJob]]:
    """Get the running and waiting jobs from the queue.

    Returns:
        A tuple containing two lists: running jobs and waiting jobs.
    """
    running_jobs = []
    waiting_jobs = []

    queue = jobs_cache.get_job_queue()
    # queue is None before it is done initializing
    if queue is not None:
        for res_id in queue:
            job = info.load_from_str(jobs_cache.get_job(res_id)).job
            if job.status.is_running():
                running_jobs.append(job)
            elif job.status.is_waiting():
                waiting_jobs.append(job)

    return running_jobs, waiting_jobs


@ensure_initialized
def unqueue_inactive() -> None:
    """Unqueue jobs that are done, aborted or erroneous."""
    queue = jobs_cache.get_job_queue()
    old_jobs = []
    for res_id in queue:
        job = info.load_from_str(jobs_cache.get_job(res_id)).job
        if job.status.is_inactive():
            old_jobs.append(res_id)

    if old_jobs:
        for res_id in old_jobs:
            logger.info("Removing job %s", res_id)
            queue.pop(queue.index(res_id))
        jobs_cache.set_job_queue(queue)
        save_priorities()
