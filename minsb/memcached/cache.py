"""Caching with Memcached using app context as back off solution."""

import json
from pathlib import Path

from flask import current_app as app
from flask import g
from pymemcache.client.base import Client

from minsb import queue


def connect():
    """Connect to the memcached socket."""

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
        app.config["cache_client"] = Client(f"unix:{socket_path}", serializer=json_serializer,
                                            deserializer=json_deserializer)
        # Check if connection is working
        app.config["cache_client"].get("test")
    except Exception as e:
        app.logger.error(f"Failed to connect to memcached! {str(e)}")
        app.config["cache_client"] = None


def get(key):
    """
    Get 'key' from memcached (or from app context) and return it.

    Initialise the queue if it has not been initialised (e.g. after memcached restart).
    """
    if not queue.is_initialized():
        queue.init_queue()

    mc = app.config.get("cache_client")
    if mc is not None:
        return mc.get(key)
    else:
        # Use app context if memcached is unavailable
        return g.job_queue.get(key)


def set(key, value):
    """
    Set 'item' to 'value' in memcached (or in app context).

    Initialise the queue if it has not been initialised (e.g. after memcached restart).
    """
    if not queue.is_initialized():
        queue.init_queue()

    mc = app.config.get("cache_client")
    if mc is not None:
        mc.set(key, value)
    else:
        # Use app context if memcached is unavailable
        g.job_queue[key] = value
