"""Login functions."""

import functools
import shlex

import owncloud
from flask import current_app as app
from flask import request

from minsb import utils
from minsb.nextcloud import storage


def login(require_init=True, require_corpus_id=True, require_corpus_exists=True):
    """Attempt to login on Nextcloud.

    Optionally require that Min SB is initialized, corpus ID was provided and corpus exists.
    """
    def decorator(function):
        @functools.wraps(function)  # Copy original function's information, needed by Flask
        def wrapper(*args, **kwargs):
            if not request.authorization:
                return utils.response("No login credentials provided", err=True), 401
            user = request.authorization.get("username")
            password = request.authorization.get("password")
            if not (user and password):
                return utils.response("Username or password missing", err=True), 401
            try:
                # Login user and create ui (user instance)
                ui = owncloud.Client(app.config.get("NC_DOMAIN", ""))
                ui.login(user, password)
                # Hack: ui.login() does not seem to raise an error when authentication fails, but ui.list() will.
                dir_listing = ui.list("/")
                app.logger.debug("User '%s' logged in", user)

                user = shlex.quote(user)
                if not require_init:
                    return function(ui, user, dir_listing, *args, **kwargs)

                # Check if Min SB was initialized
                try:
                    corpora = storage.list_corpora(ui)
                except Exception as e:
                    return utils.response("Failed to access corpora dir. "
                                          "Make sure Min Språkbank is initialized", err=True, info=str(e)), 401

                if not require_corpus_id:
                    return function(ui, user, corpora, *args, **kwargs)

                # Check if corpus ID was provided
                corpus_id = request.args.get("corpus_id") or request.form.get("corpus_id")
                if not corpus_id:
                    return utils.response("No corpus ID provided", err=True), 400
                corpus_id = shlex.quote(corpus_id)

                if not require_corpus_exists:
                    return function(ui, user, corpora, corpus_id)

                # Check if corpus exists
                if corpus_id not in corpora:
                    return utils.response(f"Corpus '{corpus_id}' does not exist", err=True), 400

                return function(ui, user, corpora, corpus_id)

            except Exception as e:
                return utils.response("Failed to authenticate", err=True, info=str(e)), 401
        return wrapper
    return decorator
