"""Caching utilities for the application.

The cache connection is created upon application startup.

The cache client (e.g. a pymemcache instance) is expected to support the following methods:
    - get(key: str) -> Any: Get value for key from cache.
    - set(key: str, value: Any, expire: int) -> None: Set value for key in cache.
    - delete(key: str) -> None: Delete key from cache.

Keys in cache related to the job queue:
    - queue_initialized: bool indicating whether the queue is initialized
    - job_queue : list of IDs of all active jobs
    - all_resources: list of all resource IDs
    - resource_dict: dict containing all resource info objects
"""

from typing import Any

from mink.cache.memcached import cache
from mink.core import registry
from mink.core.config import settings


def get_queue_initialized() -> bool:
    """Get bool value for 'queue_initialized' from the cache.

    Returns:
        True if the queue is initialized, False otherwise.
    """
    with cache.get_client() as client:
        return client.get("queue_initialized")


def set_queue_initialized(is_initialized: bool) -> None:
    """Set 'queue_initialized' to bool 'is_initialized' in the cache.

    Args:
        is_initialized: Whether the queue is initialized.
    """
    with cache.get_client() as client:
        client.set("queue_initialized", bool(is_initialized))


def get_job_queue() -> list:
    """Get entire job queue from the cache.

    Returns:
        The job queue as a list.
    """
    registry.initialize()
    with cache.get_client() as client:
        return client.get("job_queue")


def set_job_queue(value: list) -> None:
    """Set job queue in the cache.

    Args:
        value: The job queue as a list.
    """
    with cache.get_client() as client:
        client.set("job_queue", value)


def get_all_resources() -> list:
    """Get list of all jobs from the cache.

    Returns:
        A list of all resource IDs.
    """
    registry.initialize()
    with cache.get_client() as client:
        return client.get("all_resources")


def set_all_resources(value: list) -> None:
    """Set list of all jobs in the cache.

    Args:
        value: A list of all resource IDs.
    """
    with cache.get_client() as client:
        client.set("all_resources", list(set(value)))


def get_job(job: str) -> str:
    """Get 'job' from the cache and return it.

    Args:
        job: The job ID.

    Returns:
        The job as a serialized dictionary.
    """
    registry.initialize()
    with cache.get_client() as client:
        return client.get(job)


def set_job(job: str, value: str) -> None:
    """Set 'job' to 'value' in the cache.

    Args:
        job: The job ID.
        value: The job as a serialized dictionary.
    """
    registry.initialize()
    with cache.get_client() as client:
        client.set(job, value)


def remove_job(job: str) -> None:
    """Remove 'job' from the cache.

    Args:
        job: The job ID.
    """
    registry.initialize()
    with cache.get_client() as client:
        client.delete(job)


def get_apikey_data(apikey: str, default: Any = None) -> dict | None:
    """Get cached API key data, if recent enough.

    Args:
        apikey: The API key.
        default: Default value to return if the API key data is not found or expired.

    Returns:
        The API key data as a dictionary, or None if not found or expired.
    """
    with cache.get_client() as client:
        return client.get(f"apikey_data_{apikey}") or default


def set_apikey_data(apikey: str, data: dict) -> None:
    """Store API key data in cache.

    Args:
        apikey: The API key.
        data: The API key data as a dictionary.
    """
    with cache.get_client() as client:
        client.set(f"apikey_data_{apikey}", data, expire=settings.SBAUTH_CACHE_LIFETIME)


def remove_apikey_data(apikey: str) -> None:
    """Remove API key data from cache.

    Args:
        apikey: The API key.
    """
    with cache.get_client() as client:
        client.delete(f"apikey_data_{apikey}")


def get_cookie_data(cookie: str | None, default: Any = None) -> Any:
    """Get cached cookie data, if recent enough.

    Args:
        cookie: The cookie (user session ID).
        default: Default value to return if the cookie data is not found or expired.

    Returns:
        The cookie data as a dictionary, or None if not found or expired.
    """
    if cookie is None:
        return default
    with cache.get_client() as client:
        return client.get(f"cookie_data_{cookie}") or default


def set_cookie_data(cookie: str, data: dict) -> None:
    """Store cookie (user session ID) data in cache.

    Args:
        cookie: The cookie.
        data: The cookie data as a dictionary.
    """
    with cache.get_client() as client:
        client.set(f"cookie_data_{cookie}", data, expire=settings.ADMIN_MODE_LIFETIME)


def remove_cookie_data(cookie: str) -> None:
    """Remove cookie data from cache.

    Args:
        cookie: The cookie (user session ID).
    """
    with cache.get_client() as client:
        client.delete(f"cookie_data_{cookie}")
