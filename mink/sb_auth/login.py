"""Login functions."""

import functools
import json
import re
import time
import traceback
from pathlib import Path
import inspect

import jwt
import requests
import shortuuid
from flask import Blueprint
from flask import current_app as app
from flask import g, request, session

from mink import corpus_registry, exceptions, utils

bp = Blueprint("sb_auth_login", __name__)


def login(include_read=False, require_corpus_id=True, require_corpus_exists=True, require_admin=False):
    """Attempt to login on sb-auth.

    Args:
        include_read (bool, optional): Include corpora that the user has read access to. Defaults to False.
        require_corpus_id (bool, optional): This route requires the user to supply a corpus ID. Defaults to True.
        require_corpus_exists (bool, optional): This route requires that the supplied corpus ID occurs in the JWT.
            Defaults to True.
        require_admin (bool, optional): This route requires the user to be a mink admin. Defaults to False.
    """
    def decorator(function):
        @functools.wraps(function)  # Copy original function's information, needed by Flask
        def wrapper():
            # Get the function's params
            params = inspect.signature(function).parameters.keys()

            auth_header = request.headers.get("Authorization")
            if not auth_header:
                return utils.response("No login credentials provided", err=True), 401
            try:
                auth_token = auth_header.split(" ")[1]
            except Exception:
                return utils.response("No authorization token provided", err=True), 401

            try:
                user_id, corpora, mink_admin, username, email = _get_corpora(auth_token, include_read)
                contact = f"{username} <{email}>"
            except Exception as e:
                return utils.response("Failed to authenticate", err=True, info=str(e)), 401

            if require_admin and not mink_admin:
                    return utils.response("Mink admin status could not be confirmed", err=True), 401

            # Give access to all corpora if admin mode is on and user is mink admin
            if session.get("admin_mode") and mink_admin:
                corpora = corpus_registry.get_all()
            else:
                # Turn off admin mode if user is not admin
                session["admin_mode"] = False

            try:
                # Store random ID in app context, used for temporary storage
                g.request_id = shortuuid.uuid()

                if not require_corpus_id:
                    return function(**{k: v for k, v in {"user_id": user_id, "contact": contact, "corpora": corpora,
                                                         "auth_token": auth_token}.items() if k in params})

                # Check if corpus ID was provided
                corpus_id = request.args.get("corpus_id") or request.form.get("corpus_id")
                if not corpus_id:
                    return utils.response("No corpus ID provided", err=True), 400

                # Check if corpus exists
                if not require_corpus_exists:
                    return function(**{k: v for k, v in {"user_id": user_id, "contact": contact, "corpora": corpora,
                                                         "corpus_id": corpus_id, "auth_token": auth_token
                                                        }.items() if k in params})

                # Check if user is admin for corpus
                if corpus_id not in corpora:
                    return utils.response(f"Corpus '{corpus_id}' does not exist or you do not have access to it",
                                          err=True), 404
                return function(**{k: v for k, v in {"user_id": user_id, "contact": contact, "corpora": corpora,
                                                     "corpus_id": corpus_id, "auth_token": auth_token
                                                    }.items() if k in params})

            # Catch everything else and return a traceback
            except Exception as e:
                traceback_str = f"{e}: {''.join(traceback.format_tb(e.__traceback__))}"
                return utils.response("Something went wrong", err=True, info=traceback_str), 500

        return wrapper
    return decorator


@bp.route("/admin-mode-on", methods=["POST"])
@login(require_corpus_exists=False, require_corpus_id=False, require_admin=True)
def admin_mode_on():
    session["admin_mode"] = True
    return utils.response(f"Admin mode turned on")


@bp.route("/admin-mode-off", methods=["POST"])
@login(require_corpus_exists=False, require_corpus_id=False)
def admin_mode_off():
    session["admin_mode"] = False
    return utils.response(f"Admin mode turned off")


def read_jwt_key():
    """Read and return the public key for validating JWTs."""
    app.config["JWT_KEY"] = open(Path(app.instance_path) / app.config.get("SBAUTH_PUBKEY_FILE")).read()


def _get_corpora(auth_token, include_read=False):
    """Check validity of auth_token and get Mink corpora that user has write access for."""
    corpora = []
    mink_admin = False
    user_token = jwt.decode(auth_token, key=app.config.get("JWT_KEY"), algorithms=["RS256"])
    if user_token["exp"] < time.time():
        return utils.response("The provided JWT has expired", err=True), 401

    min_level = "WRITE"
    if include_read:
        min_level = "READ"
    if "scope" in user_token and "corpora" in user_token["scope"]:
        # Check if user is mink admin
        mink_admin = user_token["scope"].get("other", {}).get("mink-admin", 0) >= user_token["levels"]["WRITE"]
        # Get list of corpora
        for corpus, level in user_token["scope"].get("corpora", {}).items():
            if level >= user_token["levels"][min_level] and corpus.startswith(app.config.get("RESOURCE_PREFIX")):
                corpora.append(corpus)
    user = re.sub(r"[^\w\-_\.]", "", (user_token["idp"] + "-" + user_token["sub"]))
    username = user_token.get("name", "")
    email = user_token.get("email", "")
    return user, corpora, mink_admin, username, email


def create_resource(auth_token, resource_id):
    """Create a new resource in sb-auth."""
    url = app.config.get("SBAUTH_URL") + resource_id
    api_key = app.config.get("SBAUTH_API_KEY")
    headers = {"Authorization": f"apikey {api_key}", "Content-Type": "application/json"}
    data = {"jwt": auth_token}
    try:
        r = requests.post(url, headers=headers, data=json.dumps(data))
        status = r.status_code
    except Exception as e:
        raise(e)
    if status == 400:
        raise exceptions.CorpusExists
    elif status != 201:
        message = r.content
        raise Exception(message)


def remove_resource(resource_id) -> bool:
    """Remove a resource from sb-auth."""
    url = app.config.get("SBAUTH_URL") + resource_id
    api_key = app.config.get("SBAUTH_API_KEY")
    headers = {"Authorization": f"apikey {api_key}"}
    try:
        r = requests.delete(url, headers=headers)
        status = r.status_code
    except Exception as e:
        raise e
    if status == 204:
        return True
    elif status == 400:
        # Corpus does not exist
        return False
    else:
        message = r.content
        raise Exception(message)
