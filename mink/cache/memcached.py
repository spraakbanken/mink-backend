"""Memcached client management."""

from collections.abc import Generator
from contextlib import contextmanager

from pymemcache import serde
from pymemcache.client.base import Client


class CacheManager:
    """Manages the cache client instance."""

    def __init__(self) -> None:
        """Initialize the CacheManager without a connecting."""
        self.server = None

    def initialize(self, cache_server: str) -> None:
        """Initialize the cache client."""
        from mink.core import exceptions  # noqa: PLC0415
        from mink.core.logging import logger  # noqa: PLC0415

        self.server = cache_server

        try:
            with self.get_client() as cache_client:
                cache_client.get("test_connection")
            logger.info("Connected to memcached on %s", cache_server)
        except Exception as e:
            raise exceptions.CacheConnectionError(self.server, e) from e

    @contextmanager
    def get_client(self) -> Generator[Client, None, None]:
        """Retrieve a connected Memcached client."""
        client = Client(self.server, serde=serde.pickle_serde)
        try:
            yield client
        finally:
            client.close()


cache = CacheManager()
