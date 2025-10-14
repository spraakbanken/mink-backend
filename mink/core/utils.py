"""General utility functions."""

import gzip
import hashlib
import os
import pickle
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any

import yaml
from fastapi import status
from fastapi.responses import JSONResponse
from mkdocs.commands import build
from mkdocs.config import load_config
from starlette.background import BackgroundTask
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mink.core import exceptions, models
from mink.core.config import settings
from mink.core.logging import logger
from mink.sb_auth.login import request_id_var
from mink.sparv import storage


def response(
    status_code: int = status.HTTP_200_OK,
    message: str = "",
    return_code: str = "",
    cookie: tuple[bool, str, str] | None = None,
    **kwargs: dict[str, Any],
) -> JSONResponse:
    """Create a JSON response, check if a return code was provided, and remove empty key-value pairs.

    Args:
        status_code: The HTTP status code.
        message: The response message.
        return_code: The return code (may not be empty).
        cookie: A tuple containing a bool (True=set cookie, False=delete cookie), the cookie key and value.
        **kwargs: Additional key-value pairs to include in the response.

    Returns:
        The updated JSONResponse object.
    """
    # Remove key-value pairs if the value is an empty string
    args = {k: v for k, v in kwargs.items() if v != ""}  # noqa: PLC1901

    success = status.HTTP_200_OK <= status_code < status.HTTP_300_MULTIPLE_CHOICES

    if not message and not success:
        message = "An unexpected error occurred"

    if not return_code:
        return_code = "unexpected_error"
        # raise ValueError("A return code must be provided in the response")

    status_str = "success" if success else "error"
    if not success:
        log_kwargs = {k: v for k, v in kwargs.items() if k != "status"} or ""
        info_str = "; info: " + str(log_kwargs) if log_kwargs else ""
        logger.error("%s: %s; return_code: %s%s", status_code, message, return_code, info_str)

    response = JSONResponse(
        content={"status": status_str, "message": message, "return_code": return_code, **args},
        status_code=status_code,
    )
    if cookie is not None:
        if cookie[0]:
            response.set_cookie(key=cookie[1], value=cookie[2], httponly=True)
        else:
            response.delete_cookie(key=cookie[1])

    response.background = BackgroundTask(remove_tmp_files, request_id_var.get())

    return response


def remove_tmp_files(request_id: str | None) -> None:
    """Remove temporary files.

    Args:
        request_id: The request ID (randomly generated upon request and stored in request.state).
    """
    if request_id is not None:
        local_user_dir = Path(settings.INSTANCE_PATH) / settings.TMP_DIR / request_id
        shutil.rmtree(str(local_user_dir), ignore_errors=True)


class LimitRequestSizeMiddleware:
    """ASGI middleware to limit request body size.

    Strategy:
      1) If Content-Length is present and > limit: send 413 and return (never call app).
      2) Otherwise, pre-read body in chunks before calling the app:
         - If size ever exceeds the limit: send 413 and return.
         - If within limit: replay the buffered chunks to the app.
    """
    def __init__(self, app: ASGIApp) -> None:
        """Initialize the middleware."""
        self.app = app
        self.max_body_size = settings.MAX_CONTENT_LENGTH  # in bytes

    async def _send_413(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Send a 413 Payload Too Large response."""
        max_size_mb = int(self.max_body_size / (1024 * 1024))
        resp = response(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            **models.ErrorResponse413(
                message=f"Request data too large (max {max_size_mb} MB per upload)",
                return_code="data_too_large",
                max_size_mb=max_size_mb,
            ).model_dump(),
        )
        await resp(scope, receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Check the size of the request body and return an error if it exceeds the limit."""
        # Skip non-HTTP connections
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Check Content-Length header, don't call app if too large
        headers = {k.lower(): v for k, v in ((k.decode(), v.decode()) for k, v in scope.get("headers", []))}
        cl = headers.get("content-length")
        if cl is not None:
            try:
                content_length = int(cl)
                if content_length > self.max_body_size:
                    await self._send_413(scope, receive, send)
                    return
            # Invalid Content-Length: fall through to streaming path
            except ValueError:
                pass

        # Stream file and pre-read into buffer before entering the app
        buffered: list[bytes] = []
        received = 0
        more_body_expected = True

        while more_body_expected:
            message = await receive()

            if message["type"] == "http.disconnect":
                # Client went away; nothing to send back. Just stop.
                return

            if message["type"] != "http.request":
                # Nothing else meaningful to pre-read in HTTP; ignore and continue
                continue

            chunk = message.get("body", b"")
            if chunk:
                received += len(chunk)
                # If size limit is exceeded, send 413 and return without calling app
                if received > self.max_body_size:
                    logger.warning("Request body too large: %.2f MB", received / (1024 * 1024))
                    await self._send_413(scope, receive, send)
                    return

                buffered.append(chunk)

            # If client says "more_body": False, we're done pre-reading.
            more_body_expected = message.get("more_body", False)

        # Request size is within the size limit: replay buffered chunks to the app
        replay_index = 0
        total = len(buffered)

        async def replay_receive() -> Message:  # noqa: RUF029 (Function declared `async` but never awaits)
            """Replay the pre-read body chunks to the app."""
            nonlocal replay_index
            if replay_index < total:
                part = buffered[replay_index]
                replay_index += 1
                return {
                    "type": "http.request",
                    "body": part,
                    "more_body": replay_index < total,
                }
            # After replaying everything, send one final empty frame with more_body=False
            return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, replay_receive, send)


