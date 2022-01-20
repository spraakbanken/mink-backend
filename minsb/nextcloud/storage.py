"""Functions related to storage on Nextcloud."""

import os
import zipfile
from pathlib import Path

from dateutil.parser import parse
from flask import current_app as app

from minsb import paths


def list_corpora(oc):
    """List the available corpora in the corpora dir."""
    path = app.config.get("NC_CORPORA_DIR")
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
        # The get_last_modified method is lacking time zone info, so we don't use it.
        # Get last modified date in UTC
        last_modified = parse(elem.attributes["{DAV:}getlastmodified"]).isoformat()
        full_path = elem.get_path()
        if elem.get_content_type() != "httpd/unix-directory":
            full_path = str(Path(full_path) / elem.get_name())
        objlist.append(
            {"name": elem.get_name(), "type": elem.get_content_type(),
             "last_modified": last_modified, "size:": elem.get_size(), "path": full_path})
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
        new_path = os.path.join(user_dir, *parts[2:])
        unix_timestamp = int(parse(f.get("last_modified")).astimezone().timestamp())
        file_index[new_path] = unix_timestamp
    return file_index
