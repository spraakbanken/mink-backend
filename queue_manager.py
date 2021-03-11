"""Script for advancing the job queue with scheduled jobs.

This scheduler will

1. Unqueue jobs that are done, aborted or erroneous
2. Run the next job in the queue if there are fewer running jobs than allowed
3. For jobs with status "annotating", check if process is still running
"""

import json
import logging
import sys
import time
from pathlib import Path
from urllib import error, parse, request

from pymemcache.client.base import Client
from apscheduler.schedulers.blocking import BlockingScheduler


def check_queue(config):
    """Check the queue and run jobs if possible."""
    # Connect to memcached
    try:
        mc = connect_to_memcached(config)
    except Exception as e:
        logging.error(f"Failed to connect to memcached! {str(e)}")
        raise(e)

    if not mc.get("queue_initialized"):
        # Ask min-sb to initialise the job queue
        try:
            req = request.Request(f"{config.get('MIN_SB_URL')}/init-queue?secret_key={config.get('MIN_SB_SECRET_KEY')}",
                                  method="GET")
            with request.urlopen(req) as f:
                logging.debug(f.read().decode("UTF-8"))
        except error.HTTPError as e:
            logging.error(f"Error! {e}")
            return
    q = mc.get("queue") or []

    # Do not continue if queue is empty
    if not q:
        logging.debug("Empty queue")
        return

    # Check how many jobs are running/waiting to be run or old
    running_jobs = []
    waiting_jobs = []
    old_jobs = []
    for j in q:
        job_info = mc.get(j)
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
            logging.info(f"Removing {job}")
            q.pop(q.index(job))
        mc.set("queue", q)

    logging.info(f"Running: {len(running_jobs)} Waiting: {len(waiting_jobs)}")

    # If there are fewer running jobs than allowed, start the next one in the queue
    while waiting_jobs and len(running_jobs) < config.get("SPARV_WORKERS", 1):
        job = waiting_jobs.pop(0)
        logging.info(f"Start annotation for job {job}")
        url = f"{config.get('MIN_SB_URL')}/start-annotation"
        try:
            data = parse.urlencode({"secret_key": config.get("MIN_SB_SECRET_KEY"), "user": job.get("user"),
                                    "corpus_id": job.get("corpus_id")}).encode()
            req = request.Request(url, data=data, method="PUT")
            with request.urlopen(req) as f:
                logging.debug(f.read().decode("UTF-8"))
        except error.HTTPError as e:
            logging.error(f"Error! {e}")
            break

    # For jobs with status "annotating", check if process is still running
    for job in running_jobs:
        url = f"{config.get('MIN_SB_URL')}/check-running"
        try:
            data = parse.urlencode({"secret_key": config.get("MIN_SB_SECRET_KEY"), "user": job.get("user"),
                                    "corpus_id": job.get("corpus_id")}).encode()
            req = request.Request(url, data=data, method="GET")
            with request.urlopen(req) as f:
                logging.info(f.read().decode("UTF-8"))
        except error.HTTPError as e:
            logging.error(f"Error! {e}")


def import_config():
    """Import default and user config."""
    import config
    Config = {item: getattr(config, item) for item in dir(config) if item.isupper()}

    user_config_path = Path("instance") / "config.py"
    if user_config_path.is_file():
        from instance import config as user_config
        User_Config = {item: getattr(user_config, item) for item in dir(user_config) if item.isupper()}
        Config.update(User_Config)

    return Config


def connect_to_memcached(config):
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

    socket_path = Path("instance") / config.get("MEMCACHED_SOCKET")
    mc = Client(f"unix:{socket_path}", serializer=json_serializer, deserializer=json_deserializer)
    # Check if connection is working
    mc.get("test")
    return mc


if __name__ == '__main__':
    # Load config
    config = import_config()

    # Configure logger
    logfmt = "%(asctime)-15s - %(levelname)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    if sys.stdin.isatty():
        # Script is run interactively: log to console on debug level
        logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, format=logfmt, datefmt=datefmt)
    else:
        # Log to file
        today = time.strftime("%Y-%m-%d")
        logdir = Path("instance") / "logs"
        logfile = logdir / f"queue-{today}.log"
        logdir.mkdir(exist_ok=True)
        # Create log file if it does not exist
        if not logfile.is_file():
            with logfile.open("w") as f:
                now = time.strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"{now} CREATED DEBUG FILE\n\n")

        logging.basicConfig(filename=logfile, level=getattr(logging, config.get("LOG_LEVEL", "INFO").upper()),
                            format=logfmt, datefmt=datefmt)

    # Make apscheduler less chatty
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    # Start scheduler
    scheduler = BlockingScheduler()
    scheduler.add_executor("processpool")
    scheduler.add_job(check_queue, "interval", [config], seconds=config.get("CHECK_QUEUE_FREQUENCY", 20))

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass
