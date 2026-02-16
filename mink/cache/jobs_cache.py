"""Cache helpers for registry and job queue."""

from mink.cache.memcached import cache, cache_namespace


# ------------------------------------------------------------------------------
# Cache keys
# ------------------------------------------------------------------------------
def _key_queue_initialized() -> str:
    return cache_namespace("queue_initialized")


def _key_job_queue() -> str:
    return cache_namespace("job_queue")


def _key_all_resources() -> str:
    return cache_namespace("all_resources")


def _key_job(job_id: str) -> str:
    return cache_namespace(f"job:{job_id}")


# ------------------------------------------------------------------------------
# Getter, setters and removers for cache values
# ------------------------------------------------------------------------------
def get_queue_initialized() -> bool:
    """Get bool value for 'queue_initialized' from the cache (stating whether the queue is initialized)."""
    with cache.get_client() as client:
        return bool(client.get(_key_queue_initialized()))


def set_queue_initialized(is_initialized: bool) -> None:
    """Set 'queue_initialized' to bool 'is_initialized' in the cache."""
    with cache.get_client() as client:
        client.set(_key_queue_initialized(), bool(is_initialized))


def get_job_queue() -> list:
    """Get entire job queue (list of resource IDs of all active jobs) from the cache."""
    with cache.get_client() as client:
        return client.get(_key_job_queue()) or []


def set_job_queue(value: list) -> None:
    """Set job queue (list of resource IDs of all active jobs) in the cache."""
    with cache.get_client() as client:
        client.set(_key_job_queue(), value)


def get_all_resources() -> list:
    """Get list of all jobs (resource IDs) from the cache."""
    with cache.get_client() as client:
        return client.get(_key_all_resources()) or []


def set_all_resources(value: list) -> None:
    """Set list of all jobs (resource IDs)in the cache."""
    with cache.get_client() as client:
        client.set(_key_all_resources(), list(set(value)))


def get_job(job: str) -> str:
    """Get 'job' (resource ID) from the cache and return it.

    Args:
        job: The resource ID for the job.

    Returns:
        The job as a serialized dictionary.
    """
    with cache.get_client() as client:
        return client.get(_key_job(job)) or "null"


def set_job(job: str, value: str) -> None:
    """Set 'job' to 'value' in the cache.

    Args:
        job: The resource ID for the job.
        value: The job as a serialized dictionary.
    """
    with cache.get_client() as client:
        client.set(_key_job(job), value)


def remove_job(job: str) -> None:
    """Remove 'job' from the cache.

    Args:
        job: The resource ID for the job.
    """
    with cache.get_client() as client:
        client.delete(_key_job(job))
