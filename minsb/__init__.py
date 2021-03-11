"""Instanciation of flask app."""

import logging
import shutil
import sys
import time
from pathlib import Path

from flask import Flask, g, request
from flask_cors import CORS

from minsb import queue, utils


def create_app():
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

    # Configure logger
    logfmt = "%(asctime)-15s - %(levelname)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    if app.config.get("DEBUG"):
        logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, format=logfmt, datefmt=datefmt)
    else:
        today = time.strftime("%Y-%m-%d")
        logdir = Path("instance") / "logs"
        logfile = logdir / f"minsb-{today}.log"
        logdir.mkdir(exist_ok=True)
        # Create log file if it does not exist
        if not logfile.is_file():
            with open(logfile, "w") as f:
                now = time.strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"{now} CREATED DEBUG FILE\n\n")

        log_level = getattr(logging, app.config.get("LOG_LEVEL", "INFO").upper())
        logging.basicConfig(filename=logfile, level=log_level, format=logfmt, datefmt=datefmt)

    # Connect to memcached and init job queue
    with app.app_context():
        utils.connect_to_memcached()
        queue.init_queue()

    @app.before_request
    def before_request():
        """Init variables in app context (as backup for memcached) and try to reconnect to memcached if necessary."""
        g.queue_initialized = False
        g.job_queue = []
        if app.config["cache_client"] is None:
            utils.connect_to_memcached()

    @app.after_request
    def cleanup(response):
        """Cleanup temporary files after request."""
        if request.authorization:
            user = request.authorization.get("username")
            local_user_dir = Path(app.instance_path) / app.config.get("TMP_DIR") / user
            shutil.rmtree(str(local_user_dir), ignore_errors=True)
        return response

    # Register blueprints
    from .views import general, nextcloud, sparv
    app.register_blueprint(general.bp)
    app.register_blueprint(nextcloud.bp)
    app.register_blueprint(sparv.bp)

    return app
