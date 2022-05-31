"""Login functions."""

import functools
import json
import shlex
import time
from pathlib import Path

import jwt
import requests
from flask import current_app as app
from flask import request

from minsb import exceptions, utils


def login(require_init=False, require_corpus_id=True, require_corpus_exists=True):
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
                user, corpora = _get_corpora(auth_token)
                user = shlex.quote(user)

                if not require_corpus_id:
                    return function(None, user, corpora, auth_token, *args, **kwargs)

                # Check if corpus ID was provided
                corpus_id = request.args.get("corpus_id") or request.form.get("corpus_id")
                if not corpus_id:
                    return utils.response("No corpus ID provided", err=True), 404
                corpus_id = shlex.quote(corpus_id)

                if not require_corpus_exists:
                    return function(None, user, corpora, corpus_id, auth_token)

                # Check if corpus exists
                if corpus_id not in corpora:
                    return utils.response(f"Corpus '{corpus_id}' does not exist or you do not have permission to edit it",
                                          err=True), 404

                return function(None, user, corpora, corpus_id, auth_token)

            except Exception as e:
                return utils.response("Failed to authenticate", err=True, info=str(e)), 401
        return wrapper
    return decorator


def read_jwt_key():
    """Read and return the public key for validating JWTs."""
    app.config["JWT_KEY"] = open(Path(app.instance_path) / app.config.get("SBAUTH_PUBKEY_FILE")).read()


def _get_corpora(auth_token):
    """Check validity of auth_token and get corpora that user is admin for."""
    corpora = []
    user_token = jwt.decode(auth_token, key=app.config.get("JWT_KEY"), algorithms=["RS256"])
    if user_token["exp"] < time.time():
        return utils.response("The provided JWT has expired", err=True), 401

    # import json
    # print(json.dumps(user_token, ensure_ascii=True, indent=4))

    if "scope" in user_token and "corpora" in user_token["scope"]:
        for corpus, level in user_token["scope"]["corpora"].items():
            if user_token["levels"]["ADMIN"] <= level:
                corpora.append(corpus)
    user = user_token["name"]
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
    # TODO: what status is returned if corpus ID exists?
    if status != 200:
        raise exceptions.CorpusExists


def remove_resource(auth_token, resource_id):
    """Remove a resource from sb-auth."""
    # TODO: not finished
    url = app.config.get("SBAUTH_URL") + resource_id
    api_key = app.config.get("SBAUTH_API_KEY")
    headers = {"Authorization": f"apikey {api_key}"}
    data = {"jwt": auth_token}
    try:
        # curl  https://spraakbanken.gu.se/auth/resources/resource/<resource_id> -XDELETE -H "Authorization: apikey <secret key>"
        r = requests.delete(url, headers=headers, data=json.dumps(data))
    except Exception as e:
        # TODO: what now?
        print(e)
    pass
