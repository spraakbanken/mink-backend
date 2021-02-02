"""Utility functions."""

import datetime
import functools
import json
import os
import shlex
import zipfile
from pathlib import Path

import owncloud
from dateutil.parser import parse
from flask import Response
from flask import current_app as app
from flask import request

from minsb import paths


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
            user = request.authorization.get("username")
            password = request.authorization.get("password")
            if not (user and password):
                return response("Username or password missing!", err=True), 401
            try:
                oc = owncloud.Client(app.config.get("NC_DOMAIN", ""))
                oc.login(user, password)

                user = shlex.quote(user)
                if not require_init:
                    return function(oc, user, *args, **kwargs)

                # Check if Min SB was initialized
                try:
                    corpora = list_corpora(oc)
                except Exception as e:
                    return response("Failed to access corpora dir! "
                                    "Make sure Min Språkbank is initialized!", err=True, info=str(e)), 401

                if not require_corpus_id:
                    return function(oc, user, corpora, *args, **kwargs)

                # Check if corpus ID was provided
                corpus_id = shlex.quote(request.args.get("corpus_id") or request.form.get("corpus_id"))
                if not corpus_id:
                    return response("No corpus ID provided!", err=True), 404

                if not require_corpus_exists:
                    return function(oc, user, corpora, corpus_id)

                # Check if corpus exists
                if corpus_id not in corpora:
                    return response(f"Corpus '{corpus_id}' does not exist!", err=True), 404

                return function(oc, user, corpora, corpus_id)

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


def list_contents(oc, directory, exclude_dirs=True):
    """List file in a directory recursively."""
    listing = oc.list(directory, depth="infinity")
    objlist = []
    for elem in listing:
        # The get_last_modified method is lacking time zone info, so we don't use it
        last_modified = str(elem.attributes["{DAV:}getlastmodified"])
        objlist.append(
            {"name": elem.get_name(), "type": elem.get_content_type(),
             "last_modified": last_modified, "path": elem.get_path()})
    if exclude_dirs:
        objlist = [i for i in objlist if i.get("type") != "httpd/unix-directory"]
    return objlist


def download_dir(oc, nc_dir, local_dir, corpus_id, file_index):
    """Download directory as zip, unzip and update timestamps."""
    zipf = os.path.join(local_dir, corpus_id) + ".zip"
    oc.get_directory_as_zip(nc_dir, zipf)
    with zipfile.ZipFile(zipf, "r") as f:
        f.extractall(local_dir)

    # Change timestamps of local files
    for (root, _dirs, files) in os.walk(os.path.join(local_dir, corpus_id)):
        for f in files:
            full_path = os.path.join(root, f)
            timestamp = file_index.get(full_path)
            os.utime(full_path, (timestamp, timestamp))


def upload_dir(oc, nc_dir, local_dir, corpus_id, user, nc_file_index, delete=False):
    """Upload local dir to nc_dir on Nextcloud by adding new files and replacing newer ones.

    Args:
        oc: Owncloud instance.
        nc_dir: Nextcloud directory to upload to.
        local_dir: Local directory to upload.
        corpus_id: The corpus ID.
        user: The user name.
        nc_file_index: Dictionary created by create_file_index().
        delete: If set to True delete files that do not exist in local_dir.
    """
    local_file_index = []  # Used for file deletions
    local_path_prefix = str(paths.get_corpus_dir(user=user, corpus_id=corpus_id))

    for root, dirs, files in os.walk(local_dir):
        # Create missing directories
        for directory in dirs:
            full_path = os.path.join(root, directory)
            if full_path not in nc_file_index:
                nextcloud_path = os.path.join(nc_dir, full_path[len(local_path_prefix) + 1:])
                oc.mkdir(nextcloud_path)

        for f in files:
            full_path = os.path.join(root, f)
            local_file_index.append(full_path)
            nextcloud_path = os.path.join(nc_dir, full_path[len(local_path_prefix) + 1:])
            # Copy missing files
            if full_path not in nc_file_index:
                oc.put_file(nextcloud_path, full_path)
            # Update newer files
            else:
                nextcloud_timestamp = nc_file_index.get(full_path)
                local_timestamp = int(os.path.getmtime(full_path))
                if local_timestamp > nextcloud_timestamp:
                    oc.delete(nextcloud_path)
                    oc.put_file(nextcloud_path, full_path)

    # TODO: Take care of deletions


def create_file_index(contents, user):
    """Convert Nextcloud contents list to a file index with local paths and timestamps."""
    file_index = {}
    for f in contents:
        parts = f.get("path").split("/")
        user_dir = str(paths.get_corpora_dir(user=user))
        if f.get("type") != "httpd/unix-directory":
            new_path = os.path.join(user_dir, *parts[2:], f.get("name"))
        else:
            new_path = os.path.join(user_dir, *parts[2:])
        unix_timestamp = int(parse(f.get("last_modified")).astimezone().timestamp())
        file_index[new_path] = unix_timestamp
    return file_index


def create_zip(inpath, outpath):
    """Zip files in inpath into an archive at outpath."""
    zipf = zipfile.ZipFile(outpath, "w")
    for root, _dirs, files in os.walk(inpath):
        for f in files:
            zipf.write(os.path.join(root, f), os.path.relpath(os.path.join(root, f), os.path.join(inpath, "..")))
    zipf.close()


def check_file(filename, valid_extensions=None):
    """Shell escape filename and check if its extension is valid (return False if not)."""
    filename = Path(shlex.quote(filename))
    if valid_extensions:
        if filename.suffix not in valid_extensions:
            return False
    return filename
