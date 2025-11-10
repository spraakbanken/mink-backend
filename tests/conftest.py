"""Pytest configuration for custom logging levels."""

import logging
import sys
from collections import defaultdict
from typing import ClassVar

import pytest
from colorama import Fore, Style
from fastapi.routing import APIRoute

# Ensure mink app and loggers are imported before logging config
sys.path.insert(0, str((__file__).rsplit("/", 2)[0]))  # Add project root to sys.path if needed
from mink.core.config import settings
from mink.main import app

# Set mink's environment to testing (this affects logging and MKDocs generation)
settings.ENV = "testing"


class ColorFormatter(logging.Formatter):
    """Custom logging formatter that adds color to log messages based on their level."""
    COLORS: ClassVar[dict] = {
        logging.DEBUG: Fore.CYAN,
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Fore.MAGENTA,
    }

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record with color based on the log level."""
        color = self.COLORS.get(record.levelno, "")
        message = super().format(record)
        return f"{color}{message}{Style.RESET_ALL}"


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add custom command line options for pytest."""
    parser.addoption(
        "--custom-log-level",
        action="store",
        default="INFO",
        help="Set custom log level for test logging"
    )
    parser.addoption(
        "--mink-log-level",
        action="store",
        default="WARNING",
        help="Set log level for the 'mink' logger"
    )


def pytest_configure(config: pytest.Config) -> None:
    """Configure pytest logging."""
    default_formatter = ColorFormatter("%(name)s: %(levelname)s - %(message)s")

    # Get custom log level from command line options
    log_level_str = config.getoption("--custom-log-level").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    # Remove all handlers from root logger
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    # Set up colored handler for mink_test
    mink_test_logger = logging.getLogger("mink_test")
    mink_test_logger.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(default_formatter)
    handler.setLevel(logging.NOTSET)  # Let the logger's level control output
    mink_test_logger.addHandler(handler)
    mink_test_logger.setLevel(log_level)
    mink_test_logger.propagate = False

    # Set mink logger level from flag
    mink_log_level_str = config.getoption("--mink-log-level").upper()
    mink_log_level = getattr(logging, mink_log_level_str, logging.WARNING)
    mink_logger = logging.getLogger("mink")
    mink_logger.setLevel(mink_log_level)

    # Make mink_logger use colored output
    if not mink_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(default_formatter)
        mink_logger.addHandler(handler)
        mink_logger.propagate = False  # Prevent propagation to root logger


class RouteInfo:
    """Class to store route tags and methods from the Mink app."""
    def __init__(self) -> None:
        """Initialize the RouteInfo and populate it with route tags and methods."""
        # Collect all route-method pairs
        self.tag_dict = defaultdict(list)
        self.routes = set()
        self.tagged_routes = 0
        self.untagged_routes = []
        self.tested_routes = set()
        for route in app.routes:
            if isinstance(route, APIRoute):
                # Get tags from the route if available and non-empty
                if hasattr(route, "tags") and route.tags:
                    self.tag_dict[route.tags[0]].extend((method, route.path) for method in route.methods)
                    self.tagged_routes += 1
                    self.routes.add(route.path)
                elif hasattr(route, "methods") and hasattr(route, "path"):
                    self.untagged_routes.extend((method, route.path) for method in route.methods)
                    self.routes.add(route.path)

    def set_tested(self, path: str) -> None:
        """Mark a route as tested."""
        self.tested_routes.add(path)

    def get_untested_routes(self) -> list:
        """Get a list of untested routes."""
        return [path for path in self.routes if path not in self.tested_routes]


ROUTE_INFO = RouteInfo()


# ------------------------------------------------------------------------------
# Wrap up
# ------------------------------------------------------------------------------

def pytest_sessionfinish(session: object) -> None:  # noqa: ARG001 (unused argument)
    """Test that all routes have been tested."""
    untested = ROUTE_INFO.get_untested_routes()
    if untested:
        logging.getLogger("mink_test").warning("Found %d untested routes: %s", len(untested), untested)
