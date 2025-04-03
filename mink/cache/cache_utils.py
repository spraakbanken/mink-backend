"""Caching utilities for the application.

The cache connection is created upon application startup.

The cache client (get_cache_client, e.g. a pymemcache instance) is expected to support the following methods:
    - get(key: str) -> Any: Get value for key from cache.
    - set(key: str, value: Any, expire: int) -> None: Set value for key in cache.
    - delete(key: str) -> None: Delete key from cache.

Keys in cache related to the job queue:
    - queue_initialized: bool indicating whether the queue is initialized
    - job_queue : list of IDs of all active jobs
    - all_resources: list of all resource IDs
    - resource_dict: dict containing all resource info objects
"""

from datetime import datetime, timedelta
from typing import Any

from mink.cache.cache import get_cache_client
from mink.config import settings
from mink.core import registry


def get_queue_initialized() -> bool:
    """Get bool value for 'queue_initialized' from the cache.

    Returns:
        True if the queue is initialized, False otherwise.
    """
    return get_cache_client().get("queue_initialized")


def set_queue_initialized(is_initialized: bool) -> None:
    """Set 'queue_initialized' to bool 'is_initialized' in the cache.

    Args:
        is_initialized: Whether the queue is initialized.
    """
    get_cache_client().set("queue_initialized", bool(is_initialized))


def get_job_queue() -> list:
    """Get entire job queue from the cache.

    Returns:
        The job queue as a list.
    """
    registry.initialize()
    return get_cache_client().get("job_queue")


def set_job_queue(value: list) -> None:
    """Set job queue in the cache.

    Args:
        value: The job queue as a list.
    """
    get_cache_client().set("job_queue", value)


def get_all_resources() -> list:
    """Get list of all jobs from the cache.

    Returns:
        A list of all resource IDs.
    """
    registry.initialize()
    return get_cache_client().get("all_resources")


def set_all_resources(value: list) -> None:
    """Set list of all jobs in the cache.

    Args:
        value: A list of all resource IDs.
    """
    get_cache_client().set("all_resources", list(set(value)))


def get_job(job: str) -> dict:
    """Get 'job' from the cache and return it.

    Args:
        job: The job ID.

    Returns:
        The job as a dictionary.
    """
    registry.initialize()
    return get_cache_client().get(job)


def set_job(job: str, value: dict) -> None:
    """Set 'job' to 'value' in the cache.

    Args:
        job: The job ID.
        value: The job as a dictionary.
    """
    registry.initialize()
    get_cache_client().set(job, value)


def remove_job(job: str) -> None:
    """Remove 'job' from the cache.

    Args:
        job: The job ID.
    """
    registry.initialize()
    get_cache_client().delete(job)


def get_apikey_data(apikey: str) -> dict | None:
    """Get cached API key data, if recent enough.

    Args:
        apikey: The API key.

    Returns:
        The API key data as a dictionary, or None if not found or expired.
    """
    item = get_cache_client().get(f"apikey_data_{apikey}")
    if not item:
        return None

    timestamp, data = item

    # Delete if expired
    lifetime = settings.SBAUTH_CACHE_LIFETIME
    if timestamp + timedelta(seconds=lifetime) < datetime.now():
        remove_apikey_data(apikey)
        return None

    return data


def set_apikey_data(apikey: str, data: dict) -> None:
    """Store API key data in cache.

    Args:
        apikey: The API key.
        data: The API key data as a dictionary.
    """
    item = (datetime.now(), data)
    if get_cache_client is not None:
        get_cache_client().set(f"apikey_data_{apikey}", item)


def remove_apikey_data(apikey: str) -> None:
    """Remove API key data from cache.

    Args:
        apikey: The API key.
    """
    get_cache_client().delete(f"apikey_data_{apikey}")


def get_cookie_data(cookie: str, default: Any = None) -> dict | None:
    """Get cached cookie data, if recent enough.

    Args:
        cookie: The cookie (user session ID).
        default: Default value to return if the cookie data is not found or expired.

    Returns:
        The cookie data as a dictionary, or None if not found or expired.
    """
    return get_cache_client().get(f"cookie_data_{cookie}") or default


def set_cookie_data(cookie: str, data: dict) -> None:
    """Store cookie (user session ID) data in cache.

    Args:
        cookie: The cookie.
        data: The cookie data as a dictionary.
    """
    get_cache_client().set(f"cookie_data_{cookie}", data, expire=settings.ADMIN_MODE_LIFETIME)


def remove_cookie_data(cookie: str) -> None:
    """Remove cookie data from cache.

    Args:
        cookie: The cookie (user session ID).
    """
    get_cache_client().delete(f"cookie_data_{cookie}")
