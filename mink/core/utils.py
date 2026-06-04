"""General utility functions."""

from __future__ import annotations

import datetime
import gzip
import logging
import os
import pickle
import shutil
import tomllib
import unicodedata
import zipfile
from collections.abc import Mapping, Sequence
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import status
from fastapi.responses import JSONResponse
from mkdocs.commands import build
from mkdocs.config import load_config
from starlette.background import BackgroundTask
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mink.core import exceptions, return_codes
from mink.core.config import settings
from mink.core.logging import logger
from mink.sb_auth.login import request_id_var

if TYPE_CHECKING:
    from mink.core.storage_base import BaseStorage


def response(
    return_code: return_codes.ReturnCode | str = "",
    status_code: int | None = None,
    message: str | None = None,
    cookie: tuple[bool, str, str] | None = None,
    **kwargs: Any,
) -> JSONResponse:
    """Create a JSON response, check if a return code was provided, and remove empty key-value pairs.

    Args:
        return_code: The return code (should not be empty).
        status_code: The HTTP status code.
        message: The response message.
        cookie: A tuple containing a bool (True=set cookie, False=delete cookie), the cookie key and value.
        **kwargs: Additional key-value pairs to include in the response.

    Returns:
        The updated JSONResponse object.
    """
    # Remove key-value pairs if the value is an empty string
    args = {k: v for k, v in kwargs.items() if v != ""}  # noqa: PLC1901

    if isinstance(return_code, return_codes.ReturnCode):
        resolved_status = return_code.status_code if status_code is None else status_code
        resolved_message = message if message is not None else return_code.message
        resolved_code = return_code.code
    else:
        resolved_status = status_code if status_code is not None else status.HTTP_200_OK
        resolved_message = message or ""
        resolved_code = return_code

    success = status.HTTP_200_OK <= resolved_status < status.HTTP_300_MULTIPLE_CHOICES

    if not resolved_message and not success:
        resolved_message = return_codes.UNKNOWN_ERROR.message

    if not resolved_code:
        resolved_code = return_codes.UNKNOWN_ERROR.code
        # raise ValueError("A return code must be provided in the response")

    status_str = "success" if success else "error"
    if not success:
        log_kwargs = {k: v for k, v in kwargs.items() if k != "status"} or ""
        info_str = "; " + str(log_kwargs) if log_kwargs else ""
        logger.error("%s: %s; return_code: %s%s", resolved_status, resolved_message, resolved_code, info_str)

    response = JSONResponse(
        content={"status": status_str, "message": resolved_message, "return_code": resolved_code, **args},
        status_code=resolved_status,
    )
    if cookie is not None:
        if cookie[0]:
            response.set_cookie(key=cookie[1], value=cookie[2], httponly=True)
        else:
            response.delete_cookie(key=cookie[1])

    response.background = BackgroundTask(remove_tmp_files, request_id_var.get())

    return response


def remove_tmp_files(request_id: str) -> None:
    """Remove temporary files.

    Args:
        request_id: The request ID (randomly generated upon request and stored in request.state).
    """
    if request_id:
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
        resp = response(return_code=return_codes.CONTENT_TOO_LARGE, max_size_mb=max_size_mb)
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


def get_version_from_pyproject(path: Path = Path("pyproject.toml")) -> str:
    """Get the version of the project from the pyproject.toml file.

    Args:
        path: Path to the pyproject.toml file.
    """
    # print absolute path
    path = path.resolve()
    if not path.exists() or not path.is_file():
        logger.error("Could not find pyproject.toml file at %s", path)
        raise FileNotFoundError(f"Could not find pyproject.toml file at {path}")
    with path.open("rb") as f:
        data = tomllib.load(f)
    return data["project"]["version"]


