"""Functions related to storage on Sparv server."""

import mimetypes
import os
import shlex
import subprocess
from pathlib import Path
from typing import Union

from dateutil.parser import parse
from flask import current_app as app

from mink import utils
from mink.sparv import utils as sparv_utils

local = True


def list_contents(_ui, directory: Union[Path, str], exclude_dirs=True):
    """List files in directory on Sparv server recursively."""
    objlist = []
    directory_quoted = shlex.quote(str(directory))
    p = utils.ssh_run(f"test -d {directory_quoted} && cd {directory_quoted} && "
                      f"find * -exec ls -lgGd --time-style=full-iso {{}} \\;")
    if p.stderr:
        raise Exception(f"Failed to list contents of '{directory}': {p.stderr.decode()}")

    contents = p.stdout.decode()
    for line in contents.split("\n"):
        if not line.strip():
            continue
        permissions, _, size, date, time, tz, obj_path = line.split()
        f = Path(obj_path)
        mod_time = parse(f"{date} {time} {tz}").isoformat(timespec="seconds")
        is_dir = permissions.startswith("d")
        mimetype = mimetypes.guess_type(f)[0] or "unknown"
        if is_dir:
            if exclude_dirs:
                continue
            mimetype = "directory"
        objlist.append({
            "name": f.name, "type": mimetype,
            "last_modified": mod_time, "size": size, "path": obj_path
        })
    return objlist


