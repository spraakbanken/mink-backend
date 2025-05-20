"""Logging configuration for the Mink app."""

import logging
from logging.config import dictConfig
from pathlib import Path

from mink.core.config import settings

log_file_path = Path(settings.LOG_DIR) / settings.LOG_FILENAME

# Ensure the logs directory exists
Path(log_file_path).parent.mkdir(parents=True, exist_ok=True)

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": settings.LOG_FORMAT,
            "datefmt": settings.LOG_DATEFORMAT
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
        },
        "file": {
            "class": "logging.FileHandler",
            "formatter": "default",
            "filename": log_file_path,
        },
    },
    "root": {
        "level": "INFO",
        "handlers": ["file" if settings.LOG_TO_FILE else "console"]
    },
}

dictConfig(LOGGING_CONFIG)
logger = logging.getLogger("mink")
logger.setLevel(settings.LOG_LEVEL)
