"""Cache helpers for SB Auth."""

from typing import Any

from mink.cache.memcached import cache, cache_namespace
from mink.core.config import settings


# ------------------------------------------------------------------------------
# Cache keys
# ------------------------------------------------------------------------------
def _key_apikey(apikey: str) -> str:
    """Return the cache key for an API key."""
    return cache_namespace(f"apikey:{apikey}")


def _key_cookie(cookie: str) -> str:
    """Return the cache key for a cookie (user session ID)."""
    return cache_namespace(f"cookie:{cookie}")


# ------------------------------------------------------------------------------
# Getter, setters and removers for cache values
# ------------------------------------------------------------------------------
def get_apikey_data(apikey: str, default: Any = None) -> dict | None:
    """Get cached API key data, if recent enough.

    Args:
        apikey: The API key.
        default: Default value to return if the API key data is not found or expired.

    Returns:
        The API key data as a dictionary, or None if not found or expired.
    """
    with cache.get_client() as client:
        return client.get(_key_apikey(apikey)) or default


def set_apikey_data(apikey: str, data: dict) -> None:
    """Store API key data in cache.

    Args:
        apikey: The API key.
        data: The API key data as a dictionary.
    """
    with cache.get_client() as client:
        client.set(_key_apikey(apikey), data, expire=settings.SBAUTH_CACHE_LIFETIME)


def remove_apikey_data(apikey: str) -> None:
    """Remove API key data from cache.

    Args:
        apikey: The API key.
    """
    with cache.get_client() as client:
        client.delete(_key_apikey(apikey))


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
        return client.get(_key_cookie(cookie)) or default


def set_cookie_data(cookie: str, data: dict) -> None:
    """Store cookie (user session ID) data in cache.

    Args:
        cookie: The cookie.
        data: The cookie data as a dictionary.
    """
    with cache.get_client() as client:
        client.set(_key_cookie(cookie), data, expire=settings.ADMIN_MODE_LIFETIME)


def remove_cookie_data(cookie: str) -> None:
    """Remove cookie data from cache.

    Args:
        cookie: The cookie (user session ID).
    """
    with cache.get_client() as client:
        client.delete(_key_cookie(cookie))
