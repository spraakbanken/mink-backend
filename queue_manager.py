"""Script for advancing the job queue with scheduled jobs.

This scheduler will

1. Unqueue jobs that are done, aborted or erroneous
2. Run the next job in the queue if there are fewer running jobs than allowed
3. For jobs with status "annotating", check if process is still running
"""

import json
import os
from pathlib import Path
from urllib import error, parse, request

import memcache
from apscheduler.schedulers.blocking import BlockingScheduler


def check_queue(config):
    """Check the queue and run jobs if possible."""
    # Connect to memcached
    socket_path = Path("instance") / Path(config.get("MEMCACHED_SOCKET"))
    mc = memcache.Client([f"unix:{str(socket_path)}"], debug=1)
    if not mc.get("queue_initialized"):
        try:
            req = request.Request(f"{config.get('MIN_SB_URL')}/init-queue", method="GET")
            with request.urlopen(req) as f:
                print(f.read().decode("UTF-8"))
        except error.HTTPError as e:
            print("Error!", e)
            return
    q = mc.get("queue") or []

    # Do not continue if queue is empty
    if not q:
        print("Empty queue")
        return

    # Check how many jobs are running/waiting to be run or old
    running_jobs = []
    waiting_jobs = []
    old_jobs = []
    for j in q:
        job_info = json.loads(mc.get(j))
        status = job_info.get("status")
        if status == "annotating":
            running_jobs.append(job_info)
        elif status == "waiting":
            waiting_jobs.append(job_info)
        elif status in ["done", "error", "aborted"]:
            old_jobs.append(j)

    # Unqueue jobs that are done, aborted or erroneous
    if old_jobs:
        for job in old_jobs:
            print(f"Removing {job}")
            q.pop(q.index(job))
        mc.set("queue", q)

    print(f"Running: {len(running_jobs)} Waiting: {len(waiting_jobs)}")

    # If there are fewer running jobs than allowed, start the next one in the queue
    while waiting_jobs and len(running_jobs) < config.get("SPARV_WORKERS", 1):
        job = waiting_jobs.pop(0)
        url = f"{config.get('MIN_SB_URL')}/start-annotation"
        try:
            data = parse.urlencode({"user": job.get("user"), "corpus_id": job.get("corpus_id")}).encode()
            req = request.Request(url, data=data, method="PUT")
            with request.urlopen(req) as f:
                print(f.read().decode("UTF-8"))
        except error.HTTPError as e:
            print("Error!", e)
            break

    # For jobs with status "annotating", check if process is still running
    for job in running_jobs:
        url = f"{config.get('MIN_SB_URL')}/check-running"
        try:
            data = parse.urlencode({"user": job.get("user"), "corpus_id": job.get("corpus_id")}).encode()
            req = request.Request(url, data=data, method="GET")
            with request.urlopen(req) as f:
                print(f.read().decode("UTF-8"))
        except error.HTTPError as e:
            print("Error!", e)


def import_config():
    """Import default and user config."""
    import config
    Config = {item: getattr(config, item) for item in dir(config) if item.isupper()}

    user_config_path = Path("instance") / Path("config.py")
    if user_config_path.is_file():
        from instance import config as user_config
        User_Config = {item: getattr(user_config, item) for item in dir(user_config) if item.isupper()}
        Config.update(User_Config)

    return Config


if __name__ == '__main__':
    # Load config
    config = import_config()

    scheduler = BlockingScheduler()
    scheduler.add_executor('processpool')
    scheduler.add_job(check_queue, 'interval', [config], seconds=config.get("CHECK_QUEUE_FREQUENCY", 20))
    print('Press Ctrl+{0} to exit'.format('Break' if os.name == 'nt' else 'C'))

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass
