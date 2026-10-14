"""Memcached client management."""

import secrets
import time
from collections.abc import Generator
from contextlib import contextmanager

from pymemcache import serde
from pymemcache.client.base import Client

from mink.core.config import settings
from mink.core.logging import logger


class CacheLockTimeoutError(TimeoutError):
    """Raised when a named cache lock cannot be acquired before its deadline."""

    def __init__(self, lock_name: str) -> None:
        """Store the lock name so callers can distinguish nested lock failures."""
        self.lock_name = lock_name
        super().__init__(f"Timed out waiting for lock {lock_name!r}")


def cache_namespace(key: str) -> str:
    """Return a namespaced cache key."""
    return f"{settings.CACHE_NAMESPACE}:{key}"


class CacheManager:
    """Manages the cache client instance."""

    def __init__(self) -> None:
        """Initialize the CacheManager without connecting."""
        self.server = None

    def initialize(self, cache_server: str) -> None:
        """Initialize the cache client."""
        from mink.core import exceptions  # ruff: ignore[import-outside-top-level]

        self.server = cache_server

        try:
            with self.get_client() as cache_client:
                cache_client.get("test_connection")
            logger.info("Connected to memcached on %s", cache_server)
        except Exception as e:
            logger.exception("Failed to connect to memcached on %s: %s", cache_server, e)
            raise exceptions.CacheConnectionError(self.server, e) from e

    @contextmanager
    def get_client(self) -> Generator[Client, None, None]:
        """Retrieve a connected Memcached client."""
        if self.server is None:
            logger.exception("Cache client not initialized. Call 'initialize' first.")
            raise RuntimeError("Cache client not initialized. Call 'initialize' first.")
        # Set default_noreply to False to avoid strange behaviour during registry initialization
        # (e.g. missing resources in cache and queue)
        client = Client(self.server, serde=serde.pickle_serde, default_noreply=False)
        try:
            yield client
        finally:
            client.close()

    @contextmanager
    def lock(self, name: str, *, wait_timeout: float = 10, lease_seconds: int = 300) -> Generator[None, None, None]:
        """Acquire a distributed Memcached lock for the duration of a 'with' block.

        Memcached's 'add' operation ensures that only one caller can create a lock with a particular name. The lock
        expires automatically so that a crashed process cannot leave it locked forever. It protects shared registry
        mutations and is used in demo mode to prevent concurrent identical submissions from creating or queueing the
        same hash-based resource twice.

        Raises:
            CacheLockTimeoutError: If the lock cannot be acquired within 'wait_timeout'.
        """
        key = cache_namespace(f"lock:{name}")
        # Give this lock holder a unique identity
        owner = secrets.token_urlsafe(24)
        deadline = time.monotonic() + wait_timeout

        while True:
            with self.get_client() as client:
                acquired = client.add(key, owner, expire=lease_seconds, noreply=False)
            if acquired:
                break
            if time.monotonic() >= deadline:
                raise CacheLockTimeoutError(name)
            time.sleep(0.05)

        try:
            yield
        finally:
            # Compare ownership before releasing. CAS prevents an expired lock holder from deleting a lock acquired by
            # another request.
            try:
                self._release_lock(key, owner)
            except Exception:
                # Do not hide an exception or successful result from the protected block if Memcached becomes
                # unavailable during release. The lease will eventually expire and make the lock available again.
                logger.exception("Failed to release Memcached lock '%s'; waiting for its lease to expire", name)

    def _release_lock(self, key: str, owner: str) -> None:
        """Release a lock only if it is still owned by the caller."""
        with self.get_client() as client:
            value, cas_token = client.gets(key)

            if value == owner and cas_token is not None:
                releasing = {"owner": owner, "state": "releasing"}
                if client.cas(key, releasing, cas_token, expire=1, noreply=False):
                    client.delete(key, noreply=False)


cache = CacheManager()
