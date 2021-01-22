"""Utility functions."""

import functools
import json

import owncloud
from flask import Response, current_app, request


def error_response(msg):
    """Create json error response."""
    return Response(json.dumps({
        "status": "error",
        "message": msg
    }, ensure_ascii=False), mimetype="application/json")


def success_response(msg, **kwargs):
    """Create json success response."""
    response = {
        "status": "success",
        "message": msg
    }
    for key, value in kwargs.items():
        response[key] = value
    return Response(json.dumps(response, ensure_ascii=False), mimetype="application/json")


def login(require_init=True, require_corpus_id=True, require_corpus_exists=True):
    """Attempt to login on Nextcloud.

    Optionally require that Min SB is initialized, corpus ID was provided and corpus exists.
    """
    def decorator(function):
        @functools.wraps(function)  # Copy original function's information, needed by Flask
        def wrapper(*args, **kwargs):
            if not request.authorization:
                return error_response("No login credentials provided!"), 401
            username = request.authorization.get("username")
            password = request.authorization.get("password")
            if not (username and password):
                return error_response("Username or password missing!"), 401
            try:
                oc = owncloud.Client(current_app.config.get("NC_DOMAIN", ""))
                oc.login(username, password)
                if not require_init:
                    return function(oc, *args, **kwargs)

                # Check if Min SB was initialized
                try:
                    corpora = list_corpora(oc)
                except Exception as e:
                    return error_response("Cannot access corpora dir! "
                                          f"Make sure Min Språkbank is initialized! {e}"), 401

                if not require_corpus_id:
                    return function(oc, corpora, *args, **kwargs)

                # Check if corpus ID was provided
                corpus_id = request.args.get("corpus_id") or request.form.get("corpus_id")
                if not corpus_id:
                    return error_response("No corpus ID provided!"), 404

                if not require_corpus_exists:
                    return function(oc, corpora, corpus_id)

                # Check if corpus exists
                if corpus_id not in corpora:
                    return error_response(f"Corpus '{corpus_id}' does not exist!"), 404

                return function(oc, corpora, corpus_id)

            except Exception as e:
                return error_response(f"Could not authenticate! {e}"), 401
        return wrapper
    return decorator


def list_corpora(oc):
    """List the available corpora in the corpora dir."""
    path = current_app.config.get("CORPORA_DIR")
    corpora = []
    for elem in oc.list(path):
        if elem.get_content_type() == "httpd/unix-directory":
            corpora.append(elem.get_name())
    return corpora
