"""Script for advancing the job queue with scheduled jobs.

This scheduler will make a call to the 'advance-queue' route of the mink API.
"""

import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib import error, parse, request

from apscheduler.schedulers.blocking import BlockingScheduler

# Configure logger
logfmt = "%(asctime)-15s - %(name)s - %(levelname)s - %(message)s"
datefmt = "%Y-%m-%d %H:%M:%S"
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, format=logfmt, datefmt=datefmt)
logger = logging.getLogger("mink_queue_manager")


def advance_queue(config: dict) -> None:
    """Check the queue and run jobs if possible.

    Args:
        config: Configuration dictionary.
    """
    logger.info("Calling '/advance-queue'")
    url = f"{config.get('MINK_URL')}/advance-queue"
    try:
        data = parse.urlencode({"secret_key": config.get("MINK_SECRET_KEY")}).encode()
        req = request.Request(url, data=data, method="PUT")
        with request.urlopen(req, timeout=60) as f:
            logger.debug(f.read().decode("UTF-8"))
    except error.HTTPError as e:
        logger.error("Error advancing queue! %s", e)


def ping_healthchecks(config: dict) -> None:
    """Ping healthchecks (https://healthchecks.io/) to tell it that the queue manager is running.

    Args:
        config: Configuration dictionary.
    """
    url = config.get("HEALTHCHECKS_URL")
    if url:
        logger.info("Sending ping to healthchecks")
        try:
            with request.urlopen(url, timeout=60) as f:
                logger.debug(f.read().decode("UTF-8"))
        except error.HTTPError as e:
            logger.error("Error pinging healthchecks! %s", e)
    else:
        logger.debug("No health check URL found")


def import_config() -> dict:
    """Import default and instance config.

    Returns:
        A dictionary containing the configuration.

    Raises:
        ImportError: If the config module cannot be imported.
    """
    import config  # noqa: PLC0415
    my_config = {item: getattr(config, item) for item in dir(config) if item.isupper()}

    instance_config_path = Path("instance") / "config.py"
    if instance_config_path.is_file():
        from instance import config as instance_config  # noqa: PLC0415
        instanceconfig = {item: getattr(instance_config, item) for item in dir(instance_config) if item.isupper()}
        my_config.update(instanceconfig)

    return my_config


if __name__ == "__main__":
    # Load config
    config = import_config()

    # If script is run interactively, log to console on debug level, otherwise log to file on info level
    if not sys.stdin.isatty():
        today = time.strftime("%Y-%m-%d")
        logdir = Path("instance") / "logs"
        logfile = logdir / f"queue-{today}.log"
        # Create log dir and log file if they do not exist
        logdir.mkdir(exist_ok=True)
        logfile.touch(exist_ok=True)
        file_handler = logging.FileHandler(logfile)
        file_handler.setFormatter(logging.Formatter(fmt=logfmt, datefmt=datefmt))
        logger.addHandler(file_handler)
        logger.setLevel(config.get("LOG_LEVEL", "INFO").upper())

    logger.info("Starting Mink queue manager")

    # Make apscheduler less chatty
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    # Start scheduler
    scheduler = BlockingScheduler()
    scheduler.add_executor("threadpool", max_workers=1)
    scheduler.add_job(advance_queue, "interval", [config], seconds=config.get("CHECK_QUEUE_FREQUENCY", 20))
    scheduler.add_job(ping_healthchecks, "interval", [config], minutes=config.get("PING_FREQUENCY", 60),
                      next_run_time=datetime.now(), misfire_grace_time=10 * 60)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass
