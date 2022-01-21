"""Utilities related to a queue of Sparv jobs.

The job queue lives in the cache and also on the local file system (as backup).
"""

from pathlib import Path

from flask import current_app as app
from flask import g

from minsb import jobs


def init_queue():
    """Init a queue from the filesystem if it has not been initialised already."""
    if not g.cache.get_queue_initialised():
        app.logger.info("Initializing queue")
        queue = []
        all_jobs = []  # Storage for all jobs, including done, aborted and errorneous
        queue_dir = Path(app.instance_path) / app.config.get("QUEUE_DIR")
        queue_dir.mkdir(exist_ok=True)

        g.cache.set_queue_initialised(True)

        for f in sorted(queue_dir.iterdir(), key=lambda x: x.stat().st_mtime):
            with f.open() as fobj:
                job = jobs.load_from_str(fobj.read())
                job.save()  # Update job in file system and add to cache
                all_jobs.append(job.id)
                app.logger.debug(f"Job in cache: '{g.cache.get(job.id)}'")
            # Queue job unless it is done, aborted or erroneous
            if job.status not in [jobs.Status.done, jobs.Status.error, jobs.Status.aborted]:
                queue.append(job.id)
        g.cache.set_job_queue(queue)
        g.cache.set_all_jobs(all_jobs)
        app.logger.debug(f"Queue in cache: {g.cache.get_job_queue()}")
        app.logger.debug(f"All jobs in cache: {g.cache.get_all_jobs()}")


def add(job):
    """Add a job item to the queue."""
    queue = g.cache.get_job_queue()

    # Avoid starting multiple jobs for same corpus simultaneously
    if job.id in queue and jobs.Status.none < job.status < jobs.Status.done:
        raise Exception("There is an unfinished job for this corpus!")

    job.set_status(jobs.Status.waiting)
    if job.id in queue:
        queue.pop(queue.index(job.id))
    queue.append(job.id)
    g.cache.set_job_queue(queue)
    app.logger.debug(f"Queue in cache: {g.cache.get_job_queue()}")
    return job


def get():
    """Get the first job item from the queue."""
    queue = g.cache.get_job_queue()
    job = g.cache.get(queue[0])
    return job


def remove(job):
    """Remove job item from queue, e.g. when a job is aborted or a corpus is deleted."""
    queue = g.cache.get_job_queue()

    if job.id in queue:
        queue.pop(queue.index(job.id))
        g.cache.set_job_queue(queue)


def get_priority(job):
    """Get the queue priority of the job."""
    queue = g.cache.get_job_queue()
    try:
        return queue.index(job.id) + 1
    except ValueError:
        return -1


def get_running_waiting():
    """Get the running and waiting jobs from the queue."""
    running_jobs = []
    waiting_jobs = []

    queue = g.cache.get_job_queue()
    for j in queue:
        job = jobs.load_from_str(g.cache.get(j))
        status = job.status
        if status == jobs.Status.annotating:
            running_jobs.append(job)
        elif status == jobs.Status.waiting:
            waiting_jobs.append(job)

    return running_jobs, waiting_jobs


def unqueue_old():
    """Unqueue jobs that are done, aborted or erroneous."""
    queue = g.cache.get_job_queue()
    old_jobs = []
    for j in queue:
        job = jobs.load_from_str(g.cache.get(j))
        status = job.status
        if status in [jobs.Status.done, jobs.Status.error, jobs.Status.aborted]:
            old_jobs.append(j)

    if old_jobs:
        for j in old_jobs:
            app.logger.info(f"Removing job {j}")
            queue.pop(queue.index(j))
        g.cache.set_job_queue(queue)


def get_user_jobs(user):
    """Get all jobs belonging to one user."""
    all_jobs = g.cache.get_all_jobs()
    user_jobs = []
    for j in all_jobs:
        job = jobs.load_from_str(g.cache.get(j))
        if job.user == user:
            user_jobs.append(job)
    return user_jobs
