"""Functions related to storage on storage server."""

import mimetypes
import shlex
import subprocess
from pathlib import Path
from typing import Optional, Union

from dateutil.parser import parse
from flask import current_app as app

from mink.core import utils


# def list_contents(directory: Union[Path, str], exclude_dirs: bool = True,
#                   blacklist: Optional[list] = None):
#     """
#     List files in directory on storage server recursively.
#     If a blacklist is specified, exclude paths that match anything on the blacklist.
#     """
#     objlist = []
#     directory_quoted = shlex.quote(str(directory))
#     p = utils.ssh_run(f"test -d {directory_quoted} && cd {directory_quoted} && "
#                       f"find . -exec ls -lgGd --time-style=full-iso {{}} \\;")
#     if p.stderr:
#         raise Exception(f"Failed to list contents of '{directory}': {p.stderr.decode()}")

#     contents = p.stdout.decode()
#     for line in contents.split("\n"):
#         if not line.strip():
#             continue
#         permissions, _, size, date, time, tz, obj_path = line.split(maxsplit=6)
#         if obj_path == ".":
#             continue
#         f = Path(obj_path)
#         mod_time = parse(f"{date} {time} {tz}").isoformat(timespec="seconds")
#         is_dir = permissions.startswith("d")
#         mimetype = mimetypes.guess_type(str(f))[0] or "unknown"
#         if is_dir:
#             if exclude_dirs:
#                 continue
#             mimetype = "directory"
#         if blacklist:
#             if any(Path(f.parts[0]).match(item) for item in blacklist):
#                 continue
#         objlist.append({
#             "name": f.name, "type": mimetype, "last_modified": mod_time, "size": int(size), "path": obj_path[2:]
#         })
#     return objlist


def download_file(remote_file_path: str, local_file: Path, resource_id: str, ignore_missing: bool = False):
    """Download a file from the storage server."""
    if not _is_valid_path(remote_file_path, resource_id):
        raise Exception(f"You don't have permission to download '{remote_file_path}'")

    user, host = _get_login()
    cmd = ["rsync", "--protect-args"]
    if ignore_missing:
        cmd.append("--ignore-missing-args")
    cmd += [f"{user}@{host}:{remote_file_path}", f"{local_file}"]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.stderr:
        raise Exception(f"Failed to download '{remote_file_path}': {p.stderr.decode()}")
    if ignore_missing and not local_file.is_file():
        return False
    return True


# def get_file_contents(filepath):
#     """Get contents of file at 'filepath'."""
#     p = utils.ssh_run(f"cat {shlex.quote(str(filepath))}")
#     if p.stderr:
#         raise Exception(f"Failed to retrieve contents for '{filepath}': {p.stderr.decode()}")

#     return p.stdout.decode()


def write_file_contents(filepath: str, file_contents: bytes, resource_id: str):
    """Write contents to a new file on the storage server."""
    if not _is_valid_path(filepath, resource_id):
        raise Exception(f"You don't have permission to edit '{filepath}'")

    p = utils.ssh_run(f"cat - > {shlex.quote(str(filepath))}", input=file_contents)
    if p.stderr:
        raise Exception(f"Failed to upload contents to '{filepath}': {p.stderr.decode()}")


def remove_dir(path, resource_id: str):
    """Remove directory on 'path' from storage server."""
    if not _is_valid_path(path, resource_id):
        raise Exception(f"You don't have permission to remove '{path}'")

    p = utils.ssh_run(f"test -d {shlex.quote(str(path))} && rm -r {shlex.quote(str(path))}")
    if p.stderr:
        raise Exception(f"Failed to remove corpus dir on storage server: {p.stderr.decode()}")


# def remove_file(path, resource_id: str):
#     """Remove file on 'path' from storage server."""
#     if not _is_valid_path(path, resource_id):
#         raise Exception(f"You don't have permission to remove '{path}'")

#     p = utils.ssh_run(f"test -f {shlex.quote(str(path))} && rm {shlex.quote(str(path))}")
#     if p.stderr:
#         raise Exception(f"Failed to remove file '{path}' on storage server: {p.stderr.decode()}")


def _get_login():
    user = app.config.get("METADATA_USER")
    host = app.config.get("METADATA_HOST")
    return user, host


def _is_valid_path(path, resource_id: str):
    """Check that path points to a certain resource dir (or a descendant)."""
    return get_resource_dir(resource_id).resolve() in list(Path(path).resolve().parents) + [Path(path).resolve()]


################################################################################
# Get paths on storage server
################################################################################

def get_resources_dir() -> Path:
    """Get dir for metadata resources."""
    return Path(app.config.get("METADATA_DIR"))


def get_resource_dir(resource_id: str, mkdir=False) -> Path:
    """Get dir for given resource."""
    resources_dir = get_resources_dir()
    resdir = resources_dir / resource_id[len(app.config.get("RESOURCE_PREFIX"))] / resource_id
    if mkdir:
        _make_dir(resdir)
    return resdir


def get_source_dir(resource_id: str, mkdir: bool = False) -> Path:
    """Get source dir for given resource."""
    resdir = get_resource_dir(resource_id)
    source_dir = resdir / Path(app.config.get("METADATA_SOURCE_DIR"))
    if mkdir:
        _make_dir(source_dir)
    return source_dir


def get_yaml_file(resource_id):
    """Get path to metadata yaml file."""
    resdir = get_resource_dir(resource_id)
    return resdir / (resource_id + ".yaml")


def _make_dir(dirpath):
    """Create directory on storage server."""
    p = utils.ssh_run(f"mkdir -p {shlex.quote(str(dirpath))}")
    if p.stderr:
        raise Exception(f"Failed to create resource dir on storage server! {p.stderr.decode()}")
