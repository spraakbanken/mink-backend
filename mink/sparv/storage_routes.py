"""Routes related to storage on Sparv server."""

from pathlib import Path
from typing import cast
from xml.etree import ElementTree

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse

from mink.cache import jobs_cache
from mink.core import exceptions, models, registry, return_codes, route_utils, utils
from mink.core.config import settings
from mink.core.info import Info
from mink.core.logging import logger
from mink.core.resource import Resource
from mink.core.resource_specs import get_spec
from mink.sb_auth import login
from mink.sparv import models as sparv_models
from mink.sparv import utils as sparv_utils
from mink.sparv.config import sparv_settings
from mink.sparv.jobs import SparvJob
from mink.sparv.spec import CORPUS
from mink.sparv.storage import storage

router = APIRouter(tags=["Manage Corpora"])
SBAUTH_CORPUS = get_spec(CORPUS).sbauth_resource_type
AUTH_CORPUS = login.AuthDependency(sbauth_resource_type=SBAUTH_CORPUS)
AUTH_CORPUS_WRITE = login.AuthDependency(min_level="WRITE", sbauth_resource_type=SBAUTH_CORPUS)
AUTH_CORPUS_ADMIN = login.AuthDependency(min_level="ADMIN", sbauth_resource_type=SBAUTH_CORPUS)
AUTH_CORPUS_NO_ID = login.AuthDependencyNoResourceId(sbauth_resource_type=SBAUTH_CORPUS)


def _require_job(job: object) -> SparvJob:
    """Ensure that 'job' is a Sparv job, raise an error if not."""
    if not isinstance(job, SparvJob):
        raise exceptions.MinkHTTPException(
            return_code=return_codes.INVALID_RESOURCE_TYPE, info="Expected a corpus resource"
        )
    return cast(SparvJob, job)


# ------------------------------------------------------------------------------
# Corpus operations
# ------------------------------------------------------------------------------


@router.post(
    "/create-corpus",
    deprecated=True,
    name="create-corpus-deprecated",
)
@router.post(
    "/corpus/create",
    operation_id="create-corpus",
    status_code=status.HTTP_201_CREATED,
    response_model=models.CreateResourceResponse,
    responses={
        **models.common_auth_error_responses,
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": models.ErrorResponse500,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.FAILED_CREATING_RESOURCE.message,
                        "return_code": return_codes.FAILED_CREATING_RESOURCE.code,
                        "info": "BaseException",
                    }
                }
            },
        },
    },
)
async def create_corpus(auth_data: dict = Depends(AUTH_CORPUS_NO_ID)) -> JSONResponse:
    """Create a new corpus.

    ### Example

    ```bash
    curl -X POST '{{host}}/corpus/create' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    resource_id = await route_utils.create_resource_id(
        auth_token=auth_data["auth_token"],
        resource_type=get_spec(CORPUS).sbauth_resource_type,
        existing_ids_fn=jobs_cache.get_all_resources,
        resource_prefix=settings.RESOURCE_PREFIX,
    )

    try:
        # Create info object in registry
        res = Resource(resource_id, type=CORPUS)
        info_obj = Info(resource_id, resource=res, owner=auth_data["user"])
        info_obj.create()

        # Create corpus dir with subdirs
        corpus_dir = storage.get_corpus_dir(resource_id, mkdir=True)
        storage.get_source_dir(resource_id, mkdir=True)

        return utils.response(return_code=return_codes.CREATED_RESOURCE, resource_id=resource_id)

    # If anything fails, try to remove from storage, auth system, and registry
    except Exception as e:
        await route_utils.cleanup_partial_resource(
            resource_id=resource_id,
            auth_token=auth_data["auth_token"],
            info_obj=info_obj,
            remove_from_storage_fn=lambda: storage.remove_dir(corpus_dir, resource_id),
        )
        raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_CREATING_RESOURCE, info=str(e)) from e


@router.get(
    "/list-corpora",
    deprecated=True,
    name="list-corpora-deprecated",
)
@router.get(
    "/corpus/list",
    operation_id="list-corpora",
    response_model=sparv_models.ListResourcesResponse,
    responses={**models.common_auth_error_responses},
)
async def list_corpora(auth_data: dict = Depends(AUTH_CORPUS_NO_ID)) -> JSONResponse:
    """List the IDs of all available corpora.

    ### Example

    ```bash
    curl '{{host}}/corpus/list' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    return utils.response(
        return_code=return_codes.LISTING_CONTENT,
        info="Listing available corpus resources",
        resources=auth_data.get("resources"),
    )


@router.get(
    "/list-korp-corpora",
    deprecated=True,
    name="list-korp-corpora-deprecated",
)
@router.get(
    "/corpus/korp/list",
    operation_id="list-korp-corpora",
    response_model=sparv_models.ListResourcesResponse,
    responses={
        status.HTTP_200_OK: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": return_codes.LISTING_CONTENT.message,
                        "return_code": return_codes.LISTING_CONTENT.code,
                        "info": "Listing corpora installed in Korp",
                        "resources": ["mink-dxh6e6wtff", "mink-j86tfreaf9"],
                    }
                }
            }
        },
        **models.common_auth_error_responses,
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": models.ErrorResponse500,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.FAILED_LISTING_CONTENT.message,
                        "return_code": return_codes.FAILED_LISTING_CONTENT.code,
                        "info": "Failed to list corpora installed in Korp",
                    }
                }
            },
        },
    },
)
async def list_korp_corpora(auth_data: dict = Depends(AUTH_CORPUS_NO_ID)) -> JSONResponse:
    """List the IDs of the user's Mink corpora that are installed in Korp.

    This route is deprecated and will be removed in future versions.

    ### Example

    ```bash
    curl '{{host}}/corpus/korp/list' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    installed_corpora = []
    try:
        # Get resource infos belonging to corpora that the user may edit
        resources = registry.filter_resources(auth_data.get("resources"))
        installed_corpora = [res.id for res in resources if isinstance(res.job, SparvJob) and res.job.installed_korp]
    except Exception as e:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.FAILED_LISTING_CONTENT, info=f"Failed to list corpora installed in Korp: {e}"
        ) from e
    return utils.response(
        return_code=return_codes.LISTING_CONTENT, info="Listing corpora installed in Korp", resources=installed_corpora
    )