def build_docs() -> None:
    """Build the MkDocs documentation if source files are present and newer than the existing site output."""
    try:
        docs_root = Path("docs")
        env_file = Path(".env")
        mkdocs_config = docs_root / "mkdocs.yml"
        docs_source_dir = docs_root / "mkdocs"
        developers_guide = docs_root / "developers-guide.md"
        site_dir = docs_root / "site"

        source_paths = [mkdocs_config, docs_source_dir, developers_guide]
        freshness_paths = source_paths + ([env_file] if env_file.exists() else [])
        missing_sources = [path for path in source_paths if not path.exists()]
        if missing_sources:
            logger.warning("Skipping MkDocs build because required source path(s) are missing: %s", missing_sources)
            return

        def latest_mtime(paths: list[Path]) -> float:
            latest = 0.0
            for path in paths:
                latest = max(latest, path.stat().st_mtime)
                for p in path.rglob("*"):
                    latest = max(latest, p.stat().st_mtime)
            return latest

        # Check if the site output is at least as new as the source files; if so, skip the build
        has_site_output = site_dir.exists() and site_dir.is_dir() and any(site_dir.iterdir())
        if has_site_output:
            newest_source = latest_mtime(freshness_paths)
            newest_output = site_dir.stat().st_mtime
            if newest_source <= newest_output:
                logger.debug("Skipping MkDocs build: docs/site is up to date.")
                return

        # Load the MkDocs configuration and build the documentation
        os.environ["BASE_URL"] = settings.MINK_URL
        config = load_config(str(mkdocs_config))
        # Suppress some chatty logs
        logging.getLogger("mkdocs.plugins.mkdocs_macros.util").setLevel("WARNING")
        build.build(config)
    except Exception:
        logger.exception("Error building MkDocs documentation.")


def serialize_obj(obj: Any, *, depth: int | None = None, seen: set[int] | None = None) -> Any:
    """Recursively serialize objects while avoiding cycles and keeping depth limits."""
    if seen is None:
        seen = set()

    # Convert enums to plain values for stable logging/JSON output.
    if isinstance(obj, Enum):
        return obj.value

    # Primitives stay as-is
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj

    # Stop conditions
    obj_id = id(obj)
    if obj_id in seen:
        return "<cycle>"
    if depth is not None and depth < 0:
        return "<max-depth>"

    # Containers
    if isinstance(obj, Mapping):
        return {k: serialize_obj(v, depth=None if depth is None else depth - 1, seen=seen) for k, v in obj.items()}
    if isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
        return [serialize_obj(v, depth=None if depth is None else depth - 1, seen=seen) for v in obj]

    # Objects with serialize() method
    serialize = getattr(obj, "serialize", None)
    if callable(serialize):
        seen.add(obj_id)
        data = serialize()
        return serialize_obj(data, depth=None if depth is None else depth - 1, seen=seen)

    # Fallback
    return str(obj)


def get_current_time() -> str:
    """Get the current timestamp as an ISO 8601 string."""
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


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


def unpickle_file(inpath: Path, outpath: Path | None = None) -> Path:
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
            return_code=return_codes.INTERNAL_SERVER_ERROR, info="The zip file could not be created or is empty"
        )


def secure_filename(filename: str) -> Path:
    """Return a secure version of a filename."""
    filename = unicodedata.normalize("NFC", filename)

    for sep in os.path.sep, os.path.altsep:
        if sep:
            filename = filename.replace(sep, " ")

    return Path(filename.strip())


def size_ok(storage: BaseStorage, source_dir: Path, incoming_size: int) -> bool:
    """Check if the size of the incoming files exceeds the max resource size.

    Args:
        storage: Storage backend used to calculate the current size.
        source_dir: The source directory.
        incoming_size: The size of the incoming files.

    Returns:
        True if the size is within the limit, False otherwise.
    """
    if settings.MAX_RESOURCE_LENGTH is not None:
        current_size = storage.get_size(source_dir)
        total_size = current_size + incoming_size
        if total_size > settings.MAX_RESOURCE_LENGTH:
            return False
    return True
