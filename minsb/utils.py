"""Utility functions."""

import json

import owncloud
from flask import current_app


def error_response(msg):
    """Create json error response."""
    return json.dumps({
        "status": "error",
        "message": msg
    }, ensure_ascii=False)


def success_response(msg, **kwargs):
    """Create json success response."""
    response = {
        "status": "success",
        "message": msg
    }
    for key, value in kwargs.items():
        response[key] = value
    return json.dumps(response, ensure_ascii=False)


def login(request):
    """Attempt to login on Nextcloud."""
    if not request.authorization:
        raise Exception("No login credentials provided!")
    username = request.authorization.get("username")
    password = request.authorization.get("password")
    if not (username and password):
        raise Exception("Username or password missing!")
    oc = owncloud.Client(current_app.config.get("NC_DOMAIN", ""))
    oc.login(username, password)
    return oc


def list_corpora(oc):
    """List the available corpora in the corpora dir."""
    path = current_app.config.get("CORPORA_DIR")
    corpora = []
    for elem in oc.list(path):
        if elem.get_content_type() == "httpd/unix-directory":
            corpora.append(elem.get_name())
    return corpora
