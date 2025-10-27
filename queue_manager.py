"""Script for advancing the job queue with scheduled jobs.

This scheduler will make a call to the 'advance-queue' route of the mink API.
"""

import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
from apscheduler.schedulers.blocking import BlockingScheduler

from mink.core.config import settings

# Configure logger
logging.basicConfig(
    stream=sys.stdout, level=settings.LOG_LEVEL, format=settings.LOG_FORMAT, datefmt=settings.LOG_DATEFORMAT
)
logger = logging.getLogger("mink_queue_manager")


def advance_queue() -> None:
    """Check the queue and run jobs if possible."""
    logger.info("Calling '/advance-queue'")
    url = f"{settings.MINK_URL}/advance-queue"
    try:
        params = {"secret_key": settings.MINK_SECRET_KEY}
        with httpx.Client(timeout=60.0) as client:
            response = client.put(url, params=params)
            response.raise_for_status()
            logger.debug(response.text)
    except httpx.HTTPError:
        logger.exception("Error advancing queue")


def ping_healthchecks(url: str) -> None:
    """Ping healthchecks (https://healthchecks.io/) to tell it that the queue manager is running."""
    logger.debug("Sending ping to healthchecks")
    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.get(url)
            response.raise_for_status()
            logger.debug(response.text)
    except httpx.HTTPError:
        logger.exception("Error pinging healthchecks")


if __name__ == "__main__":
    # Configure logging
    # If script is not run interactively, log to file, otherwise log to console
    if not sys.stdin.isatty():
        log_file_path = Path(settings.LOG_DIR) / f"queue-{time.strftime('%Y-%m-%d')}.log"
        Path(log_file_path).parent.mkdir(parents=True, exist_ok=True)
        loghandler = logging.FileHandler(log_file_path)
        logger.addHandler(loghandler)

    logger.info("Starting Mink queue manager")

    # Make some loggers less chatty
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("tzlocal").setLevel(logging.WARNING)
    logging.getLogger("httpcore.http11").setLevel(logging.WARNING)
    logging.getLogger("httpcore.connection").setLevel(logging.WARNING)

    # Start scheduler and add jobs
    scheduler = BlockingScheduler()
    scheduler.add_executor("threadpool", max_workers=1)
    scheduler.add_job(advance_queue, "interval", seconds=settings.CHECK_QUEUE_FREQUENCY)
    if settings.HEALTHCHECKS_URL:
        scheduler.add_job(
            ping_healthchecks,
            "interval",
            minutes=settings.PING_FREQUENCY,
            next_run_time=datetime.now(),
            misfire_grace_time=10 * 60,
            args=[settings.HEALTHCHECKS_URL],
        )
    else:
        logger.warning("No health check URL found, not pinging healthchecks")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass
