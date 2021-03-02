"""Script for advancing the job queue with scheduled jobs."""

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
    q = mc.get("queue") or []

    # Check how many jobs are running/waiting to be run
    running_jobs = []
    waiting_jobs = []
    for j in q:
        job_info = json.loads(mc.get(j))
        if job_info.get("status") == "annotating":
            running_jobs.append(job_info)
        elif job_info.get("status") == "waiting":
            waiting_jobs.append(job_info)

    print(f"Running: {len(running_jobs)} Waiting: {len(waiting_jobs)}")

    # If there are fewer running jobs than allowed, start the next one in the queue
    if waiting_jobs and len(running_jobs) < config.get("SPARV_WORKERS", 1):
        job = waiting_jobs[0]
        url = f"{config.get('MIN_SB_URL')}/start-annotation"
        try:
            data = parse.urlencode({"user": job.get("user"), "corpus_id": job.get("corpus_id")}).encode()
            req = request.Request(url, data=data, method="PUT")
            with request.urlopen(req) as f:
                print(f.read().decode("UTF-8"))
        except error.HTTPError as e:
            print("Error!", e)

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
