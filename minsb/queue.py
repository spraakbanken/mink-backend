"""Utilities related to a queue of Sparv jobs.

The job queue lives in the cache and also on the local file system (as backup).
"""

from pathlib import Path

from flask import current_app as app

from minsb import jobs


def init_queue():
    """Initiate a queue from the filesystem."""
    queue = []
    queue_dir = Path(app.instance_path) / Path(app.config.get("QUEUE_DIR"))
    queue_dir.mkdir(exist_ok=True)
    mc = app.config.get("cache_client")

    for f in sorted(queue_dir.iterdir(), key=lambda x: x.stat().st_mtime):
        with f.open() as fobj:
            job = jobs.load_from_str(fobj.read())
            job.save()
            app.logger.debug(f"Job in cache: '{mc.get(job.id)}'")
        queue.append(job.id)

    mc.set("queue", queue)
    app.logger.debug(f"Queue in cache: {mc.get('queue')}")
    return queue


def add(job):
    """Add a job item to the queue."""
    mc = app.config.get("cache_client")
    queue = mc.get("queue")

    # Avoid starting multiple jobs for same corpus simultaneously
    if job.id in queue and jobs.Status.none < job.status < jobs.Status.done:
        raise Exception("There is an unfinished job for this corpus!")

    job.set_status(jobs.Status.waiting)
    queue.append(job.id)
    mc.set("queue", queue)
    app.logger.debug(f"Queue in cache: {mc.get('queue')}")
    return job


def get():
    """Get the first job item from the queue."""
    mc = app.config.get("cache_client")
    queue = mc.get("queue")
    job = mc.get(queue[0])
    return job


def remove(job):
    """Remove job item from queue, e.g. when a job is aborted or a corpus is deleted."""
    mc = app.config.get("cache_client")
    queue = mc.get("queue")

    if job.id in queue:
        job = queue.pop(queue.index(job.id))
        mc.set("queue", queue)
        job.remove(abort=True)


def get_priority(job):
    """Get the queue priority of the job."""
    mc = app.config.get("cache_client")
    queue = mc.get("queue")
    try:
        return queue.index(job.id) + 1
    except ValueError:
        return -1
