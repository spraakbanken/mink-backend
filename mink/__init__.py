"""Instantiation of flask app."""

__version__ = "1.2.0-dev"

import logging
import shutil
import sys
import time
import traceback
from pathlib import Path

from flask import Flask, Response, g, request
from flask_cors import CORS

# Configure logger (some modules may log before the app is created)
logfmt = "%(asctime)-15s - %(name)s - %(levelname)s - %(message)s"
datefmt = "%Y-%m-%d %H:%M:%S"
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format=logfmt, datefmt=datefmt)

# ruff: noqa: E402 (module-import-not-at-top-of-file)
from mink.core import extensions, registry, routes, utils
from mink.memcached.cache import Cache
from mink.metadata import metadata_routes
from mink.sb_auth import login
from mink.sparv import process_routes, storage_routes


def create_app(log_to_file: bool = True) -> Flask:
    """Instantiate app.

    Args:
        log_to_file: Whether to log to a logfile. If set to False, logs will be written to stdout.

    Returns:
        The Flask application instance.
    """
    app = Flask(__name__)

    # Enable CORS
    CORS(app, supports_credentials=True)

    # Load default config and override with instance config
    app.config.from_object("config")

    # Prevent Flask from sorting json
    app.config["JSON_SORT_KEYS"] = False

    # Overwrite with instance config
    instance_config_path = Path(app.instance_path) / "config.py"
    if instance_config_path.is_file():
        app.config.from_pyfile(str(instance_config_path))

    # Make sure required config variables are set
    for var in ("SPARV_HOST", "SPARV_USER"):
        if not app.config.get(var):
            raise ValueError(f"{var!r} is not set.")

    # Configure logger
    logger = logging.getLogger(__name__)
    logger.setLevel(app.config.get("LOG_LEVEL", "INFO").upper())
    if log_to_file:
        today = time.strftime("%Y-%m-%d")
        logdir = Path("instance") / "logs"
        logfile = logdir / f"mink-{today}.log"
        logdir.mkdir(exist_ok=True)
        logfile.touch(exist_ok=True)

        file_handler = logging.FileHandler(logfile)
        file_handler.setFormatter(logging.Formatter(fmt=logfmt, datefmt=datefmt))
        logger.addHandler(file_handler)

    logger.info("Starting Mink %s", __version__)

    if tracking_matomo_url := app.config.get("TRACKING_MATOMO_URL"):
        app.logger.debug("Enabling tracking to Matomo")
        matomo_options = {}
        if tracking_matomo_auth_token := app.config.get("TRACKING_MATOMO_AUTH_TOKEN"):
            matomo_options["token_auth"] = tracking_matomo_auth_token
        extensions.matomo.activate(
            app,
            matomo_url=tracking_matomo_url,
            id_site=app.config["TRACKING_MATOMO_IDSITE"],
            ignored_routes=["/advance-queue"],
            base_url=app.config.get("MINK_URL"),
            **matomo_options,
        )
        # Suppress some chatty logs
        logging.getLogger("flask_matomo2").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
    else:
        app.logger.warning("NOT tracking to Matomo, please set TRACKING_MATOMO_URL and TRACKING_MATOMO_IDSITE.")

    with app.app_context():
        # Connect to cache and init the resource registry
        g.cache = Cache()
        registry.initialize()

        # Save JWT key in memory
        login.read_jwt_key()

    @app.before_request
    def init_cache() -> None:
        """Init the cache before each request."""
        g.cache = Cache()

    @app.before_request
    def debug_info() -> None:
        """Print some debugging info about the incoming request."""
        # Don't log options and advance-queue requests (too much spam)
        if request.method != "OPTIONS" and not request.url.endswith("/advance-queue"):
            log_msg = [f"Request: {request.method} {request.url}"]
            if request.values:
                args = ", ".join(f"{k}: {v}" for k, v in request.values.items())
                log_msg.append(f"{' ' * 29}Args: {args}")
            if request.files:
                files = ", ".join(str(i) for i in request.files.to_dict(flat=False).values())
                log_msg.append(f"{' ' * 29}Files: {files}")
            app.logger.debug("\n".join(log_msg))

    @app.after_request
    def cleanup(response: Response) -> Response:
        """Cleanup temporary files after request."""
        if "request_id" in g:
            local_user_dir = Path(app.instance_path) / app.config.get("TMP_DIR") / g.request_id
            shutil.rmtree(str(local_user_dir), ignore_errors=True)
        return response

    @app.errorhandler(400)
    def handle_400_error(error: Exception) -> tuple[Response, int]:
        """Handle 400 errors (bad request)."""
        logger.warning("Bad Request: %s", error)
        return utils.response("Bad request", err=True, return_code="bad_request"), 400

    @app.errorhandler(404)
    def handle_404_error(error: Exception) -> tuple[Response, int]:
        """Handle 404 errors (not found)."""
        logger.warning("Not Found: %s", error)
        return utils.response("Page not found", err=True, return_code="page_not_found"), 404

    @app.errorhandler(413)
    def handle_413_error(_error: Exception) -> tuple[Response, int]:
        """Handle 413 errors (request_entity_too_large)."""
        max_size = app.config.get("MAX_CONTENT_LENGTH", 0)
        h_max_size = str(round(app.config.get("MAX_CONTENT_LENGTH", 0) / 1024 / 1024, 3))
        return utils.response(
            f"Request data too large (max {h_max_size} MB per upload)",
            max_content_length=max_size,
            err=True,
            return_code="data_too_large",
        ), 413

    @app.errorhandler(Exception)
    def handle_exception(exception: Exception) -> tuple[Response, int]:
        """Handle all unhandled exceptions and return a traceback."""
        tb = traceback.format_exc()
        logger.error("%s: %s", exception, tb)
        return utils.response("Something went wrong", err=True, info=tb, return_code="something_went_wrong"), 500

    # Register routes from blueprints
    app.register_blueprint(routes.bp)
    app.register_blueprint(process_routes.bp)
    app.register_blueprint(storage_routes.bp)
    app.register_blueprint(login.bp)
    app.register_blueprint(metadata_routes.bp)

    return app
