"""Utility functions."""

import datetime
import functools
import json
import os
import zipfile

import owncloud
from flask import Response
from flask import current_app as app
from flask import request


def response(msg, err=False, **kwargs):
    """Create json error response."""
    res = {"status": "error" if err else "success", "message": msg}
    for key, value in kwargs.items():
        res[key] = value
    return Response(json.dumps(res, ensure_ascii=False), mimetype="application/json")


def login(require_init=True, require_corpus_id=True, require_corpus_exists=True):
    """Attempt to login on Nextcloud.

    Optionally require that Min SB is initialized, corpus ID was provided and corpus exists.
    """
    def decorator(function):
        @functools.wraps(function)  # Copy original function's information, needed by Flask
        def wrapper(*args, **kwargs):
            if not request.authorization:
                return response("No login credentials provided!", err=True), 401
            username = request.authorization.get("username")
            password = request.authorization.get("password")
            if not (username and password):
                return response("Username or password missing!", err=True), 401
            try:
                oc = owncloud.Client(app.config.get("NC_DOMAIN", ""))
                oc.login(username, password)
                if not require_init:
                    return function(oc, *args, **kwargs)

                # Check if Min SB was initialized
                try:
                    corpora = list_corpora(oc)
                except Exception as e:
                    return response("Failed to access corpora dir! "
                                    "Make sure Min Språkbank is initialized!", err=True, info=str(e)), 401

                if not require_corpus_id:
                    return function(oc, corpora, *args, **kwargs)

                # Check if corpus ID was provided
                corpus_id = request.args.get("corpus_id") or request.form.get("corpus_id")
                if not corpus_id:
                    return response("No corpus ID provided!", err=True), 404

                if not require_corpus_exists:
                    return function(oc, corpora, corpus_id)

                # Check if corpus exists
                if corpus_id not in corpora:
                    return response(f"Corpus '{corpus_id}' does not exist!", err=True), 404

                return function(oc, corpora, corpus_id)

            except Exception as e:
                return response("Failed to authenticate!", err=True, info=str(e)), 401
        return wrapper
    return decorator


def list_corpora(oc):
    """List the available corpora in the corpora dir."""
    path = app.config.get("CORPORA_DIR")
    corpora = []
    for elem in oc.list(path):
        if elem.get_content_type() == "httpd/unix-directory":
            corpora.append(elem.get_name())
    return corpora


def list_contents(oc, directory):
    """List file in a directory recursively."""
    listing = oc.list(directory, depth="infinity")
    objlist = []
    for elem in listing:
        if elem.get_content_type() != "httpd/unix-directory":
            objlist.append(
                {"name": elem.get_name(), "type": elem.get_content_type(),
                 "last_modified": str(elem.get_last_modified()), "path": elem.get_path()})
    return objlist


def download_dir(oc, nc_dir, local_dir, user, corpus_id, contents):
    """Download directory as zip, unzip and update timestamps."""
    zipf = os.path.join(local_dir, corpus_id) + ".zip"
    oc.get_directory_as_zip(nc_dir, zipf)
    with zipfile.ZipFile(zipf, "r") as f:
        f.extractall(local_dir)

    LOCAL_TIMEZONE = datetime.datetime.now(datetime.timezone.utc).astimezone().tzinfo

    # Create file index with timestamps
    new_contents = {}
    for f in contents:
        parts = f.get("path").split("/")
        new_path = os.path.join(app.instance_path, app.config.get("TMP_DIR"), user, *parts[2:], f.get("name"))
        datetime_obj = datetime.datetime.strptime(f.get("last_modified"), "%Y-%m-%d %H:%M:%S")
        unix_timestamp = int(datetime_obj.replace(tzinfo=LOCAL_TIMEZONE).timestamp())
        new_contents[new_path] = unix_timestamp

    # Change timestamps of local files
    for (root, _dirs, files) in os.walk(os.path.join(local_dir, corpus_id)):
        for f in files:
            full_path = os.path.join(root, f)
            timestamp = new_contents.get(full_path)
            os.utime(full_path, (timestamp, timestamp))
