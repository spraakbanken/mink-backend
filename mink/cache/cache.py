"""Cache client management."""

from pymemcache import serde
from pymemcache.client.base import Client

_cache_client = None


def initialize_cache(cache_host: str) -> None:
    """Initialize the cache client.

    Args:
        cache_host: The cache server host.
    """
    global _cache_client
    _cache_client = Client(cache_host, serde=serde.pickle_serde)


def get_cache_client() -> Client:
    """Retrieve the cache client.

    Returns:
        The cache client instance.
    """
    if _cache_client is None:
        raise RuntimeError("Cache client is not initialized.")
    return _cache_client
