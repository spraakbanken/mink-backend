"""Functions related to storage on Sparv server."""

import mimetypes
import shlex
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from dateutil.parser import isoparse, parse

from mink.config import settings
from mink.core import exceptions, utils
from mink.sparv import utils as sparv_utils

if TYPE_CHECKING:
    from mink.core.jobs import Job

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
        Exception: If listing contents fails.
    """
    objlist = []
    directory_quoted = shlex.quote(str(directory))
    p = utils.ssh_run(
        f"test -d {directory_quoted} && cd {directory_quoted} && "
        f"find . -exec ls -lgGd --time-style=full-iso {{}} \\;"
    )
    if p.stderr:
        raise Exception(f"Failed to list contents of '{directory}': {p.stderr.decode()}")

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
        Exception: If the download fails or the path is invalid.
    """
    if not _is_valid_path(remote_file_path, resource_id):
        raise Exception(f"You don't have permission to download '{remote_file_path}'")

    user, host = _get_login()
    cmd = ["rsync", "--protect-args"]
    if ignore_missing:
        cmd.append("--ignore-missing-args")
    cmd += [f"{user}@{host}:{remote_file_path}", f"{local_file}"]
    p = subprocess.run(cmd, capture_output=True, check=False)
    if p.stderr:
        raise Exception(f"Failed to download '{remote_file_path}': {p.stderr.decode()}")
    return not (ignore_missing and not local_file.is_file())


def get_file_contents(filepath: Path) -> str:
    """Get contents of file at 'filepath'.

    Args:
        filepath: The path to the file.

    Returns:
        The contents of the file as a string.

    Raises:
        Exception: If retrieving the contents fails.
    """
    p = utils.ssh_run(f"cat {shlex.quote(str(filepath))}")
    if p.stderr:
        raise Exception(f"Failed to retrieve contents for '{filepath}': {p.stderr.decode()}")

    return p.stdout.decode()


def get_size(remote_path: Path) -> int:
    """Get the size (in bytes) of a file or directory.

    Args:
        remote_path: The path to the remote file or directory.

    Returns:
        The size of the file or directory in bytes.

    Raises:
        Exception: If retrieving the size fails.
    """
    p = utils.ssh_run(f"du -b -s {shlex.quote(str(remote_path))}")
    if p.stderr:
        raise Exception(f"Failed to retrieve size for path '{remote_path}': {p.stderr.decode()}")
    try:
        return int(p.stdout.decode().split()[0])
    except Exception as e:
        raise Exception(f"Failed to retrieve size for path '{remote_path}': {e}") from e


def write_file_contents(filepath: Path, file_contents: bytes, resource_id: str) -> None:
    """Write contents to a new file on the Sparv server.

    Args:
        filepath: The path to the file.
        file_contents: The contents to write to the file.
        resource_id: The resource ID.

    Raises:
        Exception: If writing the contents fails or the path is invalid.
    """
    if not _is_valid_path(filepath, resource_id):
        raise Exception(f"You don't have permission to edit '{filepath}'")

    p = utils.ssh_run(f"cat - > {shlex.quote(str(filepath))}", ssh_input=file_contents)
    if p.stderr:
        raise Exception(f"Failed to upload contents to '{filepath}': {p.stderr.decode()}")


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
        Exception: If the download fails or the path is invalid.
    """
    if not excludes:
        excludes = []
    if not _is_valid_path(remote_dir, resource_id):
        raise Exception(f"You don't have permission to download '{remote_dir}'")

    if not local_dir.is_dir():
        raise Exception(f"'{local_dir}' is not a directory")

    if zipped and zippath is None:
        raise Exception("Parameter zippath needs to be supplied when 'zipped=True'")

    user, host = _get_login()
    command = ["rsync", "--recursive"]
    command.extend(f"--exclude={e}" for e in excludes)
    command.extend([f"{user}@{host}:{remote_dir}/", f"{local_dir}"])
    p = subprocess.run(command, capture_output=True, check=False)
    if p.stderr:
        raise Exception(f"Failed to download '{remote_dir}': {p.stderr.decode()}")

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
        Exception: If the upload fails or the path is invalid.
    """
    if not _is_valid_path(remote_dir, resource_id):
        raise Exception(f"You don't have permission to edit '{remote_dir}'")

    if not local_dir.is_dir():
        raise Exception(f"'{local_dir}' is not a directory")

    args = ["--recursive", "--delete", f"{local_dir}/"] if delete else ["--recursive", f"{local_dir}/"]

    _make_dir(remote_dir)
    user, host = _get_login()
    p = subprocess.run(["rsync", *args, f"{user}@{host}:{remote_dir}"], capture_output=True, check=False)
    if p.stderr:
        raise Exception(f"Failed to upload to '{remote_dir}': {p.stderr.decode()}")


