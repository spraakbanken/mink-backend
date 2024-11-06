"""Caching with Memcached using app context as backoff solution."""

from datetime import datetime, timedelta
from pathlib import Path

from flask import current_app as app
from flask import g
from pymemcache import serde
from pymemcache.client.base import Client

from mink.core import registry


class Cache:
    """Cache class providing caching with Memcached (and app context as backoff)."""

    def __init__(self):
        """
        Init variables in app context (as backup for regular cache) and try to reconnect to cache if necessary.

        This is done before each request (app context g cannot be stored in between requests).
        """
        # Queue
        g.queue_initialized = False
        g.job_queue = []  # List of IDs of all active jobs
        g.all_resources = []  # All resource IDs
        g.resource_dict = {}  # All resource info objects
        g.apikey_data = {} # User/resource data associated with recently submitted API keys

        self.client = None
        self.connect()

    def connect(self):
        """Connect to the memcached socket and set client."""
        socket_path = Path(app.instance_path) / app.config.get("MEMCACHED_SOCKET")
        try:
            self.client = Client(f"unix:{socket_path}", serde=serde.pickle_serde)
            # Check if connection is working
            self.client.get("test")
        except Exception as e:
            app.logger.error("Failed to connect to memcached! %s", str(e))
            self.client = None

    def get_queue_initialized(self):
        """Get bool value for 'queue_initialized' from memcached (or app context)."""
        if self.client is not None:
            return self.client.get("queue_initialized")
        else:
            return g.queue_initialized

    def set_queue_initialized(self, is_initialized):
        """Set 'queue_initialized' to bool 'is_initialized' in memcached (or app context)."""
        if self.client is not None:
            self.client.set("queue_initialized", bool(is_initialized))
        else:
            g.queue_initialized = bool(is_initialized)

    def get_job_queue(self):
        """Get entire job queue from memcached (or app context)."""
        registry.initialize()

        if self.client is not None:
            return self.client.get("job_queue")
        else:
            return g.job_queue

    def set_job_queue(self, value):
        """Set job queue in memcached (or app context)."""
        if self.client is not None:
            self.client.set("job_queue", value)
        else:
            g.job_queue = value

    def get_all_resources(self):
        """Get list of all jobs from memcached (or app context)."""
        registry.initialize()
        if self.client is not None:
            return self.client.get("all_resources")
        else:
            return g.all_resources

    def set_all_resources(self, value):
        """Set list of all jobs in memcached (or app context)."""
        if self.client is not None:
            self.client.set("all_resources", list(set(value)))
        else:
            g.all_resources = list(set(value))

    def get_job(self, job):
        """Get 'job' from memcached (or from resource_dict in app context) and return it."""
        registry.initialize()

        if self.client is not None:
            return self.client.get(job)
        else:
            return g.resource_dict.get(job)

    def set_job(self, job, value):
        """Set 'job' to 'value' in memcached (or in resource_dict in app context)."""
        registry.initialize()

        if self.client is not None:
            self.client.set(job, value)
        else:
            g.resource_dict[job] = value

    def remove_job(self, job):
        """Remove 'job' from memcached (or resource_dict in app context)."""
        registry.initialize()

        if self.client is not None:
            self.client.delete(job)
        else:
            del g.resource_dict[job]

    def get_apikey_data(self, apikey):
        """Get cached API key data, if recent enough."""
        if self.client is not None:
            item = self.client.get(f"apikey_data_{apikey}")
        else:
            item = g.apikey_data.get(apikey)

        if not item:
            return None

        timestamp, data = item

        # Delete if expired
        if timestamp + timedelta(seconds=60) < datetime.now():
            self.remove_apikey_data(apikey)
            return None

        return data

    def set_apikey_data(self, apikey, data):
        """Store API key data in cache."""
        item = (datetime.now(), data)
        if self.client is not None:
            self.client.set(f"apikey_data_{apikey}", item)
        else:
            g.apikey_data[apikey] = item

    def remove_apikey_data(self, apikey):
        """Remove API key data from cache."""
        if self.client is not None:
            self.client.delete(f"apikey_data_{apikey}")
        else:
            del g.apikey_data[apikey]