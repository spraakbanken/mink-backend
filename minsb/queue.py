"""Utilities related to a queue of Sparv jobs.

The job queue lives in the cache and also on the local file system (as backup).
"""

from pathlib import Path

from flask import current_app as app
from flask import g

from minsb import jobs, utils


def init_queue():
    """Initiate a queue from the filesystem."""
    app.logger.info("Initializing queue")
    mc = app.config.get("cache_client")
    queue = []
    queue_dir = Path(app.instance_path) / app.config.get("QUEUE_DIR")
    queue_dir.mkdir(exist_ok=True)
    if mc is not None:
        mc.set("queue_initialized", True)
        for f in sorted(queue_dir.iterdir(), key=lambda x: x.stat().st_mtime):
            with f.open() as fobj:
                job = jobs.load_from_str(fobj.read())
                job.save()
                app.logger.debug(f"Job in cache: '{mc.get(job.id)}'")
            # Queue job unless it is done, aborted or erroneous
            if job.status not in [jobs.Status.done, jobs.Status.error, jobs.Status.aborted]:
                queue.append(job.id)
        mc.set("queue", queue)
        app.logger.debug(f"Queue in cache: {mc.get('queue')}")

    else:
        app.logger.info("Memcached not available. Using app context instead.")
        g.queue_initialized = True
        g.job_queue = {}
        for f in sorted(queue_dir.iterdir(), key=lambda x: x.stat().st_mtime):
            with f.open() as fobj:
                job = jobs.load_from_str(fobj.read())
                g.job_queue[job.id] = str(job)
            # Queue job unless it is done, aborted or erroneous
            if job.status not in [jobs.Status.done, jobs.Status.error, jobs.Status.aborted]:
                queue.append(job.id)
        g.job_queue["queue"] = queue
        app.logger.debug(f"Queue in cache: {g.job_queue['queue']}")


def is_initialized():
    """Return True if the job queue has been initialized, else False."""
    mc = app.config.get("cache_client")
    if mc is not None:
        try:
            if mc.get("queue_initialized"):
                return True
            return False
        except Exception as e:
            app.logger.error(f"Lost connection to memcached! ({str(e)}) Trying to reconnect...")
            utils.connect_to_memcached()
            return False

    if g.queue_initialized:
        return True
    return False


def add(job):
    """Add a job item to the queue."""
    queue = utils.memcached_get("queue")

    # Avoid starting multiple jobs for same corpus simultaneously
    if job.id in queue and jobs.Status.none < job.status < jobs.Status.done:
        raise Exception("There is an unfinished job for this corpus!")

    job.set_status(jobs.Status.waiting)
    if job.id in queue:
        queue.pop(queue.index(job.id))
    queue.append(job.id)
    utils.memcached_set("queue", queue)
    app.logger.debug(f"Queue in cache: {utils.memcached_get('queue')}")
    return job


def get():
    """Get the first job item from the queue."""
    queue = utils.memcached_get("queue")
    job = utils.memcached_get(queue[0])
    return job


def remove(job):
    """Remove job item from queue, e.g. when a job is aborted or a corpus is deleted."""
    queue = utils.memcached_get("queue")

    if job.id in queue:
        queue.pop(queue.index(job.id))
        utils.memcached_set("queue", queue)


def get_priority(job):
    """Get the queue priority of the job."""
    queue = utils.memcached_get("queue")
    try:
        return queue.index(job.id) + 1
    except ValueError:
        return -1


def get_running_waiting():
    """Get the running and waiting jobs from the queue."""
    running_jobs = []
    waiting_jobs = []

    queue = utils.memcached_get("queue")
    for j in queue:
        job = jobs.load_from_str(utils.memcached_get(j))
        status = job.status
        if status == jobs.Status.annotating:
            running_jobs.append(job)
        elif status == jobs.Status.waiting:
            waiting_jobs.append(job)

    return running_jobs, waiting_jobs


def unqueue_old():
    """Unqueue jobs that are done, aborted or erroneous."""
    queue = utils.memcached_get("queue")
    old_jobs = []
    for j in queue:
        job = jobs.load_from_str(utils.memcached_get(j))
        status = job.status
        if status in [jobs.Status.done, jobs.Status.error, jobs.Status.aborted]:
            old_jobs.append(j)

    if old_jobs:
        for j in old_jobs:
            app.logger.info(f"Removing job {j}")
            queue.pop(queue.index(j))
        utils.memcached_set("queue", queue)
