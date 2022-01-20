"""Utilities related to a queue of Sparv jobs.

The job queue lives in the cache and also on the local file system (as backup).
"""

from pathlib import Path

from flask import current_app as app
from flask import g

from minsb import jobs
from minsb.memcached import cache


def init_queue():
    """Initiate a queue from the filesystem."""
    app.logger.info("Initializing queue")
    mc = app.config.get("cache_client")
    queue = []
    all_jobs = []  # Storage for all jobs, including done, aborted and errorneous
    queue_dir = Path(app.instance_path) / app.config.get("QUEUE_DIR")
    queue_dir.mkdir(exist_ok=True)

    if mc is not None:
        mc.set("queue_initialized", True)
        for f in sorted(queue_dir.iterdir(), key=lambda x: x.stat().st_mtime):
            with f.open() as fobj:
                job = jobs.load_from_str(fobj.read())
                job.save()
                all_jobs.append(job.id)
                app.logger.debug(f"Job in cache: '{mc.get(job.id)}'")
            # Queue job unless it is done, aborted or erroneous
            if job.status not in [jobs.Status.done, jobs.Status.error, jobs.Status.aborted]:
                queue.append(job.id)
        mc.set("queue", queue)
        mc.set("all_jobs", all_jobs)
        app.logger.debug(f"Queue in memcached: {mc.get('queue')}")
        app.logger.debug(f"All jobs in memcached: {mc.get('all_jobs')}")

    else:
        app.logger.info("Memcached not available. Using app context instead.")
        g.queue_initialized = True
        g.job_queue = {}
        for f in sorted(queue_dir.iterdir(), key=lambda x: x.stat().st_mtime):
            with f.open() as fobj:
                job = jobs.load_from_str(fobj.read())
                all_jobs.append(job.id)
                g.job_queue[job.id] = str(job)
            # Queue job unless it is done, aborted or erroneous
            if job.status not in [jobs.Status.done, jobs.Status.error, jobs.Status.aborted]:
                queue.append(job.id)
        g.job_queue["queue"] = queue
        g.job_queue["all_jobs"] = all_jobs
        app.logger.debug(f"Queue in cache: {g.job_queue['queue']}")
        app.logger.debug(f"All jobs in cache: {g.job_queue['all_jobs']}")


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
            cache.connect()
            return False

    if g.queue_initialized:
        return True
    return False


def add(job):
    """Add a job item to the queue."""
    queue = cache.get("queue")

    # Avoid starting multiple jobs for same corpus simultaneously
    if job.id in queue and jobs.Status.none < job.status < jobs.Status.done:
        raise Exception("There is an unfinished job for this corpus!")

    job.set_status(jobs.Status.waiting)
    if job.id in queue:
        queue.pop(queue.index(job.id))
    queue.append(job.id)
    cache.set("queue", queue)
    app.logger.debug(f"Queue in cache: {cache.get('queue')}")
    return job


def get():
    """Get the first job item from the queue."""
    queue = cache.get("queue")
    job = cache.get(queue[0])
    return job


def remove(job):
    """Remove job item from queue, e.g. when a job is aborted or a corpus is deleted."""
    queue = cache.get("queue")

    if job.id in queue:
        queue.pop(queue.index(job.id))
        cache.set("queue", queue)


def get_priority(job):
    """Get the queue priority of the job."""
    queue = cache.get("queue")
    try:
        return queue.index(job.id) + 1
    except ValueError:
        return -1


def get_running_waiting():
    """Get the running and waiting jobs from the queue."""
    running_jobs = []
    waiting_jobs = []

    queue = cache.get("queue")
    for j in queue:
        job = jobs.load_from_str(cache.get(j))
        status = job.status
        if status == jobs.Status.annotating:
            running_jobs.append(job)
        elif status == jobs.Status.waiting:
            waiting_jobs.append(job)

    return running_jobs, waiting_jobs


def unqueue_old():
    """Unqueue jobs that are done, aborted or erroneous."""
    queue = cache.get("queue")
    old_jobs = []
    for j in queue:
        job = jobs.load_from_str(cache.get(j))
        status = job.status
        if status in [jobs.Status.done, jobs.Status.error, jobs.Status.aborted]:
            old_jobs.append(j)

    if old_jobs:
        for j in old_jobs:
            app.logger.info(f"Removing job {j}")
            queue.pop(queue.index(j))
        cache.set("queue", queue)


def get_user_jobs(user):
    """Get all jobs belonging to one user."""
    all_jobs = cache.get("all_jobs")
    user_jobs = []
    for j in all_jobs:
        job = jobs.load_from_str(cache.get(j))
        if job.user == user:
            user_jobs.append(job)
    return user_jobs