@router.delete(
    "/remove-corpus",
    deprecated=True,
    name="remove-corpus-deprecated",
)
@router.delete(
    "/corpus/remove/{resource_id}",
    operation_id="remove-corpus",
    response_model=models.BaseResponse,
    responses={
        status.HTTP_200_OK: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": return_codes.REMOVED_RESOURCE.message,
                        "return_code": return_codes.REMOVED_RESOURCE.code,
                    }
                }
            }
        },
        **models.common_auth_error_responses,
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": models.ErrorResponse500,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.FAILED_REMOVING_CONTENT.message,
                        "return_code": return_codes.FAILED_REMOVING_CONTENT.code,
                        "info": "Failed to remove resource from Korp",
                    }
                }
            },
        },
    },
)
async def remove_corpus(auth_data: dict = Depends(AUTH_CORPUS_ADMIN)) -> JSONResponse:
    """Remove a corpus from the storage server.

    Will attempt to abort any running job for this corpus and also remove it from the Sparv server.

    ### Example

    ```bash
    curl -X DELETE '{{host}}/corpus/remove/<resource_id>' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    resource_id = auth_data["resource_id"]
    info_obj = registry.get(resource_id)
    job = _require_job(info_obj.job)

    # Uninstall corpus from Korp using Sparv
    if job.installed_korp:
        try:
            job.uninstall_korp()
        except Exception as e:
            raise exceptions.MinkHTTPException(
                return_code=return_codes.FAILED_REMOVING_CONTENT, info=f"Failed to remove resource from Korp: {e}"
            ) from e

    # Uninstall corpus from Strix using Sparv
    if job.installed_strix:
        try:
            job.uninstall_strix()
        except Exception as e:
            raise exceptions.MinkHTTPException(
                return_code=return_codes.FAILED_REMOVING_CONTENT, info=f"Failed to remove resource from Strix: {e}"
            ) from e

    return await route_utils.remove_resource(
        resource_id=resource_id,
        auth_token=auth_data["auth_token"],
        info_obj=info_obj,
        remove_from_storage_fn=lambda: storage.remove_dir(storage.get_corpus_dir(resource_id), resource_id),
        abort_job=True,
    )


# ------------------------------------------------------------------------------
# Source file operations
# ------------------------------------------------------------------------------


@router.put(
    "/upload-sources",
    deprecated=True,
    name="upload-sources-deprecated",
)
@router.put(
    "/corpus/sources/upload/{resource_id}",
    operation_id="upload-corpus-sources",
    response_model=models.BaseResponse,
    responses={
        status.HTTP_201_CREATED: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": return_codes.FILE_UPLOADED.message,
                        "return_code": return_codes.FILE_UPLOADED.code,
                        "warnings": ["File 'example.txt' already existed and was replaced during upload."],
                    }
                }
            }
        },
        **models.common_auth_error_responses,
        status.HTTP_413_CONTENT_TOO_LARGE: {
            "model": models.ErrorResponse413,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.CONTENT_TOO_LARGE.message,
                        "return_code": return_codes.CONTENT_TOO_LARGE.code,
                        "file": "example.txt",
                        "info": "max file size exceeded",
                        "max_size_mb": 10,
                    }
                }
            },
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": models.ErrorResponse500,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.FAILED_UPLOADING.message,
                        "return_code": return_codes.FAILED_UPLOADING.code,
                        "info": "BaseException",
                    }
                }
            },
        },
    },
)
async def upload_sources(
    request: Request,
    files: list[UploadFile] = File(..., description="The files to upload"),
    auth_data: dict = Depends(AUTH_CORPUS_WRITE),
) -> JSONResponse:
    """Upload the attached files as corpus source files.

    Attached files will be added to the corpus or replace existing ones. Files identical in name, size and md5 checksum
    will not be uploaded again.

    ### Example

    ```bash
    curl -X PUT '{{host}}/corpus/sources/upload/<resource_id>' -H 'Authorization: Bearer YOUR_JWT' \
-F 'files=@path_to_file1' -F 'files=@path_to_file2'
    ```
    """
    resource_id = auth_data["resource_id"]

    # Check request size constraint
    try:
        content_length = int(request.headers.get("content-length", "0"))
        source_dir = storage.get_source_dir(resource_id)
    except Exception as e:
        raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_UPLOADING, info=str(e)) from e
    if not utils.size_ok(storage, source_dir, content_length):
        max_size_mb = int(settings.MAX_RESOURCE_LENGTH / (1024 * 1024))
        raise exceptions.MinkHTTPException(
            return_code=return_codes.CONTENT_TOO_LARGE,
            info="max corpus size exceeded",
            max_size_mb=max_size_mb,
        )

    existing_files = storage.list_contents(source_dir)
    max_file_size_mb = int(settings.MAX_FILE_LENGTH / (1024 * 1024))
    warnings = []
    spec = get_spec(CORPUS)

    # Upload data
    for f in files:
        if f.filename is None:
            raise exceptions.MinkHTTPException(return_code=return_codes.INVALID_FILE, info="missing filename")
        name = utils.secure_filename(f.filename)
        original_name = name

        # Make sure the file suffix is lower case (issue warning later if name was changed)
        if name.suffix.lower() != name.suffix:
            name = Path(name.stem + name.suffix.lower())

        # Check if file can be processed by Sparv
        if spec.allowed_extensions and not any(name.suffix.lower() == i.lower() for i in spec.allowed_extensions):
            raise exceptions.MinkHTTPException(
                return_code=return_codes.INVALID_FILE, file=f.filename, info="invalid file extension"
            )

        # Check if file extension is compatible with existing files
        compatible, current_ext, existing_ext = sparv_utils.file_ext_compatible(name, source_dir)
        if not compatible:
            raise exceptions.MinkHTTPException(
                return_code=return_codes.INVALID_FILE,
                file=f.filename,
                info="incompatible file extensions",
                current_file_extension=current_ext,
                existing_file_extension=existing_ext,
            )

        # Check file size constraint
        file_contents = await f.read()
        if len(file_contents) > settings.MAX_FILE_LENGTH:
            raise exceptions.MinkHTTPException(
                return_code=return_codes.CONTENT_TOO_LARGE,
                file=f.filename,
                info="max file size exceeded",
                max_size_mb=max_file_size_mb,
            )

        # Skip uploading existing files (identical in name, size and md5 checksum)
        if str(name) in [i.get("name") for i in existing_files]:
            if sparv_utils.identical_file_exists(file_contents, source_dir / name):
                if name == original_name:
                    # File with same name is identical; it will not be replaced during upload
                    warnings.append(
                        f"File '{name}' already existed with the same name, size and content. File was "
                        "not uploaded again."
                    )
                    continue
                # File extension was changed during upload and a file was replaced
                warnings.append(
                    f"File '{original_name}' did not have a lower case file extension. Its name was "
                    f"changed to '{name}' during upload and it replaced an existing file with the same "
                    "name."
                )
            else:
                # File with same name is not identical; it will be replaced during upload
                warnings.append(f"File called '{name}' already existed and was replaced during upload.")
        # File extension was changed during upload (but no files were replaced)
        elif name != original_name:
            warnings.append(
                f"File '{original_name}' did not have a lower case file extension. Its name was "
                f"changed to '{name}' during upload."
            )

        # Validate XML files
        if current_ext == ".xml":
            try:
                ElementTree.fromstring(file_contents)
            except ElementTree.ParseError as e:
                raise exceptions.MinkHTTPException(
                    return_code=return_codes.INVALID_FILE,
                    file=f.filename,
                    info=f"invalid XML: {e}",
                ) from e
        storage.write_file_contents(source_dir / name, file_contents, resource_id)

    res = registry.get(resource_id).resource
    res.set_source_files()

    # Check if file extensions were changed during the upload process and produce a warning
    if warnings:
        logger.warning("Warnings occurred during upload:\n%s", "\n".join(warnings))
    return utils.response(return_code=return_codes.FILE_UPLOADED, warnings=warnings)


@router.get(
    "/list-sources",
    deprecated=True,
    name="list-sources-deprecated",
)
@router.get(
    "/corpus/sources/list/{resource_id}",
    operation_id="list-corpus-sources",
    response_model=models.ListingFilesResponse,
    responses={
        status.HTTP_200_OK: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": return_codes.LISTING_CONTENT.message,
                        "return_code": return_codes.LISTING_CONTENT.code,
                        "info": "Listing source files",
                        "contents": models.file_model_examples,
                    }
                }
            },
        },
        **models.common_auth_error_responses,
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": models.ErrorResponse500,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.FAILED_LISTING_CONTENT.message,
                        "return_code": return_codes.FAILED_LISTING_CONTENT.code,
                        "info": "Failed to list source files",
                    }
                }
            },
        },
    },
)
async def list_sources(auth_data: dict = Depends(AUTH_CORPUS)) -> JSONResponse:
    """List the available corpus source files.

    ### Example

    ```bash
    curl '{{host}}/corpus/sources/list/<resource_id>' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    resource_id = auth_data["resource_id"]
    try:
        objlist = storage.list_contents(storage.get_source_dir(resource_id))
        return utils.response(
            return_code=return_codes.LISTING_CONTENT,
            info="Listing source files",
            contents=objlist,
        )
    except Exception as e:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.FAILED_LISTING_CONTENT, info=f"Failed to list source files: {e}"
        ) from e


@router.delete(
    "/remove-sources",
    deprecated=True,
    name="remove-sources-deprecated",
)
@router.delete(
    "/corpus/sources/remove/{resource_id}",
    operation_id="remove-corpus-sources",
    response_model=models.BaseResponse,
    responses={
        status.HTTP_200_OK: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": return_codes.REMOVED_CONTENT.message,
                        "return_code": return_codes.REMOVED_CONTENT.code,
                        "info": "Removed source files",
                    }
                }
            }
        },
        **models.common_auth_error_responses,
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "model": models.BaseErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.VALIDATION_ERROR.message,
                        "return_code": return_codes.VALIDATION_ERROR.code,
                        "info": "Missing required query parameter 'remove'",
                    }
                }
            },
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": models.ErrorResponse500,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.FAILED_REMOVING_CONTENT.message,
                        "return_code": return_codes.FAILED_REMOVING_CONTENT.code,
                        "info": "Failed to remove some source files",
                        "failed": ["file1.xml", "file2.xml"],
                        "succeeded": ["file3.xml"],
                    }
                }
            },
        },
    },
)
async def remove_sources(
    remove: list[str] = Query(..., description="Files to remove, comma-separated"),
    auth_data: dict = Depends(AUTH_CORPUS_WRITE),
) -> JSONResponse:
    """Remove the source files given in the `remove` parameter from the corpus.

    Files are provided as a comma-separated list of paths relative to the source directory. If any files could not be
    removed they will be listed in the error response.

    ### Example

    ```bash
    curl -X DELETE '{{host}}/corpus/sources/remove/<resource_id>?remove=file1,file2' \
