"""Shared storage utilities for SSH/rsync-based storage backends."""

from __future__ import annotations

import hashlib
import ipaddress
import mimetypes
import shlex
import socket
import subprocess
from fnmatch import fnmatchcase
from pathlib import Path
from typing import ClassVar

from dateutil.parser import parse

from mink.core import exceptions, utils
from mink.core.config import settings
from mink.core.logging import logger
from mink.sb_auth.login import request_id_var


class BaseStorage:
    """Base class for storage backends with capability flags and shared helpers.

    Expected usage is to subclass this and implement the required methods, while the capability flags can be set
    according to what the specific storage backend supports.
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
        """Ensure that the storage supports the given capability."""
        if not getattr(self, f"supports_{capability}", False):
            raise exceptions.ParameterError(f"{capability} not supported for this storage")

    def _is_local_host(self) -> bool:
        """Check if configured host is localhost."""
        host = self.host.strip().lower()
        if host in {"localhost", "127.0.0.1", "::1"}:
            return True
        try:
            ip = ipaddress.ip_address(socket.gethostbyname(host))
        except Exception:
            return False
        else:
            return ip.is_loopback

    def _rsync_target(self, path: str | Path, remote: bool = False) -> str:
        """Build rsync path target for local/remote transport."""
        path_str = str(path)
        if remote and not self._is_local_host():
            return f"{self.user}@{self.host}:{path_str}"
        return path_str

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

    def file_exists(self, filepath: Path) -> bool:
        """Check if a remote file exists at the given path."""
        try:
            fileinfo = self.get_file_info(filepath)
            if fileinfo:
                return True
        except exceptions.ReadError:
            return False
        else:
            return True

    def ssh_run(self, command: str, ssh_input: bytes | None = None) -> subprocess.CompletedProcess:
        """Execute 'command' on server and return process.

        Args:
            command: The command to execute.
            ssh_input: The input to pass to the command.

        Returns:
            The completed process.
        """
        if self._is_local_host():
            return subprocess.run(
                ["bash", "-c", command],
                capture_output=True,
                input=ssh_input,
                check=False,
            )
        return subprocess.run(
            ["ssh", "-i", settings.SSH_KEY, f"{self.user}@{self.host}", command],
            capture_output=True,
            input=ssh_input,
            check=False,
        )

    def rsync(
        self,
        src: str | Path,
        dst: str | Path,
        *,
        src_remote: bool = False,
        dst_remote: bool = False,
        args: list[str] | None = None,
    ) -> subprocess.CompletedProcess:
        """Run rsync with local/remote endpoint selection.

        Args:
            src: Source path.
            dst: Destination path.
            src_remote: Whether source is on configured remote storage.
            dst_remote: Whether destination is on configured remote storage.
            args: Additional rsync flags/arguments.

        Returns:
            The completed process from rsync.
        """
        if src_remote and dst_remote and not self._is_local_host():
            raise exceptions.ParameterError("Rsync between two remote endpoints is not supported")

        command = ["rsync"]
        if args:
            command.extend(args)
        command.extend([self._rsync_target(src, remote=src_remote), self._rsync_target(dst, remote=dst_remote)])
        return subprocess.run(command, capture_output=True, check=False)

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
            # Filter out blacklisted paths using glob-style matching
            if any(fnmatchcase(str(f), item) for item in blacklist_items):
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

    def identical_file_exists(self, incoming_file_contents: bytes, existing_file: Path) -> bool:
        """Check if the incoming file is identical (in size and md5 hash) to the existing file.

        Args:
            incoming_file_contents: The incoming file contents.
            existing_file: Path to the existing file.
        """
        if len(incoming_file_contents) == self.get_size(existing_file):
            remote_file_contents = self.get_file_contents(existing_file, as_bytes=True)
            remote_file_hash = hashlib.md5(remote_file_contents).hexdigest()  # type: ignore
            incoming_file_hash = hashlib.md5(incoming_file_contents).hexdigest()
            if incoming_file_hash == remote_file_hash:
                return True
        return False

    def download_file(self, remote_file_path: Path, local_file: Path, resource_id: str) -> bool:
        """Download a file from the remote server.

        Args:
            remote_file_path: The path to the remote file.
            local_file: The local file path to save the downloaded file to.
            resource_id: The resource ID.

        Returns:
            True if the file was downloaded successfully, False otherwise.
        """
        # Check if file exists in storage
        if not self.file_exists(remote_file_path):
            raise FileNotFoundError(f"File not found: {remote_file_path}")

        self._ensure("read")
        if not self.is_valid_path(remote_file_path, resource_id):
            raise exceptions.ReadError(remote_file_path, "You don't have permission to download this file")

        args = ["--protect-args"]
        p = self.rsync(remote_file_path, local_file, src_remote=True, args=args)
        if p.stderr:
            raise exceptions.ReadError(remote_file_path, p.stderr.decode())
        return local_file.is_file()

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
        skip_empty_dirs: bool = True,
    ) -> Path:
        """Download remote_dir on server to local_dir by rsyncing.

        Args:
            remote_dir: The remote directory to download.
            local_dir: The local directory to save the downloaded contents.
            resource_id: The resource ID.
            zipped: Whether to zip the downloaded contents.
            zippath: The path to save the zipped file.
            excludes: List of paths to exclude.
            skip_empty_dirs: Whether to skip empty directories in the download.

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

        args = ["--recursive", *(f"--exclude={e}" for e in excludes)]
        if skip_empty_dirs:
            args.append("--prune-empty-dirs")
        p = self.rsync(f"{remote_dir}/", local_dir, src_remote=True, args=args)
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

        args = ["--recursive", "--delete"] if delete else ["--recursive"]

        self.make_dir(remote_dir)
        p = self.rsync(f"{local_dir}/", remote_dir, dst_remote=True, args=args)
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
