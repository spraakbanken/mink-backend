"""Script for advancing the job queue with scheduled jobs.

This scheduler will make calls to the '/queue/advance' and '/queue/health' routes of the Mink API.
"""

import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
from apscheduler.schedulers.blocking import BlockingScheduler

from mink.core import return_codes
from mink.core.config import settings

# Configure logger
logging.basicConfig(
    stream=sys.stdout, level=settings.LOG_LEVEL, format=settings.LOG_FORMAT, datefmt=settings.LOG_DATEFORMAT
)
logger = logging.getLogger("mink_queue_manager")
_QUEUE_HEALTH_STATE: dict[str, bool | str | None] = {"healthy": None, "warning": None}


def advance_queue() -> None:
    """Check the queue and run jobs if possible."""
    logger.info("Calling '/queue/advance'")
    url = f"{settings.MINK_URL}/queue/advance"
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


def send_slack_webhook(message: str) -> None:
    """Send a queue-health notification to Slack if a webhook URL is configured."""
    if not settings.SLACK_NOTIFICATIONS_WEBHOOK_URL:
        return

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(settings.SLACK_NOTIFICATIONS_WEBHOOK_URL, json={"text": message})
            response.raise_for_status()
    except httpx.HTTPError:
        logger.exception("Error sending queue health Slack notification")


def check_queue_health() -> None:
    """Poll queue health and log or notify when the health state changes."""
    logger.info("Calling '/queue/health'")
    url = f"{settings.MINK_URL}/queue/health"
    params = {"secret_key": settings.MINK_SECRET_KEY}
    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.get(url, params=params)

        if response.status_code == return_codes.QUEUE_HEALTHY.status_code:
            if _QUEUE_HEALTH_STATE["healthy"] is False:
                logger.info("Queue health restored")
                send_slack_webhook("Mink queue health restored.")
            else:
                logger.debug("Queue health looks good")
            _QUEUE_HEALTH_STATE["healthy"] = True
            _QUEUE_HEALTH_STATE["warning"] = None
            return

        if response.status_code == return_codes.QUEUE_DEGRADED.status_code:
            try:
                payload = response.json()
            except ValueError:
                payload = {}

            warnings = payload.get("warnings") or []
            if warnings:
                warning_text = "; ".join(str(warning) for warning in warnings)
            else:
                warning_text = str(payload.get("info") or response.text or return_codes.QUEUE_DEGRADED.message)

            if _QUEUE_HEALTH_STATE["healthy"] is not False or _QUEUE_HEALTH_STATE["warning"] != warning_text:
                logger.warning("Queue health warning: %s", warning_text)
                send_slack_webhook(f"Mink queue health warning: {warning_text}")
            else:
                logger.debug("Queue health still degraded: %s", warning_text)
            _QUEUE_HEALTH_STATE["healthy"] = False
            _QUEUE_HEALTH_STATE["warning"] = warning_text
            return

        response.raise_for_status()
        logger.debug("Unexpected queue health response: %s", response.text)
    except httpx.HTTPError:
        logger.exception("Error checking queue health")


if __name__ == "__main__":
    # Configure logging
    # If script is not run interactively, log to file, otherwise log to console
    if not sys.stdin.isatty():
        log_file_path = Path(settings.LOG_DIR) / f"queue-{time.strftime('%Y-%m-%d')}.log"
        Path(log_file_path).parent.mkdir(parents=True, exist_ok=True)
        loghandler = logging.FileHandler(log_file_path)
        loghandler.setFormatter(logging.Formatter(settings.LOG_FORMAT, datefmt=settings.LOG_DATEFORMAT))
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
    scheduler.add_job(check_queue_health, "interval", seconds=settings.CHECK_QUEUE_HEALTH_FREQUENCY)
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