def build_docs() -> None:
    """Build the MkDocs documentation."""
    try:
        # Load the MkDocs configuration and build the documentation
        os.environ["BASE_URL"] = settings.MINK_URL
        config = load_config("docs/mkdocs.yml")
        build.build(config)
    except Exception:
        logger.exception("Error building MkDocs documentation.")


def ssh_run(command: str, ssh_input: bytes | None = None) -> subprocess.CompletedProcess:
    """Execute 'command' on server and return process.

    Args:
        command: The command to execute.
        ssh_input: The input to pass to the command.

    Returns:
        The completed process.
    """
    return subprocess.run(
        ["ssh", "-i", settings.SSH_KEY, f"{settings.SPARV_USER}@{settings.SPARV_HOST}", command],
        capture_output=True,
        input=ssh_input,
        check=False,
    )


def uncompress_gzip(inpath: Path, outpath: Path | None = None) -> None:
    """Uncompress file with gzip and save to outpath (or inpath if no outpath is given).

    Args:
        inpath: The path to the input file.
        outpath: The path to the output file.
    """
    with gzip.open(inpath, "rb") as z:
        data = z.read()
        if outpath is None:
            outpath = inpath
        with outpath.open("wb") as f:
            f.write(data)


def unpickle_file(inpath: Path, outpath: Path | None = None) -> None:
    """Unpickle file and save to outpath (or inpath if no outpath is given).

    Args:
        inpath: The path to the input file.
        outpath: The path to the output file.

    Returns:
        The path to the output file.
    """
    with inpath.open("rb") as f:
        data = pickle.load(f)
        # Remove .pkl or .pickle suffix if present
        if outpath is None and inpath.suffix in {".pkl", ".pickle"}:
            outpath = inpath.with_suffix("")
        elif outpath is None:
            outpath = inpath
        with outpath.open("wb") as out_f:
            out_f.write(data.encode("utf-8"))
    return outpath


def create_zip(inpath: Path, outpath: Path, zip_rootdir: str | None = None) -> None:
    """Zip files in inpath into an archive at outpath.

    Args:
        inpath: The path to the input files.
        outpath: The path to the output zip file.
        zip_rootdir: Name that the root folder inside the zip file should be renamed to.
    """
    zipf = zipfile.ZipFile(str(outpath), "w")
    if inpath.is_file():
        zipf.write(inpath, inpath.name)
    else:
        for filepath in inpath.rglob("*"):
            zippath = filepath.relative_to(inpath.parent)
            if zip_rootdir:
                zippath = zip_rootdir / Path(*zippath.parts[1:])
            zipf.write(filepath, zippath)
    zipf.close()
    if not outpath.exists() or outpath.lstat().st_size == 0:
        raise exceptions.MinkHTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="The zip file could not be created or is empty",
            return_code="failed_creating_zip",
        )


