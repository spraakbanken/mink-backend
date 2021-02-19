"""Instanciation of flask app."""

import logging
import os
import shutil
import sys

from flask import Flask, request
from flask_cors import CORS
import memcache

from minsb import queue


def create_app():
    """Instanciate app."""
    app = Flask(__name__)

    # Enable CORS
    CORS(app, supports_credentials=True)

    # Set default config
    app.config.from_object("config")

    # Overwrite with instance config
    if os.path.exists(os.path.join(app.instance_path, "config.py")):
        app.config.from_pyfile(os.path.join(app.instance_path, "config.py"))

    # Configure logger
    logfmt = "%(asctime)-15s - %(levelname)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    if app.config.get("DEBUG"):
        logging.basicConfig(stream=sys.stdout, level=logging.DEBUG,
                            format=logfmt, datefmt=datefmt)

    # Connect to memcached
    socket_path = os.path.join(app.instance_path, app.config.get("MEMCACHED_SOCKET"))
    app.config["cache_client"] = memcache.Client([f"unix:{socket_path}"], debug=1)

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