-H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    if not remove:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.VALIDATION_ERROR, info="Missing required query parameter 'remove'"
        )

    # Remove files
    resource_id = auth_data["resource_id"]
    successes = []
    fails = []
    for rf in remove:
        storage_path = storage.get_source_dir(resource_id) / rf
        try:
            storage.remove_file(storage_path, resource_id)
            successes.append(rf)
        except Exception:
            fails.append(rf)

    if fails and successes:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.FAILED_REMOVING_CONTENT,
            info="Failed to remove some source files",
            failed=fails,
            succeeded=successes,
        )
    if fails:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.FAILED_REMOVING_CONTENT, info="Failed to remove source files"
        )

    res = registry.get(resource_id).resource
    res.set_source_files(deleted_sources=True)

    return utils.response(return_code=return_codes.REMOVED_CONTENT, info="Removed source files")


@router.get(
    "/download-sources",
    deprecated=True,
    name="download-sources-deprecated",
)
@router.get(
    "/corpus/sources/download/{resource_id}",
    operation_id="download-corpus-sources",
    response_model=models.FileResponse,
    response_class=FileResponse,
    responses={
        status.HTTP_200_OK: {"content": {"application/octet-stream": {}}, "description": "A file download response"},
        **models.common_auth_error_responses,
        status.HTTP_404_NOT_FOUND: {"model": models.ErrorResponse404File},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": models.ErrorResponse500,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.FAILED_DOWNLOADING.message,
                        "return_code": return_codes.FAILED_DOWNLOADING.code,
                        "info": "BaseException",
                    }
                }
            },
        },
    },
)
async def download_sources(
    download_file: str | None = Query(None, alias="file", description="The file name or path to download"),
    zipped: bool = Query(False, alias="zip", description="Whether to zip the file or not"),
    auth_data: dict = Depends(AUTH_CORPUS),
) -> FileResponse:
    """Download the corpus source files as a zip file.

    The parameter `file` may be used to download a specific source file. This parameter must either be a file name or an
    absolute path on the Storage server. The `zip` parameter may be set to `false` in combination with the file param to
    avoid zipping the file to be downloaded.

    ### Example

    ```bash
    curl '{{host}}/corpus/sources/download/<resource_id>?file=some_file_name&zip=true' \
-H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    resource_id = auth_data["resource_id"]
    try:
        # Check if there are any source files
        storage_source_dir = storage.get_source_dir(resource_id)
        source_contents = storage.list_contents(storage_source_dir, exclude_dirs=False)
    except Exception as e:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.FAILED_DOWNLOADING, info=f"Failed to list source files: {e}"
        ) from e
    if source_contents == []:
        raise exceptions.MinkHTTPException(return_code=return_codes.FILE_NOT_FOUND)

    local_source_dir = storage.get_local_source_dir(resource_id, mkdir=True)
    local_corpus_dir = storage.get_local_resource_dir(resource_id, mkdir=True)

    # Download and zip file specified in args
    if download_file:
        download_file_name = Path(download_file).name
        download_file_path = storage_source_dir / download_file
        if download_file not in [i.get("path") for i in source_contents]:
            raise exceptions.MinkHTTPException(return_code=return_codes.FILE_NOT_FOUND)
        try:
            local_path = local_source_dir / download_file_name
            storage.download_file(download_file_path, local_path, resource_id)
            if zipped:
                outfile_path = local_corpus_dir / f"{resource_id}_{download_file_name}.zip"
                utils.create_zip(local_path, outfile_path, zip_rootdir=resource_id)
                return FileResponse(outfile_path, media_type="application/zip", filename=outfile_path.name)
            # Determine content type
            content_type = "application/xml"
            for file_obj in source_contents:
                if file_obj.get("name") == download_file_name:
                    content_type = file_obj.get("type")
                    break
            return FileResponse(local_path, media_type=content_type, filename=local_path.name)
        except FileNotFoundError as e:
            raise exceptions.MinkHTTPException(return_code=return_codes.FILE_NOT_FOUND, info=str(e)) from e
        except Exception as e:
            raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_DOWNLOADING, info=str(e)) from e

    # Download all files as zip archive
    try:
        zip_out = local_corpus_dir / f"{resource_id}_source.zip"
        # Get files from storage server
        storage.download_dir(storage_source_dir, local_source_dir, resource_id, zipped=True, zippath=zip_out)
        return FileResponse(zip_out, media_type="application/zip", filename=zip_out.name)
    except Exception as e:
        raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_DOWNLOADING, info=str(e)) from e


# ------------------------------------------------------------------------------
# Config file operations
# ------------------------------------------------------------------------------


@router.put(
    "/upload-config",
    deprecated=True,
    name="upload-config-deprecated",
)
@router.put(
    "/corpus/config/upload/{resource_id}",
    operation_id="upload-corpus-config",
    status_code=status.HTTP_201_CREATED,
    response_model=models.BaseResponse,
    responses={
        status.HTTP_201_CREATED: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": return_codes.FILE_UPLOADED.message,
                        "return_code": return_codes.FILE_UPLOADED.code,
                    }
                }
            }
        },
        **models.common_auth_error_responses,
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "model": models.BaseErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.VALIDATION_ERROR.message,
                        "return_code": return_codes.VALIDATION_ERROR.code,
                        "info": "Both a file and plain text config were provided"
                    }
                }
            },
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": models.ErrorResponse500,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.FAILED_UPLOADING.message,
                        "return_code": return_codes.FAILED_UPLOADING.code,
                        "info": "BaseException",
                    }
                }
            },
        },
    },
)
async def upload_config(
    yaml_file: UploadFile | None = models.upload_file_opt_param,
    yaml_txt: str | None = Query(None, alias="config", description="The config file as plain text"),
    auth_data: dict = Depends(AUTH_CORPUS_WRITE),
) -> JSONResponse:
    """Upload a corpus configuration as file or plain text (using the `config` parameter).

    The config must be in yaml format. Read more about corpus config files in the [Sparv Pipeline
    documentation](https://spraakbanken.gu.se/sparv/user-manual/corpus-configuration).

    If a config file already exists for the given corpus it will be replaced by the newly uploaded one.

    Please note that any yaml comments may be removed from your config upon upload.

    ### Example

    ```bash
    curl -X PUT '{{host}}/corpus/config/upload/<resource_id>' -H 'Authorization: Bearer YOUR_JWT' \
-F 'file=@path_to_config_file'
    ```
    """
    resource_id = auth_data["resource_id"]
    config_path = storage.get_config_file(resource_id)
    source_files = storage.list_contents(storage.get_source_dir(resource_id))

    return await route_utils.upload_yaml_file(
        yaml_file=yaml_file,
        yaml_txt=yaml_txt,
        res_obj=registry.get(resource_id).resource,
        standardize_fn=lambda contents: sparv_utils.standardize_config(contents, resource_id),
        write_fn=lambda data: storage.write_file_contents(config_path, data, resource_id),
        validate_fn=lambda contents: sparv_utils.require_compatible_config(contents, source_files),
    )


@router.get(
    "/download-config",
    deprecated=True,
    name="download-config-deprecated",
)
@router.get(
    "/corpus/config/download/{resource_id}",
    operation_id="download-corpus-config",
    response_model=models.FileResponse,
    response_class=FileResponse,
    responses={
        status.HTTP_200_OK: {"content": {"application/octet-stream": {}}, "description": "A file download response"},
        **models.common_auth_error_responses,
        status.HTTP_404_NOT_FOUND: {"model": models.ErrorResponse404File},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": models.ErrorResponse500,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.FAILED_DOWNLOADING.message,
                        "return_code": return_codes.FAILED_DOWNLOADING.code,
                        "info": "BaseException",
                    }
                }
            },
        },
    },
)
async def download_config(auth_data: dict = Depends(AUTH_CORPUS)) -> FileResponse:
    """Download the corpus config file in YAML format.

    ### Example

    ```bash
    curl '{{host}}/corpus/config/download/<resource_id>' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    resource_id = auth_data["resource_id"]
    storage_yaml_file = storage.get_config_file(resource_id)
    local_yaml_file = storage.get_local_config_file(resource_id)
    return route_utils.download_file_response(
        local_path=local_yaml_file,
        ensure_local_dir_fn=lambda: storage.get_local_source_dir(resource_id, mkdir=True),
        download_fn=lambda: storage.download_file(storage_yaml_file, local_yaml_file, resource_id),
        media_type="text/yaml",
    )


# ------------------------------------------------------------------------------
# Export file operations
# ------------------------------------------------------------------------------


@router.get(
    "/list-exports",
    deprecated=True,
    name="list-exports-deprecated",
)
@router.get(
    "/corpus/exports/list/{resource_id}",
    operation_id="list-corpus-exports",
    response_model=models.ListingFilesResponse,
    responses={
        status.HTTP_200_OK: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": return_codes.LISTING_CONTENT.message,
                        "return_code": return_codes.LISTING_CONTENT.code,
                        "info": "Listing export files",
                        "contents": [
                            {
                                "name": "dokument1.csv",
                                "type": "text/csv",
                                "last_modified": "2022-06-10T17:55:37+02:00",
                                "size": 4876,
                                "path": "csv_export/dokument1.csv",
                            },
                            {
                                "name": "dokument1_export.xml",
                                "type": "application/xml",
                                "last_modified": "2022-06-10T17:55:38+02:00",
                                "size": 13429,
                                "path": "xml_export.pretty/dokument1_export.xml",
                            },
                        ],
                    }
                }
            },
        },
        **models.common_auth_error_responses,
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": models.ErrorResponse500,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.FAILED_LISTING_CONTENT.message,
                        "return_code": return_codes.FAILED_LISTING_CONTENT.code,
                        "info": "Failed to list export files",
                    }
                }
            },
        },
    },
)
async def list_exports(auth_data: dict = Depends(AUTH_CORPUS)) -> JSONResponse:
    """List the available export files created by Sparv.

    ### Example

    ```bash
    curl '{{host}}/corpus/exports/list/<resource_id>' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    resource_id = auth_data["resource_id"]
    try:
        objlist = storage.list_contents(
            storage.get_export_dir(resource_id), blacklist=sparv_settings.SPARV_EXPORT_BLACKLIST
        )
        return utils.response(return_code=return_codes.LISTING_CONTENT, info="Listing export files", contents=objlist)
    except Exception as e:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.FAILED_LISTING_CONTENT, info=f"Failed to list export files: {e}"
        ) from e


