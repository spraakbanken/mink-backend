"""Logging configuration for the Mink app."""

import logging
from logging.config import dictConfig
from pathlib import Path

from mink.config import settings

# Ensure the logs directory exists
Path(settings.LOG_FILE_PATH).parent.mkdir(parents=True, exist_ok=True)

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
            "filename": settings.LOG_FILE_PATH,
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
