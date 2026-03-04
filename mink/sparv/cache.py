"""Cache helpers for Sparv schema."""

from mink.cache.memcached import cache, cache_namespace
from mink.sparv.config import sparv_settings


# ------------------------------------------------------------------------------
# Cache keys
# ------------------------------------------------------------------------------
def _key_sparv_schema() -> str:
    """Return the cache key for the Sparv schema."""
    return cache_namespace("sparv_schema")


def _key_sparv_languages() -> str:
    """Return the cache key for the Sparv languages."""
    return cache_namespace("sparv_languages")


def _key_sparv_exports() -> str:
    """Return the cache key for the Sparv exports."""
    return cache_namespace("sparv_exports")


# ------------------------------------------------------------------------------
# Getter, setters and removers for cache values
# ------------------------------------------------------------------------------
def set_sparv_schema(schema: dict) -> None:
    """Store Sparv schema in cache."""
    with cache.get_client() as client:
        client.set(_key_sparv_schema(), schema, expire=sparv_settings.SPARV_CACHE_LIFETIME)


def get_sparv_schema() -> dict | None:
    """Return cached Sparv schema as a dictionary, or None if not found."""
    with cache.get_client() as client:
        return client.get(_key_sparv_schema())


def set_sparv_languages(languages: list) -> None:
    """Store Sparv languages in cache."""
    with cache.get_client() as client:
        client.set(_key_sparv_languages(), languages, expire=sparv_settings.SPARV_CACHE_LIFETIME)


def get_sparv_languages() -> list | None:
    """Return cached Sparv languages info as a list, or None if not found."""
    with cache.get_client() as client:
        return client.get(_key_sparv_languages())


def set_sparv_exports(exports: list) -> None:
    """Store Sparv exports in cache."""
    with cache.get_client() as client:
        client.set(_key_sparv_exports(), exports, expire=sparv_settings.SPARV_CACHE_LIFETIME)


def get_sparv_exports() -> list | None:
    """Return cached Sparv exports as a list, or None if not found."""
    with cache.get_client() as client:
        return client.get(_key_sparv_exports())
