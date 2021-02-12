"""Utilities related to a job queue.

The job queue lives in the cache and also on the local file system (as backup).
"""

from pathlib import Path

from flask import current_app as app

PARTITIONER = "_"  # The string used to separate a user and a corpus ID


def init_queue():
    """Initiate a queue from the filesystem."""
    queue = []
    queue_dir = Path(app.instance_path) / Path(app.config.get("QUEUE_DIR"))
    queue_dir.mkdir(exist_ok=True)

    for f in sorted(queue_dir.iterdir(), key=lambda x: x.stat().st_mtime):
        user = f.name[:f.name.rfind(PARTITIONER)]
        corpus_id = f.name[f.name.rfind(PARTITIONER) + len(PARTITIONER):]
        queue.append((user, corpus_id))

    return queue


def add(user, corpus_id):
    """Add an item to the queue."""
    mc = app.config.get("cache_client")
    queue = mc.get("queue")

    # No queue in cache, get from file system
    if queue is None:
        queue = init_queue()

    # Add to file system queue
    queue_dir = Path(app.instance_path) / Path(app.config.get("QUEUE_DIR"))
    queue_dir.mkdir(exist_ok=True)
    (queue_dir / Path(f"{user}{PARTITIONER}{corpus_id}")).touch()

    queue.append((user, corpus_id))
    mc.set("queue", queue)
    app.logger.debug(f"Queue in cache: '{mc.get(queue)}'")


def pop():
    """Get the first item from the queue and remove it."""
    mc = app.config.get("cache_client")
    queue = mc.get("queue")

    # No queue in cache, get from file system
    if queue is None:
        queue = init_queue()
        mc.set("queue", queue)

        # No queue on file system either
        if not queue:
            return None

    user, corpus_id = queue.pop(0)

    # Pop from file system queue
    queue_dir = Path(app.instance_path) / Path(app.config.get("QUEUE_DIR"))
    filename = queue_dir / Path(f"{user}{PARTITIONER}{corpus_id}")
    filename.unlink(missing_ok=True)

    mc.set("queue", queue)
    return user, corpus_id