@router.get(
    "/download-exports",
    deprecated=True,
    name="download-exports-deprecated",
)
@router.get(
    "/corpus/exports/download/{resource_id}",
    operation_id="download-corpus-exports",
    response_model=models.FileResponse,
    response_class=FileResponse,
    responses={
        status.HTTP_200_OK: {"content": {"application/octet-stream": {}}, "description": "A file download response"},
        **models.common_auth_error_responses,
        status.HTTP_404_NOT_FOUND: {"model": models.ErrorResponse404File},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "model": models.BaseErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.VALIDATION_ERROR.message,
                        "return_code": return_codes.VALIDATION_ERROR.code,
                        "info": "Both 'file' and 'dir' parameters were provided"
                    }
                }
            },
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": models.ErrorResponse500,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.FAILED_DOWNLOADING.message,
                        "return_code": return_codes.FAILED_DOWNLOADING.code,
                        "info": "BaseException",
                    }
                }
            },
        },
    },
)
async def download_exports(
    download_file: str | None = Query(None, alias="file", description="The file name or path to download"),
    download_folder: str | None = Query(None, alias="dir", description="The directory to download"),
    zipped: bool = Query(True, alias="zip", description="Whether to zip the file or not"),
    auth_data: dict = Depends(AUTH_CORPUS),
) -> FileResponse:
    """Download all available export files created by Sparv.

    The parameters `file` and `dir` may be used to download a specific export file or a directory of export files. These
    parameters must be supplied as  paths relative to the export directory. Only one of these parameters may be applied
    at a time.

    The `zip` parameter may be set to `false` in combination with the `file` param to avoid zipping the file to be
    downloaded. If `zip` is used without the file parameter it will have no effect.

    ### Example

    ```bash
    curl '{{host}}/corpus/exports/download/<resource_id>?file=some_file_name&zip=true' \
-H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    if download_file and download_folder:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.VALIDATION_ERROR, info="Both 'file' and 'dir' parameters were provided"
        )

    resource_id = auth_data["resource_id"]
    storage_export_dir = storage.get_export_dir(resource_id)
    local_corpus_dir = storage.get_local_resource_dir(resource_id, mkdir=True)
    local_export_dir = storage.get_local_export_dir(resource_id, mkdir=True)
    blacklist = sparv_settings.SPARV_EXPORT_BLACKLIST

    try:
        export_contents = storage.list_contents(storage_export_dir, exclude_dirs=False, blacklist=blacklist)
    except Exception as e:
        raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_DOWNLOADING, info=str(e)) from e
    if export_contents == []:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.FILE_NOT_FOUND, info="No exports available for corpus"
        )

    # Download and zip folder specified in args
    if download_folder:
        download_folder_name = "_".join(Path(download_folder).parts)
        full_download_folder = storage_export_dir / download_folder
        if download_folder not in [i.get("path") for i in export_contents]:
            logger.error(
                "Requested download folder '%s' not found in export contents for corpus '%s'",
                download_folder,
                resource_id,
            )
            raise exceptions.MinkHTTPException(return_code=return_codes.FILE_NOT_FOUND)
        try:
            zip_out = local_corpus_dir / f"{resource_id}_{download_folder_name}.zip"
            (local_export_dir / download_folder).mkdir(exist_ok=True)
            storage.download_dir(
                full_download_folder, local_export_dir / download_folder, resource_id, zipped=True, zippath=zip_out
            )
            return FileResponse(zip_out, media_type="application/zip", filename=zip_out.name)
        except Exception as e:
            raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_DOWNLOADING, info=str(e)) from e

    # Download and zip file specified in args
    if download_file:
        download_file_name = Path(download_file).name
        download_file_path = storage_export_dir / download_file
        if download_file not in [i.get("path") for i in export_contents]:
            raise exceptions.MinkHTTPException(return_code=return_codes.FILE_NOT_FOUND, file=download_file)
        try:
            local_path = local_export_dir / download_file
            (local_export_dir / download_file).parent.mkdir(exist_ok=True)
            if zipped:
                outfile_path = local_corpus_dir / f"{resource_id}_{download_file_name}.zip"
                storage.download_file(download_file_path, local_path, resource_id)
                utils.create_zip(local_path, outfile_path, zip_rootdir=resource_id)
                return FileResponse(outfile_path, media_type="application/zip", filename=outfile_path.name)
            storage.download_file(download_file_path, local_path, resource_id)
            # Determine content type
            content_type = "application/xml"
            for file_obj in export_contents:
                if file_obj.get("name") == download_file_name:
                    content_type = file_obj.get("type")
                    break
            return FileResponse(local_path, media_type=content_type, filename=local_path.name)
        except FileNotFoundError as e:
            raise exceptions.MinkHTTPException(return_code=return_codes.FILE_NOT_FOUND, info=str(e)) from e
        except Exception as e:
            raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_DOWNLOADING, info=str(e)) from e

    # Download all export files (if not (download_file or download_folder))
    else:
        try:
            zip_out = local_corpus_dir / f"{resource_id}_export.zip"
            # Get files from storage server
            storage.download_dir(
                storage_export_dir, local_export_dir, resource_id, zipped=True, zippath=zip_out, excludes=blacklist
            )
            return FileResponse(zip_out, media_type="application/zip", filename=zip_out.name)
        except Exception as e:
            raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_DOWNLOADING, info=str(e)) from e


@router.delete(
    "/remove-exports",
    deprecated=True,
    name="remove-exports-deprecated",
)
@router.delete(
    "/corpus/exports/remove/{resource_id}",
    operation_id="remove-corpus-exports",
    response_model=models.BaseResponse,
    responses={
        status.HTTP_200_OK: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": return_codes.REMOVED_CONTENT.message,
                        "return_code": return_codes.REMOVED_CONTENT.code,
                        "info": "Removed export files"
                    },
                }
            },
        },
        **models.common_auth_error_responses,
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": models.ErrorResponse500,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.FAILED_REMOVING_CONTENT.message,
                        "return_code": return_codes.FAILED_REMOVING_CONTENT.code,
                        "info": "Failed to remove export files",
                    }
                }
            },
        },
    },
)
async def remove_exports(auth_data: dict = Depends(AUTH_CORPUS_WRITE)) -> JSONResponse:
    """Remove all export files for the corpus from the storage server.

    Will attempt to remove exports from the Sparv server, too, but won't crash if this fails.

    ### Example

    ```bash
    curl -X DELETE '{{host}}/corpus/exports/remove/<resource_id>' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    resource_id = auth_data["resource_id"]
    if not storage.local:
        try:
            # Remove export dir from storage server and create a new empty one
            storage.remove_dir(storage.get_export_dir(resource_id), resource_id)
            storage.get_export_dir(resource_id, mkdir=True)
        except Exception as e:
            raise exceptions.MinkHTTPException(
                return_code=return_codes.FAILED_REMOVING_CONTENT,
                info=f"Failed to remove export files from storage server: {e}",
            ) from e

    try:
        # Remove from Sparv server
        job = _require_job(registry.get(resource_id).job)
        success, sparv_output = job.clean_export()
    except Exception as e:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.FAILED_REMOVING_CONTENT,
            info=f"Failed to remove export files from Sparv server: {e}",
        ) from e
    if not success:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.FAILED_REMOVING_CONTENT,
            info=f"Failed to remove export files from Sparv server: {sparv_output}",
        )

    return utils.response(return_code=return_codes.REMOVED_CONTENT, info="Removed export files")


@router.get(
    "/download-source-text",
    deprecated=True,
    response_model=models.FileResponse,
    response_class=FileResponse,
    responses={
        status.HTTP_200_OK: {"content": {"text/plain": {}}, "description": "A file download response"},
        **models.common_auth_error_responses,
        status.HTTP_404_NOT_FOUND: {"model": models.ErrorResponse404File},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "model": models.BaseErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.VALIDATION_ERROR.message,
                        "return_code": return_codes.VALIDATION_ERROR.code,
                        "info": "Missing required query parameter 'file'"
                    }
                }
            },
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": models.ErrorResponse500,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.FAILED_DOWNLOADING.message,
                        "return_code": return_codes.FAILED_DOWNLOADING.code,
                        "info": "BaseException",
                    }
                }
            },
        },
    },
)
async def download_source_text(
    download_file: str = Query(..., alias="file", description="The file name to download"),
    auth_data: dict = Depends(AUTH_CORPUS),
) -> FileResponse:
    """Download one of the source files in plain text.

    The plain text is extracted by Sparv and therefore it can only be requested after a completed Sparv job.
    The source file name (including its file extension) must be specified in the `file` parameter.

    ### Example

    ```bash
    curl '{{host}}/download-source-text?resource_id=<resource_id>&file=some_file_name' \
