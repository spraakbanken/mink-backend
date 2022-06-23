"""Login functions."""

import functools
import json
import re
import time
from pathlib import Path

import jwt
import requests
import shortuuid
from flask import current_app as app
from flask import g, request

from mink import exceptions, utils


def login(require_init=False, include_read=False, require_corpus_id=True, require_corpus_exists=True):
    """Attempt to login on sb-auth.

    Args:
        require_init (bool, optional): Requires Mink to be initialised. Defaults to False.
        include_read (bool, optional): Include corpora that the user has read access to. Defaults to False.
        require_corpus_id (bool, optional): This route requires the user to supply a corpus ID. Defaults to True.
        require_corpus_exists (bool, optional): This route requires that the supplied corpus ID occurs in the JWT.
            Defaults to True.
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
                user, corpora = _get_corpora(auth_token, include_read)
                # Store random ID in app context, used for temporary storage
                g.request_id = shortuuid.uuid()

                if not require_corpus_id:
                    return function(None, user, corpora, auth_token, *args, **kwargs)

                # Check if corpus ID was provided
                corpus_id = request.args.get("corpus_id") or request.form.get("corpus_id")
                if not corpus_id:
                    return utils.response("No corpus ID provided", err=True), 400

                # Check if corpus exists
                if not require_corpus_exists:
                    return function(None, user, corpora, corpus_id, auth_token)

                # Check if user is admin for corpus
                if corpus_id not in corpora:
                    return utils.response(f"Corpus '{corpus_id}' does not exist or you do not have permission to edit it",
                                          err=True), 400

                return function(None, user, corpora, corpus_id, auth_token)

            except Exception as e:
                return utils.response("Failed to authenticate", err=True, info=str(e)), 401
        return wrapper
    return decorator


def read_jwt_key():
    """Read and return the public key for validating JWTs."""
    app.config["JWT_KEY"] = open(Path(app.instance_path) / app.config.get("SBAUTH_PUBKEY_FILE")).read()


def _get_corpora(auth_token, include_read=False):
    """Check validity of auth_token and get Mink corpora that user has write access for."""
    corpora = []
    user_token = jwt.decode(auth_token, key=app.config.get("JWT_KEY"), algorithms=["RS256"])
    if user_token["exp"] < time.time():
        return utils.response("The provided JWT has expired", err=True), 401

    min_level = "WRITE"
    if include_read:
        min_level = "READ"
    if "scope" in user_token and "corpora" in user_token["scope"]:
        for corpus, level in user_token["scope"]["corpora"].items():
            if level >= user_token["levels"][min_level] and corpus.startswith(app.config.get("RESOURCE_PREFIX")):
                corpora.append(corpus)
    user = re.sub(r"[^\w\-_\.]", "", (user_token["idp"] + "-" + user_token["sub"]))
    return user, corpora


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
