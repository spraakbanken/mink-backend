"""Functions related to storage on Sparv server."""

import mimetypes
import shlex
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from dateutil.parser import isoparse, parse

from mink.core import exceptions, utils
from mink.core.config import settings
from mink.sparv import utils as sparv_utils

if TYPE_CHECKING:
    from mink.core.info import Info

local = True


def list_contents(directory: Path, exclude_dirs: bool = True, blacklist: list | None = None) -> list:
    """List files in directory on Sparv server recursively.

    Args:
        directory: The directory to list contents of.
        exclude_dirs: Whether to exclude directories from the list.
        blacklist: List of paths to exclude.

    Returns:
        A list of dictionaries containing file information.

    Raises:
        exceptions.ReadError: If listing contents fails.
    """
    objlist = []
    directory_quoted = shlex.quote(str(directory))
    p = utils.ssh_run(
        f"test -d {directory_quoted} && cd {directory_quoted} && "
        f"find . -exec ls -lgGd --time-style=full-iso {{}} \\;"
    )
    if p.stderr:
        raise exceptions.ReadError(directory, f"Failed to list contents: {p.stderr.decode()}")

    contents = p.stdout.decode()
    for line in contents.split("\n"):
        if not line.strip():
            continue
        permissions, _, size, date, time, tz, obj_path = line.split(maxsplit=6)
        if obj_path == ".":
            continue
        f = Path(obj_path)
        mod_time = parse(f"{date} {time} {tz}").isoformat(timespec="seconds")
        is_dir = permissions.startswith("d")
        mimetype = mimetypes.guess_type(str(f))[0] or "unknown"
        if is_dir:
            if exclude_dirs:
                continue
            mimetype = "directory"
        if blacklist and any(Path(f.parts[0]).match(item) for item in blacklist):
            continue
        objlist.append(
            {"name": f.name, "type": mimetype, "last_modified": mod_time, "size": int(size), "path": obj_path[2:]}
        )
    return objlist


def download_file(remote_file_path: Path, local_file: Path, resource_id: str, ignore_missing: bool = False) -> bool:
    """Download a file from the Sparv server.

    Args:
        remote_file_path: The path to the remote file.
        local_file: The local file path to save the downloaded file to.
        resource_id: The resource ID.
        ignore_missing: Whether to ignore missing files.

    Returns:
        True if the file was downloaded successfully, False otherwise.

    Raises:
        exceptions.ReadError: If the download fails or the path is invalid.
    """
    if not _is_valid_path(remote_file_path, resource_id):
        raise exceptions.ReadError(remote_file_path, "You don't have permission to download this file")

    user, host = _get_login()
    cmd = ["rsync", "--protect-args"]
    if ignore_missing:
        cmd.append("--ignore-missing-args")
    cmd += [f"{user}@{host}:{remote_file_path}", f"{local_file}"]
    p = subprocess.run(cmd, capture_output=True, check=False)
    if p.stderr:
        raise exceptions.ReadError(remote_file_path, p.stderr.decode())
    return not (ignore_missing and not local_file.is_file())


def get_file_contents(filepath: Path) -> str:
    """Get contents of file at 'filepath'.

    Args:
        filepath: The path to the file.

    Returns:
        The contents of the file as a string.

    Raises:
        exceptions.ReadError: If retrieving the contents fails.
    """
    p = utils.ssh_run(f"cat {shlex.quote(str(filepath))}")
    if p.stderr:
        raise exceptions.ReadError(filepath, p.stderr.decode())

    return p.stdout.decode()


def get_size(remote_path: Path) -> int:
    """Get the size (in bytes) of a file or directory.

    Args:
        remote_path: The path to the remote file or directory.

    Returns:
        The size of the file or directory in bytes.

    Raises:
        exceptions.ReadError: If retrieving the size fails.
    """
    p = utils.ssh_run(f"du -b -s {shlex.quote(str(remote_path))}")
    if p.stderr:
        raise exceptions.ReadError(remote_path, f"Failed to retrieve size: {p.stderr.decode()}")
    try:
        return int(p.stdout.decode().split()[0])
    except Exception as e:
        raise exceptions.ReadError(remote_path, "Failed to retrieve size") from e


