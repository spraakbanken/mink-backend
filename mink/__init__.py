"""Instanciation of flask app."""

import logging
import shutil
import sys
import time
from pathlib import Path

from flask import Flask, g, request
from flask_cors import CORS

from mink import corpus_registry, queue, utils
from mink.memcached.cache import Cache
from mink.sb_auth.login import read_jwt_key


def create_app(debug=False):
    """Instanciate app."""
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
            with open(logfile, "w") as f:
                now = time.strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"{now} CREATED DEBUG FILE\n\n")

        log_level = getattr(logging, app.config.get("LOG_LEVEL", "INFO").upper())
        logging.basicConfig(filename=logfile, level=log_level, format=logfmt, datefmt=datefmt)

    with app.app_context():
        # Connect to cache and init job queue
        g.cache = Cache()
        queue.init()
        corpus_registry.init()

        # Save JWT key in memory
        read_jwt_key()

    @app.before_request
    def init_cache():
        """Init the cache before each request."""
        g.cache = Cache()

    @app.before_request
    def debug_info():
        """Print some debugging info about the incoming request."""
        app.logger.debug(f"URL:    {request.url}")
        if request.values:
            app.logger.debug(f"Values: {list(request.values.items())}")
        if request.files:
            app.logger.debug(f"Files:  {request.files}")

    @app.after_request
    def cleanup(response):
        """Cleanup temporary files after request."""
        if "request_id" in g:
            local_user_dir = Path(app.instance_path) / app.config.get("TMP_DIR") / g.request_id
            shutil.rmtree(str(local_user_dir), ignore_errors=True)
        return response

    @app.errorhandler(413)
    def request_entity_too_large(error):
        """Handle large requests."""
        max_size = app.config.get('MAX_CONTENT_LENGTH', 0)
        h_max_size = str(round(app.config.get('MAX_CONTENT_LENGTH', 0) / 1024 / 1024, 3))
        return utils.response(
            f"Request data too large (max {h_max_size} MB per upload)", max_content_length=max_size, err=True), 413

    # Register routes from blueprints
    from . import routes as general_routes
    app.register_blueprint(general_routes.bp)
    from .sparv import process_routes
    app.register_blueprint(process_routes.bp)
    from .sparv import storage_routes
    app.register_blueprint(storage_routes.bp)
    from .sb_auth import login as login_routes
    app.register_blueprint(login_routes.bp)

    return app
