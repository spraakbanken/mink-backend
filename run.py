"""Run the FastAPI application with Uvicorn for development.

This script sets up the Uvicorn server with custom logging and reload capabilities.
"""

import argparse
import logging.config

import uvicorn

from mink.core.config import settings as mink_settings

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "()": "uvicorn.logging.DefaultFormatter",
            "fmt": mink_settings.LOG_FORMAT_UVICORN,
            "use_colors": None,
        },
    },
    "handlers": {
        "default": {
            "class": "logging.StreamHandler",
            "formatter": "default",
        },
    },
    "root": {"handlers": ["default"], "level": "INFO"},
}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the FastAPI app with Uvicorn.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to (default: 8000)")
    args = parser.parse_args()

    logging.config.dictConfig(LOGGING_CONFIG)
    mink_settings.ENV = "development"
    logging.getLogger("mink").info("Will start Mink in development mode")

    uvicorn.run(
        "mink.main:app",
        host=args.host,
        port=args.port,
        reload=True,
        reload_includes=["mink/**/*", "templates/**/*", "docs/developers-guide.md", "docs/mkdocs/index.md"],
        reload_excludes=["run.py", "queue_manager.py", "tests/*.py", "**/__pycache__/**/*"],
        log_config=None,  # Prevents uvicorn from overriding the above logging config
    )