def file_ext_valid(filename: Path, valid_extensions: list[str] | None = None) -> bool:
    """Check if file extension is valid.

    Args:
        filename: The filename to check.
        valid_extensions: List of valid extensions.

    Returns:
        True if the file extension is valid, False otherwise.
    """
    return not (valid_extensions and not any(i.lower() == filename.suffix.lower() for i in valid_extensions))


def file_ext_compatible(filename: Path, source_dir: Path) -> tuple[bool, str, str | None]:
    """Check if the file extension of filename is identical to the first file in source_dir.

    Args:
        filename: The filename to check.
        source_dir: The source directory.

    Returns:
        A tuple containing a boolean indicating compatibility, the current extension, and the existing extension.
    """
    existing_files = storage.list_contents(source_dir)
    current_ext = filename.suffix
    if not existing_files:
        return True, current_ext, None
    existing_ext = Path(existing_files[0].get("name")).suffix
    return current_ext == existing_ext, current_ext, existing_ext


def size_ok(source_dir: Path, incoming_size: int) -> bool:
    """Check if the size of the incoming files exceeds the max corpus size.

    Args:
        source_dir: The source directory.
        incoming_size: The size of the incoming files.

    Returns:
        True if the size is within the limit, False otherwise.
    """
    if settings.MAX_CORPUS_LENGTH is not None:
        current_size = storage.get_size(source_dir)
        total_size = current_size + incoming_size
        if total_size > settings.MAX_CORPUS_LENGTH:
            return False
    return True


def identical_file_exists(incoming_file_contents: bytes, existing_file: Path) -> bool:
    """Check if the incoming file is identical to the existing file.

    Args:
        incoming_file_contents: The incoming file contents.
        existing_file: Path to the existing file.

    Returns:
        True if the files are identical (in size and md5 hash), False otherwise.
    """
    if len(incoming_file_contents) == storage.get_size(existing_file):
        remote_file_contents = storage.get_file_contents(existing_file).encode("utf-8")
        remote_file_hash = hashlib.md5(remote_file_contents).hexdigest()
        incoming_file_hash = hashlib.md5(incoming_file_contents).hexdigest()
        if incoming_file_hash == remote_file_hash:
            return True
    return False


def config_compatible(config: str, source_file: dict) -> tuple[bool, dict[str, Any] | None]:
    """Check if the importer module in the corpus config is compatible with the source files.

    Args:
        config: The corpus config.
        source_file: The source file.

    Returns:
        A tuple containing a boolean indicating compatibility, the current importer, and the expected importer.
    """
    file_ext = Path(source_file.get("name")).suffix
    config_yaml = yaml.load(config, Loader=yaml.FullLoader)
    current_importer = config_yaml.get("import", {}).get("importer", "").split(":")[0] or None
    importer_dict = settings.SPARV_IMPORTER_MODULES

    # If no importer is specified xml is default
    if current_importer is None and file_ext == ".xml":
        return True, None, None

    expected_importer = importer_dict.get(file_ext)
    if current_importer == expected_importer:
        return True, current_importer, expected_importer
    return False, current_importer, expected_importer


