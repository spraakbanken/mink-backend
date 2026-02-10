"""Shared storage utilities for SSH/rsync-based storage backends."""

from __future__ import annotations

import mimetypes
import shlex
import subprocess
from pathlib import Path
from typing import ClassVar

from dateutil.parser import parse

from mink.core import exceptions, utils
from mink.core.config import settings
from mink.core.logging import logger
from mink.sb_auth.login import request_id_var


class BaseStorage:
    """Base class for storage backends with capability flags and shared helpers.

    Expected usage is via a module-level singleton, e.g. `storage = SparvStorage()`,
    which keeps call sites simple while preserving object-oriented behavior.
    """
    # ------------------------------------------------------------------------------
    # Capability flags
    # ------------------------------------------------------------------------------
    supports_list: ClassVar[bool] = True
    supports_read: ClassVar[bool] = True
    supports_write: ClassVar[bool] = True
    supports_remove: ClassVar[bool] = True
    supports_upload: ClassVar[bool] = True
    supports_download_dir: ClassVar[bool] = True

    # ------------------------------------------------------------------------------
    # Config for subclass
    # ------------------------------------------------------------------------------
    always_exclude: ClassVar[list[str]] = []  # Paths to always exclude when listing contents
    user: str
    host: str

    # ------------------------------------------------------------------------------
    # Methods that must be implemented by subclass
    # ------------------------------------------------------------------------------
    def is_valid_path(self, path: Path, resource_id: str) -> bool:
        """Check if path points to a permitted location for the resource."""
        raise NotImplementedError

    # ------------------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------------------
    def _ensure(self, capability: str) -> None:
        if not getattr(self, f"supports_{capability}", False):
            raise exceptions.ParameterError(f"{capability} not supported for this storage")

    # ------------------------------------------------------------------------------
    # Local path getters (on Mink server, used for file downloads)
    # ------------------------------------------------------------------------------
    @staticmethod
    def get_local_resources_dir(mkdir: bool = False) -> Path:
        """Get user specific dir for resources."""
        if not request_id_var.get():
            logger.error("Request ID not set. Cannot get path to local resources dir.")
            raise exceptions.RequestIDNotSetError
        resources_dir = Path(settings.INSTANCE_PATH) / settings.TMP_DIR / request_id_var.get()
        if mkdir:
            resources_dir.mkdir(parents=True, exist_ok=True)
        return resources_dir

    def get_local_resource_dir(self, resource_id: str, mkdir: bool = False) -> Path:
        """Get dir for given resource."""
        resources_dir = self.get_local_resources_dir(mkdir=mkdir)
        resdir = resources_dir / resource_id
        if mkdir:
            resdir.mkdir(parents=True, exist_ok=True)
        return resdir

    # ------------------------------------------------------------------------------
    # Shared implementations
    # ------------------------------------------------------------------------------
    @staticmethod
    def relative_path(filepath: Path) -> str:
        """Return a path string for API responses."""
        return str(filepath)

    def ssh_run(self, command: str, ssh_input: bytes | None = None) -> subprocess.CompletedProcess:
        """Execute 'command' on server and return process.

        Args:
            command: The command to execute.
            ssh_input: The input to pass to the command.

        Returns:
            The completed process.
        """
        return subprocess.run(
            ["ssh", "-i", settings.SSH_KEY, f"{self.user}@{self.host}", command],
            capture_output=True,
            input=ssh_input,
            check=False,
        )

    def list_contents(self, directory: Path, exclude_dirs: bool = True, blacklist: list | None = None) -> list:
        """List files in directory on remote server recursively.

        Args:
            directory: The directory to list contents of.
            exclude_dirs: Whether to exclude directories from the list.
            blacklist: List of paths to exclude.

        Returns:
            A list of dictionaries containing file information.
        """
        self._ensure("list")
        objlist = []
        directory_quoted = shlex.quote(str(directory))
        p = self.ssh_run(
            f"test -d {directory_quoted} && cd {directory_quoted} && "
            f"find . -exec ls -lgGd --time-style=full-iso {{}} \\;"
        )
        if p.stderr:
            raise exceptions.ReadError(directory, f"Failed to list contents: {p.stderr.decode()}")

        blacklist_items = list(blacklist or [])
        blacklist_items.extend(self.always_exclude)

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
            if any(Path(f.parts[0]).match(item) for item in blacklist_items):
                continue
            objlist.append(
                {"name": f.name, "type": mimetype, "last_modified": mod_time, "size": int(size), "path": obj_path[2:]}
            )
        return objlist

    def get_file_info(self, filepath: Path) -> dict:
        """Get info about a file on remote server.

        Args:
            filepath: The path to the file.

        Returns:
            A dictionary containing file information.
        """
        self._ensure("read")
        p = self.ssh_run(f"ls -lgGd --time-style=full-iso {shlex.quote(str(filepath))}")
        if p.stderr:
            raise exceptions.ReadError(filepath, f"Failed to get file info: {p.stderr.decode()}")

        fileinfo = p.stdout.decode().strip()
        permissions, _, size, date, time, tz, _ = fileinfo.split(maxsplit=6)
        mod_time = parse(f"{date} {time} {tz}").isoformat(timespec="seconds")
        mimetype = "directory" if permissions.startswith("d") else mimetypes.guess_type(str(filepath))[0] or "unknown"

        return {
            "name": filepath.name,
            "type": mimetype,
            "last_modified": mod_time,
            "size": int(size),
            "path": self.relative_path(filepath),
        }

    def download_file(
        self, remote_file_path: Path, local_file: Path, resource_id: str, ignore_missing: bool = False
    ) -> bool:
        """Download a file from the remote server.

        Args:
            remote_file_path: The path to the remote file.
            local_file: The local file path to save the downloaded file to.
            resource_id: The resource ID.
            ignore_missing: Whether to ignore missing files.

        Returns:
            True if the file was downloaded successfully, False otherwise.
        """
        self._ensure("read")
        if not self.is_valid_path(remote_file_path, resource_id):
            raise exceptions.ReadError(remote_file_path, "You don't have permission to download this file")

        cmd = ["rsync", "--protect-args"]
        if ignore_missing:
            cmd.append("--ignore-missing-args")
        cmd += [f"{self.user}@{self.host}:{remote_file_path}", f"{local_file}"]
        p = subprocess.run(cmd, capture_output=True, check=False)
        if p.stderr:
            raise exceptions.ReadError(remote_file_path, p.stderr.decode())
        return not (ignore_missing and not local_file.is_file())

    def get_file_contents(self, filepath: Path, as_bytes: bool = False) -> bytes | str:
        """Get contents of file at 'filepath'.

        Args:
            filepath: The path to the file.
            as_bytes: If True, return bytes; else return decoded string.

        Returns:
            The contents of the file as string or bytes.
        """
        self._ensure("read")
        p = self.ssh_run(f"cat {shlex.quote(str(filepath))}")
        if p.stderr:
            raise exceptions.ReadError(filepath, p.stderr.decode())
        if as_bytes:
            return p.stdout
        return p.stdout.decode()

    def get_size(self, remote_path: Path) -> int:
        """Get the size (in bytes) of a file or directory.

        Args:
            remote_path: The path to the remote file or directory.

        Returns:
            The size of the file or directory in bytes.
        """
        self._ensure("read")
        p = self.ssh_run(f"du -b -s {shlex.quote(str(remote_path))}")
        if p.stderr:
            raise exceptions.ReadError(remote_path, f"Failed to retrieve size: {p.stderr.decode()}")
        try:
            return int(p.stdout.decode().split()[0])
        except Exception as e:
            raise exceptions.ReadError(remote_path, "Failed to retrieve size") from e

    def write_file_contents(self, filepath: Path, file_contents: bytes, resource_id: str) -> None:
        """Write contents to a new file on the remote server.

        Args:
            filepath: The path to the file.
            file_contents: The contents to write to the file.
            resource_id: The resource ID.
        """
        self._ensure("write")
        if not self.is_valid_path(filepath, resource_id):
            raise exceptions.WriteError(filepath, "You don't have permission to edit this file")

        p = self.ssh_run(f"cat - > {shlex.quote(str(filepath))}", ssh_input=file_contents)
        if p.stderr:
            raise exceptions.WriteError(filepath, p.stderr.decode())

    def download_dir(
        self,
        remote_dir: Path,
        local_dir: Path,
        resource_id: str,
        zipped: bool = False,
        zippath: Path | None = None,
        excludes: list | None = None,
    ) -> Path:
        """Download remote_dir on server to local_dir by rsyncing.

        Args:
            remote_dir: The remote directory to download.
            local_dir: The local directory to save the downloaded contents.
            resource_id: The resource ID.
            zipped: Whether to zip the downloaded contents.
            zippath: The path to save the zipped file.
            excludes: List of paths to exclude.

        Returns:
            The path to the local directory or the zipped file.
        """
        self._ensure("download_dir")
        if not excludes:
            excludes = []
        if not self.is_valid_path(remote_dir, resource_id):
            raise exceptions.ReadError(remote_dir, "You don't have permission to download this directory")

        if not local_dir.is_dir():
            raise exceptions.ReadError(local_dir, "Directory is not valid")

        if zipped and zippath is None:
            raise exceptions.ParameterError("'zippath' may not be None if 'zipped=True'")

        command = ["rsync", "--recursive"]
        command.extend(f"--exclude={e}" for e in excludes)
        command.extend([f"{self.user}@{self.host}:{remote_dir}/", f"{local_dir}"])
        p = subprocess.run(command, capture_output=True, check=False)
        if p.stderr:
            raise exceptions.ReadError(remote_dir, p.stderr.decode())

        if not zipped:
            return local_dir

        utils.create_zip(local_dir, zippath, zip_rootdir=resource_id)  # type: ignore[arg-type]
        return zippath  # type: ignore[return-value]

    def upload_dir(self, remote_dir: Path, local_dir: Path, resource_id: str, delete: bool = False) -> None:
        """Upload local dir to remote_dir on server by rsyncing.

        Args:
            remote_dir: Directory on remote server to upload to.
            local_dir: Local directory to upload.
            delete: If set to True delete files that do not exist in local_dir.
            resource_id: Resource ID.
        """
        self._ensure("upload")
        if not self.is_valid_path(remote_dir, resource_id):
            raise exceptions.WriteError(remote_dir, "You don't have permission to edit this directory")

        if not local_dir.is_dir():
            raise exceptions.WriteError(local_dir, "Directory is not valid")

        args = ["--recursive", "--delete", f"{local_dir}/"] if delete else ["--recursive", f"{local_dir}/"]

        self.make_dir(remote_dir)
        p = subprocess.run(["rsync", *args, f"{self.user}@{self.host}:{remote_dir}"], capture_output=True, check=False)
        if p.stderr:
            raise exceptions.WriteError(remote_dir, p.stderr.decode())

    def remove_dir(self, path: Path, resource_id: str) -> None:
        """Remove directory on remote server.

        Args:
            path: The path to the directory.
            resource_id: The resource ID.
        """
        self._ensure("remove")
        if not self.is_valid_path(path, resource_id):
            raise exceptions.WriteError(path, "You don't have permission to remove this directory")

        p = self.ssh_run(f"test -d {shlex.quote(str(path))} && rm -r {shlex.quote(str(path))}")
        if p.stderr:
            raise exceptions.WriteError(path, f"Cannot remove corpus dir: {p.stderr.decode()}")

    def remove_file(self, path: Path, resource_id: str) -> None:
        """Remove file on remote server.

        Args:
            path: The path to the file.
            resource_id: The resource ID.
        """
        self._ensure("remove")
        if not self.is_valid_path(path, resource_id):
            raise exceptions.WriteError(path, "You don't have permission to remove this file")

        p = self.ssh_run(f"test -f {shlex.quote(str(path))} && rm {shlex.quote(str(path))}")
        if p.stderr:
            raise exceptions.WriteError(path, f"Failed to remove file: {p.stderr.decode()}")

    def make_dir(self, dirpath: Path) -> None:
        """Create directory on remote server.

        Args:
            dirpath: The path to the directory to create.
        """
        self._ensure("write")
        p = self.ssh_run(f"mkdir -p {shlex.quote(str(dirpath))}")
        if p.stderr:
            raise exceptions.WriteError(dirpath, f"Failed to create resource dir: {p.stderr.decode()}")