def write_file_contents(filepath: Path, file_contents: bytes, resource_id: str) -> None:
    """Write contents to a new file on the Sparv server.

    Args:
        filepath: The path to the file.
        file_contents: The contents to write to the file.
        resource_id: The resource ID.

    Raises:
        exceptions.WriteError: If writing the contents fails or the path is invalid.
    """
    if not _is_valid_path(filepath, resource_id):
        raise exceptions.WriteError(filepath, "You don't have permission to edit this file")

    p = utils.ssh_run(f"cat - > {shlex.quote(str(filepath))}", ssh_input=file_contents)
    if p.stderr:
        raise exceptions.WriteError(filepath, p.stderr.decode())


def download_dir(
    remote_dir: Path,
    local_dir: Path,
    resource_id: str,
    zipped: bool = False,
    zippath: Path | None = None,
    excludes: list | None = None,
) -> Path:
    """Download remote_dir on Sparv server to local_dir by rsyncing.

    Args:
        remote_dir: The remote directory to download.
        local_dir: The local directory to save the downloaded contents.
        resource_id: The resource ID.
        zipped: Whether to zip the downloaded contents.
        zippath: The path to save the zipped file.
        excludes: List of paths to exclude.

    Returns:
        The path to the local directory or the zipped file.

    Raises:
        exceptions.ReadError: If the download fails or the path is invalid.
    """
    if not excludes:
        excludes = []
    if not _is_valid_path(remote_dir, resource_id):
        raise exceptions.ReadError(remote_dir, "You don't have permission to download this directory")

    if not local_dir.is_dir():
        raise exceptions.ReadError(local_dir, "Directory is not valid")

    if zipped and zippath is None:
        raise exceptions.ParameterError("'zippath' may not be None if 'zipped=True'")

    user, host = _get_login()
    command = ["rsync", "--recursive"]
    command.extend(f"--exclude={e}" for e in excludes)
    command.extend([f"{user}@{host}:{remote_dir}/", f"{local_dir}"])
    p = subprocess.run(command, capture_output=True, check=False)
    if p.stderr:
        raise exceptions.ReadError(remote_dir, p.stderr.decode())

    if not zipped:
        return local_dir

    utils.create_zip(local_dir, zippath, zip_rootdir=resource_id)
    return zippath


def upload_dir(remote_dir: Path, local_dir: Path, resource_id: str, delete: bool = False) -> None:
    """Upload local dir to remote_dir on Sparv server by rsyncing.

    Args:
        remote_dir: Directory on Sparv to upload to.
        local_dir: Local directory to upload.
        delete: If set to True delete files that do not exist in local_dir.
        resource_id: Resource ID.

    Raises:
        exceptions.WriteError: If the upload fails or the path is invalid.
    """
    if not _is_valid_path(remote_dir, resource_id):
        raise exceptions.WriteError(remote_dir, "You don't have permission to edit this directory")

    if not local_dir.is_dir():
        raise exceptions.WriteError(local_dir, "Directory is not valid")

    args = ["--recursive", "--delete", f"{local_dir}/"] if delete else ["--recursive", f"{local_dir}/"]

    _make_dir(remote_dir)
    user, host = _get_login()
    p = subprocess.run(["rsync", *args, f"{user}@{host}:{remote_dir}"], capture_output=True, check=False)
    if p.stderr:
        raise exceptions.WriteError(remote_dir, p.stderr.decode())


def remove_dir(path: Path, resource_id: str) -> None:
    """Remove directory on 'path' from Sparv server.

    Args:
        path: The path to the directory.
        resource_id: The resource ID.

    Raises:
        exceptions.WriteError: If removing the directory fails or the path is invalid.
    """
    if not _is_valid_path(path, resource_id):
        raise exceptions.WriteError(path, "You don't have permission to remove this directory")

    p = utils.ssh_run(f"test -d {shlex.quote(str(path))} && rm -r {shlex.quote(str(path))}")
    if p.stderr:
        raise exceptions.WriteError(path, f"Cannot remove corpus dir: {p.stderr.decode()}")


