"""Cache helpers for Sparv schema."""

from mink.cache.memcached import cache, cache_namespace
from mink.sparv.config import sparv_settings


# ------------------------------------------------------------------------------
# Cache keys
# ------------------------------------------------------------------------------
def _key_sparv_schema() -> str:
    """Return the cache key for the Sparv schema."""
    return cache_namespace("sparv_schema")


# ------------------------------------------------------------------------------
# Getter, setters and removers for cache values
# ------------------------------------------------------------------------------
def set_sparv_schema(schema: dict) -> None:
    """Store Sparv schema in cache.

    Args:
        schema: The Sparv schema as a dictionary.
    """
    with cache.get_client() as client:
        client.set(_key_sparv_schema(), schema, expire=sparv_settings.SPARV_SCHEMA_CACHE_LIFETIME)


def get_sparv_schema() -> dict | None:
    """Get cached Sparv schema.

    Returns:
        The Sparv schema as a dictionary, or None if not found.
    """
    with cache.get_client() as client:
        return client.get(_key_sparv_schema())
