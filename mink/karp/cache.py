"""Cache helpers for Karp-related data."""

from mink.cache.memcached import cache, cache_namespace
from mink.karp.config import karp_settings


# ------------------------------------------------------------------------------
# Cache keys
# ------------------------------------------------------------------------------
def _key_lexicon_output_contents(resource_id: str) -> str:
    """Return the cache key for a lexicon output file listing."""
    return cache_namespace(f"lexicon_output_contents:{resource_id}")


# ------------------------------------------------------------------------------
# Getter, setters and removers for cache values
# ------------------------------------------------------------------------------
def set_lexicon_output_contents(resource_id: str, contents: list) -> None:
    """Store cached output listing for one lexicon resource."""
    with cache.get_client() as client:
        client.set(
            _key_lexicon_output_contents(resource_id),
            contents,
            expire=karp_settings.KARP_OUTPUT_CONTENTS_CACHE_LIFETIME,
        )


def get_lexicon_output_contents(resource_id: str) -> list | None:
    """Return cached output listing for one lexicon resource, or None if not found."""
    with cache.get_client() as client:
        return client.get(_key_lexicon_output_contents(resource_id))


def remove_lexicon_output_contents(resource_id: str) -> None:
    """Remove cached output listing for one lexicon resource."""
    with cache.get_client() as client:
        client.delete(_key_lexicon_output_contents(resource_id))
