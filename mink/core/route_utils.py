"""Shared helpers for route handlers."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import shortuuid
from fastapi import Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from mink.core import exceptions, info, registry, return_codes, utils
from mink.core.config import settings
from mink.core.info import Info
from mink.core.logging import logger
from mink.core.resource_specs import get_spec
from mink.core.status import Status
from mink.sb_auth import login


def get_info_from_auth(auth_data: dict) -> Info:
    """Return cached info object from auth_data, or load it from the registry."""
    info_obj = auth_data.get("info_obj")
    if info_obj is not None:
        return info_obj
    return registry.get(auth_data["resource_id"])


def get_validated_source_dir(
    *, request: Request, resource_id: str, get_source_dir: Callable[[str], Path], storage: Any
) -> Path:
    """Return the resource's source dir after validating the incoming request size.

    Args:
        request: The incoming request containing the content-length header.
        resource_id: Resource ID for which to get the source directory.
        get_source_dir: Callable that returns the source directory Path for a given resource ID.
        storage: Storage backend used for validating content size.
    """
    try:
        content_length = int(request.headers.get("content-length", "0"))
        source_dir = get_source_dir(resource_id)
    except Exception as e:
        raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_UPLOADING, info=str(e)) from e

    if not utils.size_ok(storage, source_dir, content_length):
        max_size_mb = int(settings.MAX_RESOURCE_LENGTH / (1024 * 1024))
        raise exceptions.MinkHTTPException(
            return_code=return_codes.CONTENT_TOO_LARGE,
            info="max resource size exceeded",
            max_size_mb=max_size_mb,
        )

    return source_dir


async def prepare_source_upload(
    *,
    upload_file: UploadFile,
    normalize_name: Callable[[Path], Path] | None = None,
    allowed_extensions: tuple[str, ...] | list[str] | None = None,
) -> tuple[Path, Path, bytes]:
    """Validate and read an uploaded source file.

    Args:
        upload_file: The uploaded file to prepare.
        normalize_name: Optional function for normalizing the filename (e.g. making extension lowercase).
        allowed_extensions: Optional list of allowed file extensions (e.g. [".xml", ".txt"]).

    Returns:
        A tuple of (original_name, normalized_name, file_contents).
    """
    if upload_file.filename is None:
        raise exceptions.MinkHTTPException(return_code=return_codes.INVALID_FILE, info="missing filename")

    original_name = utils.secure_filename(upload_file.filename)
    name = normalize_name(original_name) if normalize_name is not None else original_name

    if allowed_extensions and not any(name.suffix.lower() == ext.lower() for ext in allowed_extensions):
        raise exceptions.MinkHTTPException(
            return_code=return_codes.INVALID_FILE,
            file=upload_file.filename,
            info="invalid file extension",
        )

    file_contents = await upload_file.read()
    if len(file_contents) > settings.MAX_FILE_LENGTH:
        max_file_size_mb = int(settings.MAX_FILE_LENGTH / (1024 * 1024))
        raise exceptions.MinkHTTPException(
            return_code=return_codes.CONTENT_TOO_LARGE,
            file=upload_file.filename,
            info="max file size exceeded",
            max_size_mb=max_file_size_mb,
        )

    return original_name, name, file_contents


def uploaded_source_exists(
    *,
    storage: Any,
    source_dir: Path,
    existing_file_names: set[str],
    file_contents: bytes,
    name: Path,
    original_name: Path,
    warnings: list[str],
) -> bool:
    """Append warnings for an existing file and return True if upload should be skipped.

    Args:
        storage: Storage backend used for checking existing files.
        source_dir: Source directory Path where the file would be uploaded.
        existing_file_names: Set of existing file names in the source directory.
        file_contents: Contents of the file being uploaded.
        name: Normalized file name for the uploaded file.
        original_name: Original file name for the uploaded file.
        warnings: List to which any warnings about existing files will be appended.
    """
    file_exists = str(name) in existing_file_names
    renamed_during_upload = name != original_name

    if not file_exists:
        if renamed_during_upload:
            warnings.append(f"File '{original_name}' was renamed to '{name}' during upload.")
        return False

    identical_file = storage.identical_file_exists(file_contents, source_dir / name)
    if identical_file and not renamed_during_upload:
        warnings.append(
            f"File '{name}' already existed with the same name, size and content. File was not uploaded again."
        )
        return True

    if identical_file:
        warnings.append(
            f"File '{original_name}' was renamed to '{name}' during upload and it replaced an existing file with the "
            "same name."
        )
    else:
        warnings.append(f"File called '{name}' already existed and was replaced during upload.")

    return False


def get_user_organization_prefix(user: Any) -> str | None:
    """Return the normalized organization prefix for a user.

    Args:
        user: User object with an `id` attribute.

    Returns:
        The user's organization prefix in lowercase.
    """
    org_prefix = settings.ORGANIZATION_PREFIXES.get(user.id)
    if org_prefix is not None:
        org_prefix = org_prefix.strip().lower()
    return org_prefix


def validate_public_id_organization_prefix(
    *, public_id: str, user: Any, return_code: Any = return_codes.FAILED_CREATING_RESOURCE
) -> str:
    """Validate that a public ID starts with the user's organization prefix.

    Args:
        public_id: Public ID to validate.
        user: User object with an `id` attribute.
        return_code: Return code used if validation fails.

    Returns:
        The user's normalized organization prefix.
    """
    org_prefix = get_user_organization_prefix(user)
    if org_prefix is None:
        raise exceptions.MinkHTTPException(
            return_code=return_code,
            info=f"No organization prefix found for user with ID '{user.id}'",
        )
    if not public_id.startswith(f"{org_prefix}-"):
        raise exceptions.MinkHTTPException(
            return_code=return_code,
            info=f"Public ID '{public_id}' does not start with organization prefix '{org_prefix}'",
        )
    return org_prefix


async def create_resource_id(
    *,
    auth_token: str,
    resource_type: str,
    existing_ids_fn: Callable[[], list[str]],
    resource_prefix: str,
    max_tries: int = 3,
) -> str:
    """Create a unique resource ID and register it with the auth system.

    Args:
        auth_token: Auth token used for creating the resource in the auth system.
        resource_type: Auth system resource type (e.g. "corpora", "metadata").
        existing_ids_fn: Callable returning currently known resource IDs.
        resource_prefix: Prefix to use for generated resource IDs.
        max_tries: Max number of attempts for generating a unique ID.

    Returns:
        The newly created resource ID.
    """
    # Create a new resource ID
    resource_id: str | None = None
    tries = 1
    while resource_id is None:
        # Give up after max_tries tries
        if tries > max_tries:
            raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_CREATING_RESOURCE)
        tries += 1
        candidate = f"{resource_prefix}{shortuuid.uuid()[:10]}".lower()
        if candidate in set(existing_ids_fn()):
            continue
        try:
            await login.create_resource(auth_token, candidate, resource_type=resource_type)
        except exceptions.ResourceExistsError:
            # Resource ID is in use in authentication system, try to create another one
            continue
        except Exception as e:
            raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_CREATING_RESOURCE, info=str(e)) from e
        resource_id = candidate
    return resource_id


async def remove_resource(
    *,
    resource_id: str,
    auth_token: str,
    info_obj: Any,
    remove_from_storage_fn: Callable[[], None],
    abort_job: bool = False,
) -> JSONResponse:
    """Remove a resource from storage, auth, and registry.

    Args:
        resource_id: Resource ID to remove.
        auth_token: Auth token used for removing the resource from the auth system.
        info_obj: Resource info object (for registry removal).
        remove_from_storage_fn: Callback that removes the resource from storage.
        abort_job: Whether to abort any running job before removing from registry.

    Returns:
        JSONResponse indicating success.
    """
    try:
        remove_from_storage_fn()
    except Exception as e:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.FAILED_REMOVING_CONTENT,
            info=f"Failed to remove resource from storage: {e}",
        ) from e

    try:
        await login.remove_resource(auth_token, resource_id)
    except Exception as e:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.FAILED_REMOVING_CONTENT,
            info=f"Failed to remove resource from authentication system: {e}",
        ) from e

    try:
        info_obj.remove(abort_job=abort_job)
    except Exception:
        logger.exception("Failed to remove resource '%s' from registry.", resource_id)

    return utils.response(return_code=return_codes.REMOVED_RESOURCE)


async def cleanup_partial_resource(
    *,
    resource_id: str,
    auth_token: str,
    info_obj: Any,
    remove_from_storage_fn: Callable[[], None],
) -> None:
    """Attempt to clean up partially created resource data from storage, auth system, and registry.

    Args:
        resource_id: Resource ID to clean up.
        auth_token: Auth token used for removing the resource from the auth system.
        info_obj: Resource info object (for registry removal).
        remove_from_storage_fn: Callback that removes the resource from storage.
    """
    try:
        remove_from_storage_fn()
    except Exception:
        logger.exception("Failed to remove partially uploaded data for resource '%s'.", resource_id)
    try:
        await login.remove_resource(auth_token, resource_id)
    except Exception:
        logger.exception("Failed to remove resource '%s' from auth system.", resource_id)
    try:
        info_obj.remove()
    except Exception:
        logger.exception("Failed to remove resource '%s' from registry.", resource_id)


async def get_yaml_payload(*, yaml_file: UploadFile | None, yaml_txt: str | None) -> str | bytes:
    """Return YAML payload from file or plain text.

    Args:
        yaml_file: Uploaded YAML file, if provided.
        yaml_txt: YAML content as plain text, if provided.

    Returns:
        YAML payload as bytes (from file) or string (from text).
    """
    if yaml_file and yaml_txt:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.VALIDATION_ERROR,
            info="Both a file and plain text config were provided"
        )

    if yaml_file:
        valid_mime_types = {"application/yaml", "application/x-yaml", "text/yaml", "text/x-yaml"}
        has_yaml_suffix = bool(yaml_file.filename and Path(yaml_file.filename).suffix.lower() in {".yaml", ".yml"})
        # MIME types can vary by client/tool; accept known YAML MIME types and .yaml/.yml uploads.
        if (
            yaml_file.content_type
            and yaml_file.content_type != "application/octet-stream"
            and yaml_file.content_type not in valid_mime_types
            and not has_yaml_suffix
        ):
            raise exceptions.MinkHTTPException(
                return_code=return_codes.INVALID_FILE, info="File format needs to be YAML"
            )
        return await yaml_file.read()

    if yaml_txt:
        return yaml_txt

    raise exceptions.MinkHTTPException(return_code=return_codes.MISSING_FILE_UPLOAD)


async def upload_yaml_file(
    *,
    yaml_file: UploadFile | None,
    yaml_txt: str | None,
    res_obj: Any,
    write_fn: Callable[[bytes], None],
    standardize_fn: Callable[[str | bytes], tuple[str, str]] | None = None,
    validate_fn: Callable[[str | bytes], None] | None = None,
) -> JSONResponse:
    """Upload YAML from file or plain text, then write standardized output.

    Args:
        yaml_file: Uploaded YAML file, if provided.
        yaml_txt: YAML content as plain text, if provided.
        res_obj: Resource info object (for setting resource name).
        write_fn: Callback for writing the standardized yaml bytes.
        standardize_fn: Optional function returning standardized yaml and resource name.
        validate_fn: Optional validation callback for the raw yaml payload.

    Returns:
        JSONResponse indicating success.
    """
    yaml_contents = await get_yaml_payload(yaml_file=yaml_file, yaml_txt=yaml_txt)

    def _process_yaml_upload() -> None:
        if validate_fn is not None:
            validate_fn(yaml_contents)
        if standardize_fn is not None:
            new_yaml, resource_name = standardize_fn(yaml_contents)
            res_obj.set_resource_name(resource_name)
        else:
            new_yaml = str(yaml_contents)
        write_fn(new_yaml.encode("UTF-8"))

    try:
        _process_yaml_upload()
    except exceptions.MinkHTTPException:
        raise
    except Exception as e:
        raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_UPLOADING, info=str(e)) from e

    return utils.response(return_code=return_codes.FILE_UPLOADED)


def download_file_response(
    *,
    local_path: Path,
    ensure_local_dir_fn: Callable[[], object],
    download_fn: Callable[[], bool],
    media_type: str,
) -> FileResponse:
    """Download a file and return a file response, or raise a MinkHTTPException.

    Args:
        local_path: Local path where the file will be stored.
        ensure_local_dir_fn: Callable that ensures local directory exists.
        download_fn: Callable that downloads the file and returns True if found.
        media_type: Response media type.

    Returns:
        FileResponse for the downloaded file.
    """
    ensure_local_dir_fn()
    try:
        download_ok = download_fn()
    except FileNotFoundError as e:
        raise exceptions.MinkHTTPException(return_code=return_codes.FILE_NOT_FOUND, info=str(e)) from e
    except Exception as e:
        raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_DOWNLOADING, info=str(e)) from e
    if download_ok:
        return FileResponse(local_path, media_type=media_type, filename=local_path.name)
    raise exceptions.MinkHTTPException(return_code=return_codes.FILE_NOT_FOUND)


def download_exports_response(
    *,
    storage: Any,
    resource_id: str,
    remote_dir: Path,
    local_resource_dir: Path,
    local_exports_dir: Path,
    download_file: str | None = None,
    download_folder: str | None = None,
    zipped: bool = True,
    blacklist: list[str] | None = None,
    default_media_type: str = "application/xml",
    archive_suffix: str = "export",
) -> FileResponse:
    """Download all exports, one export file, or a subdirectory of exports.

    Args:
        storage: Storage backend used for listing and downloading content.
        resource_id: Resource ID.
        remote_dir: Remote directory containing the downloadable content.
        local_resource_dir: Local resource directory used for zip output files.
        local_exports_dir: Local export directory used for downloaded files.
        download_file: Relative file path to download.
        download_folder: Relative directory path to download.
        zipped: Whether to zip a specific file download.
        blacklist: Optional blacklist for listing/downloading content.
        default_media_type: Fallback media type for direct file downloads.
        archive_suffix: Suffix for archive names when downloading all exports.

    Returns:
        A file response for the requested download.
    """
    if download_file and download_folder:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.VALIDATION_ERROR,
            info="Both 'file' and 'dir' parameters were provided",
        )

    try:
        exports_contents = storage.list_contents(remote_dir, exclude_dirs=False, blacklist=blacklist)
    except Exception as e:
        raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_DOWNLOADING, info=str(e)) from e

    if not exports_contents:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.FILE_NOT_FOUND, info="No exports available for resource"
        )

    content_paths = {item.get("path") for item in exports_contents}

    if download_folder:
        if download_folder not in content_paths:
            logger.error(
                "Requested download folder '%s' not found in export contents for resource '%s'",
                download_folder,
                resource_id,
            )
            raise exceptions.MinkHTTPException(return_code=return_codes.FILE_NOT_FOUND)
        try:
            download_folder_name = "_".join(Path(download_folder).parts)
            zip_out = local_resource_dir / f"{resource_id}_{download_folder_name}.zip"
            local_folder = local_exports_dir / download_folder
            local_folder.mkdir(parents=True, exist_ok=True)
            storage.download_dir(
                remote_dir / download_folder,
                local_folder,
                resource_id,
                zipped=True,
                zippath=zip_out,
            )
            return FileResponse(zip_out, media_type="application/zip", filename=zip_out.name)
        except FileNotFoundError as e:
            raise exceptions.MinkHTTPException(return_code=return_codes.FILE_NOT_FOUND, info=str(e)) from e
        except Exception as e:
            raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_DOWNLOADING, info=str(e)) from e

    if download_file:
        if download_file not in content_paths:
            raise exceptions.MinkHTTPException(return_code=return_codes.FILE_NOT_FOUND, file=download_file)
        try:
            download_file_name = Path(download_file).name
            local_path = local_exports_dir / download_file
            local_path.parent.mkdir(parents=True, exist_ok=True)
            storage.download_file(remote_dir / download_file, local_path, resource_id)
            if zipped:
                outfile_path = local_resource_dir / f"{resource_id}_{download_file_name}.zip"
                utils.create_zip(local_path, outfile_path, zip_rootdir=resource_id)
                return FileResponse(outfile_path, media_type="application/zip", filename=outfile_path.name)
            content_type = default_media_type
            for file_obj in exports_contents:
                if file_obj.get("path") == download_file:
                    content_type = file_obj.get("type") or default_media_type
                    break
            return FileResponse(local_path, media_type=content_type, filename=local_path.name)
        except FileNotFoundError as e:
            raise exceptions.MinkHTTPException(return_code=return_codes.FILE_NOT_FOUND, info=str(e)) from e
        except Exception as e:
            raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_DOWNLOADING, info=str(e)) from e

    try:
        zip_out = local_resource_dir / f"{resource_id}_{archive_suffix}.zip"
        storage.download_dir(
            remote_dir,
            local_exports_dir,
            resource_id,
            zipped=True,
            zippath=zip_out,
            excludes=blacklist,
        )
        return FileResponse(zip_out, media_type="application/zip", filename=zip_out.name)
    except FileNotFoundError as e:
        raise exceptions.MinkHTTPException(return_code=return_codes.FILE_NOT_FOUND, info=str(e)) from e
    except Exception as e:
        raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_DOWNLOADING, info=str(e)) from e


def make_status_response(info: info.Info, admin: bool = False) -> dict:
    """Check the annotation status for a given resource and return a dict that can be used to make a response.

    Args:
        info: The info object.
        admin: Whether the user is an admin.
    """
    job = info.job
    job.update_job_info()
    info_attrs = info.serialize()

    job_status = job.status
    spec = get_spec(info.resource.type)

    if job_status.is_none():
        return {"job_status": Status.none, "info": "There is no active job for this resource", **info_attrs}

    if job_status.is_syncing(spec.sync_processes):
        return {"job_status": Status.running, "info": "Files are being synced", **info_attrs}

    if job_status.is_waiting():
        return {"job_status": Status.waiting, "info": "Job has been queued", **info_attrs}

    if job_status.is_aborted(job.current_process):
        return {"job_status": Status.aborted, "info": "Job was aborted by the user", **info_attrs}

    if job_status.is_running():
        return {"job_status": Status.running, "info": "Job is running", **info_attrs}

    if spec.on_done_sync and job_status.is_done(job.current_process):
        result = spec.on_done_sync(info, admin)
        if result:
            return {**result, **info_attrs}

    if job_status.is_done(job.current_process):
        return {"job_status": Status.done, "info": "Job was completed successfully", **info_attrs}

    if job_status.is_error(job.current_process):
        logger.error(
            "An error occurred during processing; warnings: %s, errors: %s, output: %s, job_attrs: %s",
            info_attrs["job"]["warnings"],
            info_attrs["job"]["errors"],
            info_attrs["job"]["output"],
            info_attrs,
        )
        return {"job_status": Status.error, "info": "An error occurred during processing", **info_attrs}

    raise exceptions.MinkHTTPException(
        return_code=return_codes.INTERNAL_SERVER_ERROR, info=f"Unknown job status: {job_status}", **info_attrs
    )