def download_file(_ui, remote_file_path: str, local_file: Path):
    """Download a file from the Sparv server."""
    if not _is_valid_path(remote_file_path):
        raise Exception(f"You don't have permission to download '{remote_file_path}'")

    user, host = _get_login()
    p = subprocess.run(["rsync", f"{user}@{host}:{remote_file_path}", f"{local_file}"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.stderr:
        raise Exception(f"Failed to download '{remote_file_path}': {p.stderr.decode()}")


def get_file_contents(_ui, filepath):
    """Get contents of file at 'filepath'."""
    p = utils.ssh_run(f"cat {shlex.quote(str(filepath))}")
    if p.stderr:
        raise Exception(f"Failed to retrieve contents for '{filepath}': {p.stderr.decode()}")

    return p.stdout.decode()


def write_file_contents(_ui, filepath: str, file_contents):
    """Write contents to a new file on the Sparv server."""
    if not _is_valid_path(filepath):
        raise Exception(f"You don't have permission to edit '{filepath}'")

    p = utils.ssh_run(f"echo {shlex.quote(file_contents)} >{shlex.quote(str(filepath))}")
    if p.stderr:
        raise Exception(f"Failed to upload contents to '{filepath}': {p.stderr.decode()}")


def download_dir(_ui, remote_dir, local_dir, corpus_id, file_index=None, zipped=False, zippath=None):
    """Download remote_dir on Sparv server to local_dir by rsyncing."""
    if not _is_valid_path(remote_dir):
        raise Exception(f"You don't have permission to download '{remote_dir}'")

    if not local_dir.is_dir():
        raise Exception(f"'{local_dir}' is not a directory")

    if zipped and zippath is None:
        raise Exception("Parameter zippath needs to be supplied when 'zipped=True'")

    user, host = _get_login()
    p = subprocess.run(["rsync", "--recursive", f"{user}@{host}:{remote_dir}/", f"{local_dir}"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.stderr:
        raise Exception(f"Failed to download '{remote_dir}': {p.stderr.decode()}")

    if not zipped:
        return local_dir

    utils.create_zip(local_dir, zippath)
    return zippath


def upload_dir(_ui, remote_dir, local_dir, _corpus_id, _user, _file_index, delete=False):
    """Upload local dir to remote_dir on Sparv server by rsyncing.

    Args:
        remote_dir: Directory on Sparv to upload to.
        local_dir: Local directory to upload.
        delete: If set to True delete files that do not exist in local_dir.
    """
    if not _is_valid_path(remote_dir):
        raise Exception(f"You don't have permission to edit '{remote_dir}'")

    if not local_dir.is_dir():
        raise Exception(f"'{local_dir}' is not a directory")

    if delete:
        args = ["--recursive", "--delete", f"{local_dir}/"]
    else:
        args = ["--recursive", f"{local_dir}/"]

    _make_dir(remote_dir)
    user, host = _get_login()
    p = subprocess.run(["rsync"] + args + [f"{user}@{host}:{remote_dir}"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.stderr:
        raise Exception(f"Failed to upload to '{remote_dir}': {p.stderr.decode()}")


def create_file_index(contents, user):
    """Convert Nextcloud contents list to a file index with local paths and timestamps."""
    # TODO: Is this needed for anything?
    file_index = {}
    for f in contents:
        parts = f.get("path").split("/")
        user_dir = str(utils.get_corpora_dir(user))
        new_path = os.path.join(user_dir, *parts[2:])
        unix_timestamp = int(parse(f.get("last_modified")).astimezone().timestamp())
        file_index[new_path] = unix_timestamp
    return file_index


def remove_dir(_ui, path):
    """Remove directory on 'path' from Sparv server."""
    if not _is_valid_path(path):
        raise Exception(f"You don't have permission to remove '{path}'")

    p = utils.ssh_run(f"test -d {shlex.quote(str(path))} && rm -r {shlex.quote(str(path))}")
    if p.stderr:
        raise Exception(f"Failed to remove corpus dir on Sparv server: {p.stderr.decode()}")


def remove_file(_ui, path):
    """Remove file on 'path' from Sparv server."""
    if not _is_valid_path(path):
        raise Exception(f"You don't have permission to remove '{path}'")

    p = utils.ssh_run(f"test -f {shlex.quote(str(path))} && rm {shlex.quote(str(path))}")
    if p.stderr:
        raise Exception(f"Failed to remove file '{path}' on Sparv server: {p.stderr.decode()}")


def _get_login():
    user = app.config.get("SPARV_USER")
    host = app.config.get("SPARV_HOST")
    return user, host


def _is_valid_path(path):
    """Check that path points to a corpus dir (or a descendant) and not to e.g. the entire Sparv data dir."""
    return get_corpora_dir(None) in Path(path).parents


################################################################################
# Get paths on Sparv server
################################################################################

def get_corpora_dir(_ui, mkdir=False):
    """Get corpora directory."""
    corpora_dir = sparv_utils.get_corpora_dir()
    if mkdir:
        _make_dir(corpora_dir)
    return corpora_dir


def get_corpus_dir(_ui, corpus_id, mkdir=False):
    """Get dir for given corpus."""
    corpus_dir = sparv_utils.get_corpus_dir(corpus_id)
    if mkdir:
        _make_dir(corpus_dir)
    return corpus_dir


def get_export_dir(_ui, corpus_id, mkdir=False):
    """Get export dir for given corpus."""
    export_dir = sparv_utils.get_export_dir(corpus_id)
    if mkdir:
        _make_dir(export_dir)
    return export_dir


def get_work_dir(_ui, corpus_id, mkdir=False):
    """Get sparv workdir for given corpus."""
    work_dir = sparv_utils.get_work_dir(corpus_id)
    if mkdir:
        _make_dir(work_dir)
    return work_dir


def get_source_dir(_ui, corpus_id: str, mkdir: bool = False) -> Path:
    """Get source dir for given corpus."""
    source_dir = sparv_utils.get_source_dir(corpus_id)
    if mkdir:
        _make_dir(source_dir)
    return source_dir


def get_config_file(_ui, corpus_id):
    """Get path to corpus config file."""
    return sparv_utils.get_config_file(corpus_id)


def _make_dir(dirpath):
    """Create directory on Sparv server."""
    p = utils.ssh_run(f"mkdir -p {shlex.quote(str(dirpath))}")
    if p.stderr:
        raise Exception(f"Failed to create corpus dir on Sparv server! {p.stderr.decode()}")