-H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    resource_id = auth_data["resource_id"]
    storage_work_dir = storage.get_work_dir(resource_id)
    local_corpus_dir = storage.get_local_resource_dir(resource_id, mkdir=True)

    if not download_file:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.VALIDATION_ERROR, info="Missing required query parameter 'file'"
        )

    file_stem = Path(download_file).stem
    download_file_path = (
        storage_work_dir / Path(download_file).parent / file_stem / sparv_settings.SPARV_PLAIN_TEXT_FILE
    )

    # Check if file exists
    try:
        storage.get_file_info(download_file_path)
    except exceptions.ReadError as e:
        raise exceptions.MinkHTTPException(return_code=return_codes.FILE_NOT_FOUND) from e
    except Exception as e:
        raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_DOWNLOADING, info=str(e)) from e

    # Download and return file
    try:
        out_file_name = file_stem + "_plain.txt"
        local_path = local_corpus_dir / out_file_name
        storage.download_file(download_file_path, local_path, resource_id)
        utils.uncompress_gzip(local_path)
        utils.unpickle_file(local_path)
        return FileResponse(local_path, media_type="text/plain", filename=local_path.name)
    except FileNotFoundError as e:
        raise exceptions.MinkHTTPException(return_code=return_codes.FILE_NOT_FOUND, info=str(e)) from e
    except Exception as e:
        raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_DOWNLOADING, info=str(e)) from e