def remove_file(path: Path, resource_id: str) -> None:
    """Remove file on 'path' from Sparv server.

    Args:
        path: The path to the file.
        resource_id: The resource ID.

    Raises:
        exceptions.WriteError: If removing the file fails or the path is invalid.
    """
    if not _is_valid_path(path, resource_id):
        raise exceptions.WriteError(path, "You don't have permission to remove this file")

    p = utils.ssh_run(f"test -f {shlex.quote(str(path))} && rm {shlex.quote(str(path))}")
    if p.stderr:
        raise exceptions.WriteError(path, f"Failed to remove file: {p.stderr.decode()}")


def get_file_changes(resource_id: str, info_item: "Info") -> tuple[bool, bool, bool]:
    """Get changes for source files and config file.

    Args:
        resource_id: The resource ID.
        info_item: The resource info item.

    Returns:
        A tuple containing three booleans:
        - Whether source files have changed.
        - Whether source files have been deleted.
        - Whether the config file has changed.

    Raises:
        exceptions.JobNotFoundError: If the job has not started.
    """
    source_changed = sources_deleted = config_changed = False

    if not info_item.job.started:
        raise exceptions.JobNotFoundError(resource_id)
    started = isoparse(info_item.job.started)

    # Compare source files modification times to the time stamp of the last job started
    source_files = info_item.resource.source_files
    for sf in source_files:
        if isoparse(sf.get("last_modified")) > started:
            source_changed = True
            break

    # Compare the 'sources_deleted' timestamp to the time stamp of the last job started
    if isoparse(info_item.resource.sources_deleted) > started:
        sources_deleted = True

    # Compare the config file modification time to the time stamp of the last job started
    corpus_files = list_contents(get_corpus_dir(resource_id))
    config_file = get_config_file(resource_id)
    for f in corpus_files:
        if f.get("name") == config_file.name:
            if isoparse(f.get("last_modified")) > started:
                config_changed = True
            break

    return source_changed, sources_deleted, config_changed


def _get_login() -> tuple:
    """Get the login credentials for the Sparv server.

    Returns:
        A tuple containing the username and host.

    Raises:
        KeyError: If the login credentials are not found in the config.
    """
    return settings.SPARV_USER, settings.SPARV_HOST


def _is_valid_path(path: Path, resource_id: str) -> bool:
    """Check that path points to a certain corpus dir (or a descendant).

    Args:
        path: The path to check.
        resource_id: The resource ID.

    Returns:
        True if the path is valid, False otherwise.
    """
    return get_corpus_dir(resource_id).resolve() in {*list(path.resolve().parents), path.resolve()}


# ------------------------------------------------------------------------------
# Get paths on Sparv server
# ------------------------------------------------------------------------------

def get_corpus_dir(resource_id: str, mkdir: bool = False) -> Path:
    """Get dir for given corpus."""
    corpus_dir = sparv_utils.get_corpus_dir(resource_id)
    if mkdir:
        _make_dir(corpus_dir)
    return corpus_dir


def get_export_dir(resource_id: str, mkdir: bool = False) -> Path:
    """Get export dir for given corpus."""
    export_dir = sparv_utils.get_export_dir(resource_id)
    if mkdir:
        _make_dir(export_dir)
    return export_dir


def get_work_dir(resource_id: str, mkdir: bool = False) -> Path:
    """Get sparv workdir for given corpus."""
    work_dir = sparv_utils.get_work_dir(resource_id)
    if mkdir:
        _make_dir(work_dir)
    return work_dir


def get_source_dir(resource_id: str, mkdir: bool = False) -> Path:
    """Get source dir for given corpus."""
    source_dir = sparv_utils.get_source_dir(resource_id)
    if mkdir:
        _make_dir(source_dir)
    return source_dir


def get_config_file(resource_id: str) -> Path:
    """Get path to corpus config file."""
    return sparv_utils.get_config_file(resource_id)


def _make_dir(dirpath: Path) -> None:
    """Create directory on Sparv server."""
    p = utils.ssh_run(f"mkdir -p {shlex.quote(str(dirpath))}")
    if p.stderr:
        raise exceptions.WriteError(dirpath, f"Failed to create resource dir: {p.stderr.decode()}")
