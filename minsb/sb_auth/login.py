"""Login functions."""

import functools
import shlex
import time
from pathlib import Path

import jwt
from flask import current_app as app
from flask import request

from minsb import utils
from minsb.nextcloud import storage


def login(require_init=True, require_corpus_id=True, require_corpus_exists=True):
    """Attempt to login on sb-auth.

    Optionally require that Min SB is initialized, corpus ID was provided and corpus exists.
    """
    def decorator(function):
        @functools.wraps(function)  # Copy original function's information, needed by Flask
        def wrapper(*args, **kwargs):

            auth_header = request.headers.get("Authorization")
            if not auth_header:
                return utils.response("No login credentials provided", err=True), 401
            try:
                auth_token = auth_header.split(" ")[1]
            except Exception:
                return utils.response("No authorization token provided", err=True), 401

            try:
                permissions = []
                user_token = jwt.decode(auth_token, key=app.config.get("JWT_KEY"), algorithms=["RS256"])
                if user_token["exp"] < time.time():
                    return utils.response("The provided JWT has expired", err=True), 401
                import json
                print(json.dumps(user_token, ensure_ascii=True, indent=4))
                user = user_token["name"]
                email = user_token["email"]
                if "scope" in user_token and "corpora" in user_token["scope"]:
                    for corpus, level in user_token["scope"]["corpora"].items():
                        if user_token["levels"]["READ"] <= level:
                            permissions.append(corpus)
                user = shlex.quote(user)
                if not require_init:
                    return function(None, user, permissions, *args, **kwargs)

                return function(None, user, permissions, *args, **kwargs)

                # Check if Min SB was initialized
                try:
                    corpora = storage.list_corpora(ui)
                except Exception as e:
                    return utils.response("Failed to access corpora dir. "
                                    "Make sure Min Språkbank is initialized", err=True, info=str(e)), 401

            #     if not require_corpus_id:
            #         return function(ui, user, corpora, *args, **kwargs)

            #     # Check if corpus ID was provided
            #     corpus_id = request.args.get("corpus_id") or request.form.get("corpus_id")
            #     if not corpus_id:
            #         return utils.response("No corpus ID provided", err=True), 404
            #     corpus_id = shlex.quote(corpus_id)

            #     if not require_corpus_exists:
            #         return function(ui, user, corpora, corpus_id)

            #     # Check if corpus exists
            #     if corpus_id not in corpora:
            #         return utils.response(f"Corpus '{corpus_id}' does not exist", err=True), 404

            #     return function(ui, user, corpora, corpus_id)

            except Exception as e:
                return utils.response("Failed to authenticate", err=True, info=str(e)), 401
        return wrapper
    return decorator


def read_jwt_key():
    """Read and return the public key for validating JWTs."""
    app.config["JWT_KEY"] = open(Path(app.instance_path) / app.config.get("SBAUTH_PUBKEY_FILE")).read()


def _get_permissions(auth_header, auth_token):
    """Check validity of auth_token and get user permissions."""
