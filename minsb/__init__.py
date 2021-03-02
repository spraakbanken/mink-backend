"""Instanciation of flask app."""

import logging
import os
import shutil
import sys
import time

from flask import Flask, request
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
    app.config['JSON_SORT_KEYS'] = False

    # Overwrite with instance config
    if os.path.exists(os.path.join(app.instance_path, "config.py")):
        app.config.from_pyfile(os.path.join(app.instance_path, "config.py"))

    # Configure logger
    logfmt = "%(asctime)-15s - %(levelname)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    if app.config.get("DEBUG"):
        logging.basicConfig(stream=sys.stdout, level=logging.DEBUG,
                            format=logfmt, datefmt=datefmt)
    else:
        today = time.strftime("%Y-%m-%d")
        logdir = os.path.join(app.instance_path, "logs")
        logfile = os.path.join(logdir, f"{today}.log")
        # Create log dir if it does not exist
        if not os.path.exists(logdir):
            os.makedirs(logdir)
        # Create log file if it does not exist
        if not os.path.isfile(logfile):
            with open(logfile, "w") as f:
                now = time.strftime("%Y-%m-%d %H:%M:%S")
                f.write("%s CREATED DEBUG FILE\n\n" % now)
        logging.basicConfig(filename=logfile, level=logging.INFO,
                            format=logfmt, datefmt=datefmt)

    # Connect to memcached
    with app.app_context():
        utils.connect_to_memcached()

    # Init job queue
    with app.app_context():
        queue.init_queue()

    @app.after_request
    def cleanup(response):
        """Cleanup temporary files after request."""
        if request.authorization:
            user = request.authorization.get("username")
            local_user_dir = os.path.join(app.instance_path, app.config.get("TMP_DIR"), user)
            shutil.rmtree(local_user_dir, ignore_errors=True)
        return response

    # Register blueprints
    from .views import general, nextcloud, sparv
    app.register_blueprint(general.bp)
    app.register_blueprint(nextcloud.bp)
    app.register_blueprint(sparv.bp)

    return app