def remove_dir(path: Path, resource_id: str) -> None:
    """Remove directory on 'path' from Sparv server.

    Args:
        path: The path to the directory.
        resource_id: The resource ID.

    Raises:
        Exception: If removing the directory fails or the path is invalid.
    """
    if not _is_valid_path(path, resource_id):
        raise Exception(f"You don't have permission to remove '{path}'")

    p = utils.ssh_run(f"test -d {shlex.quote(str(path))} && rm -r {shlex.quote(str(path))}")
    if p.stderr:
        raise Exception(f"Failed to remove corpus dir on Sparv server: {p.stderr.decode()}")


def remove_file(path: Path, resource_id: str) -> None:
    """Remove file on 'path' from Sparv server.

    Args:
        path: The path to the file.
        resource_id: The resource ID.

    Raises:
        Exception: If removing the file fails or the path is invalid.
    """
    if not _is_valid_path(path, resource_id):
        raise Exception(f"You don't have permission to remove '{path}'")

    p = utils.ssh_run(f"test -f {shlex.quote(str(path))} && rm {shlex.quote(str(path))}")
    if p.stderr:
        raise Exception(f"Failed to remove file '{path}' on Sparv server: {p.stderr.decode()}")


def get_file_changes(resource_id: str, job: "Job") -> tuple:
    """Get changes for source files and config file.

    Args:
        resource_id: The resource ID.
        job: The job object.

    Returns:
        A tuple containing lists of added, changed, and deleted source files, and the changed config file.

    Raises:
        JobNotFoundError: If the job has not started.
        CouldNotListSourcesError: If listing source files fails.
    """
    if not job.started:
        raise exceptions.JobNotFoundError
    started = isoparse(job.started)

    # Get current source files
    try:
        source_files = list_contents(get_source_dir(resource_id))
    except Exception as e:
        raise exceptions.CouldNotListSourcesError(str(e)) from e
    source_file_paths = [f["path"] for f in source_files]
    available_file_paths = [f["path"] for f in job.source_files]

    # Check for new source files
    added_sources = [sf for sf in source_files if sf["path"] not in available_file_paths]

    # Compare all source files modification time to the time stamp of the last job started
    changed_sources = []
    for sf in source_files:
        if sf in added_sources:
            continue
        mod = isoparse(sf.get("last_modified"))
        if mod > started:
            changed_sources.append(sf)

    # Check for deleted source files
    deleted_sources = [fileobj for fileobj in job.source_files if fileobj["path"] not in source_file_paths]

    # Compare the config file modification time to the time stamp of the last job started
    changed_config = {}
    corpus_files = list_contents(get_corpus_dir(resource_id))
    config_file = get_config_file(resource_id)
    for f in corpus_files:
        if f.get("name") == config_file.name:
            config_mod = isoparse(f.get("last_modified"))
            if config_mod > started:
                changed_config = f
            break

    return added_sources, changed_sources, deleted_sources, changed_config


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
        raise Exception(f"Failed to create corpus dir on Sparv server! {p.stderr.decode()}")