def standardize_config(config: str, resource_id: str) -> tuple[str, str]:
    """Set the correct corpus ID and remove the compression setting in the corpus config.

    Args:
        config: The corpus config.
        resource_id: The corpus ID.

    Returns:
        A tuple containing the standardized config and the corpus name.
    """
    config_yaml = yaml.load(config, Loader=yaml.FullLoader)

    # Set correct corpus ID
    if config_yaml.get("metadata", {}).get("id") != resource_id:
        if not config_yaml.get("metadata"):
            config_yaml["metadata"] = {}
        config_yaml["metadata"]["id"] = resource_id

    # Get corpus name
    name = config_yaml.get("metadata", {}).get("name", {})

    # Remove the compression setting in order to use the standard one given by the default config
    if config_yaml.get("sparv", {}).get("compression") is not None:
        config_yaml["sparv"].pop("compression")
        # Remove entire Sparv section if empty
        if not config_yaml.get("sparv", {}):
            config_yaml.pop("sparv")

    # Remove settings that a Mink user is not allowed to modify
    config_yaml.pop("cwb", None)
    config_yaml.pop("korp", None)
    config_yaml.pop("sbx_strix", None)
    # Remove all install and uninstall targets (this is handled in the installation step instead)
    config_yaml.pop("install", None)
    config_yaml.pop("uninstall", None)

    # Add Korp settings
    config_yaml["korp"] = {
        "protected": True,
        "context": ["1 sentence", "5 sentence"],
        "within": ["sentence", "5 sentence"],
    }
    # Make Strix corpora appear in correct mode
    config_yaml["sbx_strix"] = {"modes": [{"name": "mink"}]}
    # Add '<text>:misc.id as _id' to annotations for Strix' sake
    if "export" in config_yaml and "annotations" in config_yaml["export"]:  # noqa: SIM102
        if "<text>:misc.id as _id" not in config_yaml["export"]["annotations"]:
            config_yaml["export"]["annotations"].append("<text>:misc.id as _id")

    return yaml.dump(config_yaml, sort_keys=False, allow_unicode=True), name


def standardize_metadata_yaml(metadata_yaml: str) -> tuple[str, str]:
    """Get resource name from metadata yaml and remove comments etc.

    Args:
        metadata_yaml: The metadata yaml.

    Returns:
        A tuple containing the standardized yaml and the resource name.
    """
    yaml_contents = yaml.load(metadata_yaml, Loader=yaml.FullLoader)

    # Get resource name
    name = yaml_contents.get("name", {})

    return yaml.dump(yaml_contents, sort_keys=False, allow_unicode=True), name


# ------------------------------------------------------------------------------
# Get local paths (mostly used for download)
# ------------------------------------------------------------------------------

def get_resources_dir(mkdir: bool = False) -> Path:
    """Get user specific dir for corpora."""
    if request_id_var.get() is None:
        logger.error("Resource ID not set. Cannot get path to local corpora dir.")
        raise exceptions.RequestIDNotSetError
    resources_dir = Path(settings.INSTANCE_PATH) / settings.TMP_DIR / request_id_var.get()
    if mkdir:
        resources_dir.mkdir(parents=True, exist_ok=True)
    return resources_dir


def get_resource_dir(resource_id: str, mkdir: bool = False) -> Path:
    """Get dir for given resource."""
    resources_dir = get_resources_dir(mkdir=mkdir)
    resdir = resources_dir / resource_id
    if mkdir:
        resdir.mkdir(parents=True, exist_ok=True)
    return resdir


def get_export_dir(resource_id: str, mkdir: bool = False) -> Path:
    """Get export dir for given resource."""
    resdir = get_resource_dir(resource_id, mkdir=mkdir)
    export_dir = resdir / settings.SPARV_EXPORT_DIR
    if mkdir:
        export_dir.mkdir(parents=True, exist_ok=True)
    return export_dir


def get_work_dir(resource_id: str, mkdir: bool = False) -> Path:
    """Get sparv workdir for given corpus."""
    resdir = get_resource_dir(resource_id, mkdir=mkdir)
    work_dir = resdir / settings.SPARV_WORK_DIR
    if mkdir:
        work_dir.mkdir(parents=True, exist_ok=True)
    return work_dir


def get_source_dir(resource_id: str, mkdir: bool = False) -> Path:
    """Get source dir for given corpus."""
    resdir = get_resource_dir(resource_id, mkdir=mkdir)
    source_dir = resdir / settings.SPARV_SOURCE_DIR
    if mkdir:
        source_dir.mkdir(parents=True, exist_ok=True)
    return source_dir


def get_config_file(resource_id: str) -> Path:
    """Get path to corpus config file."""
    resdir = get_resource_dir(resource_id)
    return resdir / settings.SPARV_CORPUS_CONFIG


def get_metadata_yaml_file(resource_id: str) -> Path:
    """Get path to local metadata yaml file."""
    resdir = get_resource_dir(resource_id)
    return resdir / (resource_id + ".yaml")