@router.get(
    "/check-changes",
    deprecated=True,
    name="check-changes-deprecated",
)
@router.get(
    "/corpus/job/check-input/{resource_id}",
    operation_id="check-corpus-input",
    response_model=sparv_models.CheckInputResponse,
    responses={
        **models.common_auth_error_responses,
        status.HTTP_404_NOT_FOUND: {
            "model": models.ErrorResponse404Resource,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.RESOURCE_NOT_PROCESSED.message,
                        "return_code": return_codes.RESOURCE_NOT_PROCESSED.code,
                    }
                }
            },
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": models.ErrorResponse500,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.FAILED_CHECKING_STATUS.message,
                        "return_code": return_codes.FAILED_CHECKING_STATUS.code,
                        "info": "BaseException",
                    }
                }
            },
        },
    },
)
async def check_input(auth_data: dict = Depends(AUTH_CORPUS)) -> JSONResponse:
    """Check for any changes in the config and source files since the last Sparv job was started.

    Those changes include added and deleted source files.

    ### Example

    ```bash
    curl -X GET '{{host}}/corpus/job/check-input/<resource_id>' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    resource_id = auth_data["resource_id"]
    try:
        info_item = registry.get(resource_id)
    except Exception as e:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.FAILED_GETTING_JOB, info=f"Error getting job info for resource: {e}"
        ) from e
    try:
        sources_changed, sources_deleted, config_changed = storage.get_file_changes(resource_id, info_item)
        input_changed = sources_changed or sources_deleted or config_changed
        job = _require_job(info_item.job)
        return utils.response(
            return_code=return_codes.CHECKED_STATUS,
            info=f"The input has {'not ' if not input_changed else ''}changed since the last run",
            input_changed=input_changed,
            config_changed=config_changed,
            sources_changed=sources_changed,
            sources_deleted=sources_deleted,
            last_run_started=job.started,
        )

    except exceptions.JobNotFoundError as e:
        raise exceptions.MinkHTTPException(return_code=return_codes.RESOURCE_NOT_PROCESSED) from e

    except Exception as e:
        raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_CHECKING_STATUS, info=str(e)) from e
