"""Functions related to meta data storage on storage server."""

import shlex
import subprocess
from pathlib import Path

from mink.core import exceptions, utils
from mink.core.config import settings


def download_file(remote_file_path: Path, local_file: Path, resource_id: str, ignore_missing: bool = False) -> bool:
    """Download a file from the storage server.

    Args:
        remote_file_path: The path to the remote file.
        local_file: The local file path to save the downloaded file.
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


def write_file_contents(filepath: Path, file_contents: bytes, resource_id: str) -> None:
    """Write contents to a new file on the storage server.

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


def remove_dir(path: Path, resource_id: str) -> None:
    """Remove directory on 'path' from storage server.

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


def _get_login() -> tuple[str, str]:
    """Get the login credentials for the storage server.

    Returns:
        A tuple containing the username and host.
    """
    return settings.METADATA_USER, settings.METADATA_HOST


def _is_valid_path(path: Path, resource_id: str) -> bool:
    """Check that path points to a certain resource dir (or a descendant).

    Args:
        path: The path to check.
        resource_id: The resource ID.

    Returns:
        True if the path is valid, False otherwise.
    """
    return get_resource_dir(resource_id).resolve() in {*list(path.resolve().parents), path.resolve()}


# ------------------------------------------------------------------------------
# Get paths on storage server
# ------------------------------------------------------------------------------

def get_resources_dir() -> Path:
    """Get dir for metadata resources."""
    return Path(settings.METADATA_DIR)


def get_resource_dir(resource_id: str, mkdir: bool = False) -> Path:
    """Get dir for given resource."""
    resources_dir = get_resources_dir()
    resdir = resources_dir / resource_id[len(settings.RESOURCE_PREFIX)] / resource_id
    if mkdir:
        _make_dir(resdir)
    return resdir


def get_source_dir(resource_id: str, mkdir: bool = False) -> Path:
    """Get source dir for given resource."""
    resdir = get_resource_dir(resource_id)
    source_dir = resdir / settings.METADATA_SOURCE_DIR
    if mkdir:
        _make_dir(source_dir)
    return source_dir


def get_yaml_file(resource_id: str) -> Path:
    """Get path to metadata yaml file."""
    resdir = get_resource_dir(resource_id)
    return resdir / (resource_id + ".yaml")


def _make_dir(dirpath: Path) -> None:
    """Create directory on storage server."""
    p = utils.ssh_run(f"mkdir -p {shlex.quote(str(dirpath))}")
    if p.stderr:
        raise exceptions.WriteError(dirpath, f"Failed to create resource dir: {p.stderr.decode()}")
