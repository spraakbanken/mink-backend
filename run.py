"""Run the FastAPI application with Uvicorn for development.

This script sets up the Uvicorn server with custom logging and reload capabilities.
"""

import argparse
import logging.config

import uvicorn

from mink.core.config import settings as mink_settings

mink_settings.ENV = "development"
mink_settings.LOG_TO_FILE = False
mink_settings.LOG_LEVEL = "DEBUG"

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
    "root": {"handlers": ["default"], "level": mink_settings.LOG_LEVEL},
}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the FastAPI app with Uvicorn.")
    parser.add_argument("--host", "-H", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
    parser.add_argument("--port", "-p", type=int, default=8000, help="Port to bind to (default: 8000)")
    args = parser.parse_args()

    logging.config.dictConfig(LOGGING_CONFIG)
    logging.getLogger("mink").info("Will start Mink in development mode")

    # Suppress some chatty logs
    logging.getLogger("watchfiles.main").setLevel("WARNING")

    uvicorn.run(
        "mink.main:app",
        host=args.host,
        port=args.port,
        reload=True,
            reload_includes=["mink/**/*", "templates/**/*", "docs/developers-guide.md", "docs/mkdocs/index.md"],
            reload_excludes=[
                "run.py",
                "queue_manager.py",
                "tests/*.py",
                "**/__pycache__/*",
                "mink/__pycache__",
                "**/*.pyc",
                "**/*.pyo",
            ],
        log_config=None,  # Prevents uvicorn from overriding the above logging config
    )
