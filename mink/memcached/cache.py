"""Caching with Memcached using app context as backoff solution."""

import json
from pathlib import Path

from flask import current_app as app
from flask import g
from pymemcache.client.base import Client

from mink import corpus_registry, queue


class Cache():
    """Cache class providing caching with Memcached (and app context as backoff)."""

    def __init__(self):
        """
        Init variables in app context (as backup for regular cache) and try to reconnect to cache if necessary.

        This is done before each request (app context g cannot be stored in between requests).
        """
        # Queue
        g.queue_initialized = False
        g.job_queue = []  # Active jobs
        g.jobs_dict = {}
        g.all_jobs = []  # All jobs, including those with status done, error and aborted

        # Corpora
        g.corpus_registry_initialized = False
        g.corpora = []

        self.client = None
        self.connect()

    def connect(self):
        """Connect to the memcached socket and set client."""
        def json_serializer(key, value):
            if type(value) == str:
                return value, 1
            return json.dumps(value), 2

        def json_deserializer(key, value, flags):
            if flags == 1:
                return value
            if flags == 2:
                return json.loads(value)
            raise Exception("Unknown serialization format")

        socket_path = Path(app.instance_path) / app.config.get("MEMCACHED_SOCKET")
        try:
            self.client = Client(f"unix:{socket_path}", serializer=json_serializer,
                                    deserializer=json_deserializer)
            # Check if connection is working
            self.client.get("test")
        except Exception as e:
            app.logger.error(f"Failed to connect to memcached! {str(e)}")
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
        queue.init()

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

    def get_all_jobs(self):
        """Get list of all jobs from memcached (or app context)."""
        queue.init()
        if self.client is not None:
            return self.client.get("all_jobs")
        else:
            return g.all_jobs

    def set_all_jobs(self, value):
        """Set list of all jobs in memcached (or app context)."""
        if self.client is not None:
            self.client.set("all_jobs", list(set(value)))
        else:
            g.all_jobs = list(set(value))

    def get_job(self, job):
        """Get 'job' from memcached (or from job_queue in app context) and return it."""
        queue.init()

        if self.client is not None:
            return self.client.get(job)
        else:
            return g.jobs_dict.get(job)

    def set_job(self, job, value):
        """Set 'job' to 'value' in memcached (or in job_queue in app context)."""
        queue.init()

        if self.client is not None:
            self.client.set(job, value)
        else:
            g.jobs_dict[job] = value

    def remove_job(self, job):
        """Remove 'job' from memcached (or job_queue in app context)."""
        queue.init()

        if self.client is not None:
            self.client.delete(job)
        else:
            del g.jobs_dict[job]

    def get_corpus_registry_initialized(self):
        """Get bool value for 'corpus_registry_initialized' from memcached (or app context)."""
        if self.client is not None:
            return self.client.get("corpus_registry_initialized")
        else:
            return g.corpus_registry_initialized

    def set_corpus_registry_initialized(self, is_initialized):
        """Set 'corpus_registry_initialized' to bool 'is_initialized' in memcached (or app context)."""
        if self.client is not None:
            self.client.set("corpus_registry_initialized", bool(is_initialized))
        else:
            g.corpus_registry_initialized = bool(is_initialized)

    def set_corpora(self, corpora):
        """Set list of corpus IDs in memcached (or app context)."""
        corpus_registry.init()

        if self.client is not None:
            self.client.set("corpora", corpora)
        else:
            g.corpora = corpora

    def get_corpora(self):
        """Get list of all corpus IDs from memcached (or app context)."""
        corpus_registry.init()
        if self.client is not None:
            return self.client.get("corpora")
        else:
            return g.corpora
