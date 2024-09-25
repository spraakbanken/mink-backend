"""Instantiation of flask app."""

__version__ = "1.1.0"

import logging
import shutil
import sys
import time
from pathlib import Path

from flask import Flask, g, request
from flask_cors import CORS

from mink.core import extensions, registry, utils
from mink.memcached.cache import Cache
from mink.sb_auth.login import read_jwt_key

from .core import routes as general_routes
from .metadata import metadata_routes
from .sb_auth import login as login_routes
from .sparv import process_routes, storage_routes


def create_app(debug=False):
    """Instantiate app."""
    app = Flask(__name__)

    # Enable CORS
    CORS(app, supports_credentials=True)

    # Set default config
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
    logfmt = "%(asctime)-15s - %(levelname)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    if debug:
        logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, format=logfmt, datefmt=datefmt)
    else:
        today = time.strftime("%Y-%m-%d")
        logdir = Path("instance") / "logs"
        logfile = logdir / f"mink-{today}.log"
        logdir.mkdir(exist_ok=True)
        # Create log file if it does not exist
        if not logfile.is_file():
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            logfile.write_text(f"{now} CREATED DEBUG FILE\n\n")

        log_level = getattr(logging, app.config.get("LOG_LEVEL", "INFO").upper())
        logging.basicConfig(filename=logfile, level=log_level, format=logfmt, datefmt=datefmt)

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
    else:
        app.logger.warning("NOT tracking to Matomo, please set TRACKING_MATOMO_URL and TRACKING_MATOMO_IDSITE.")
    with app.app_context():
        # Connect to cache and init the resource registry
        g.cache = Cache()
        registry.initialize()

        # Save JWT key in memory
        read_jwt_key()

    @app.before_request
    def init_cache():
        """Init the cache before each request."""
        g.cache = Cache()

    @app.before_request
    def debug_info():
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
    def cleanup(response):
        """Cleanup temporary files after request."""
        if "request_id" in g:
            local_user_dir = Path(app.instance_path) / app.config.get("TMP_DIR") / g.request_id
            shutil.rmtree(str(local_user_dir), ignore_errors=True)
        return response

    @app.errorhandler(413)
    def request_entity_too_large(_error):
        """Handle large requests."""
        max_size = app.config.get("MAX_CONTENT_LENGTH", 0)
        h_max_size = str(round(app.config.get("MAX_CONTENT_LENGTH", 0) / 1024 / 1024, 3))
        return utils.response(
            f"Request data too large (max {h_max_size} MB per upload)",
            max_content_length=max_size,
            err=True,
            return_code="data_too_large",
        ), 413

    # Register routes from blueprints
    app.register_blueprint(general_routes.bp)
    app.register_blueprint(process_routes.bp)
    app.register_blueprint(storage_routes.bp)
    app.register_blueprint(login_routes.bp)
    app.register_blueprint(metadata_routes.bp)

    return app
