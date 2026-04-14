"""Routes for lexicon resources."""

from typing import cast

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse

from mink.cache import jobs_cache
from mink.core import exceptions, models, registry, return_codes, route_utils, utils
from mink.core.config import settings
from mink.core.info import Info
from mink.core.resource import Resource
from mink.core.resource_specs import get_spec
from mink.karp import models as karp_models
from mink.karp import utils as karp_utils
from mink.karp.jobs import KarpJob
from mink.karp.spec import LEXICON
from mink.karp.storage import storage
from mink.sb_auth import login

router = APIRouter(tags=["Manage Lexicons"], prefix="/lexicon")
SBAUTH_LEXICON = get_spec(LEXICON).sbauth_resource_type
AUTH_LEXICON = login.AuthDependency(sbauth_resource_type=SBAUTH_LEXICON)
AUTH_WRITE = login.AuthDependency(min_level="WRITE", sbauth_resource_type=SBAUTH_LEXICON)
AUTH_ADMIN = login.AuthDependency(min_level="ADMIN", sbauth_resource_type=SBAUTH_LEXICON)
AUTH_NO_ID = login.AuthDependencyNoResourceId(sbauth_resource_type=SBAUTH_LEXICON)


def _require_job(job: object) -> KarpJob:
    """Ensure that 'job' is a Karp job, raise an error if not."""
    if not isinstance(job, KarpJob):
        raise exceptions.MinkHTTPException(
            return_code=return_codes.INVALID_RESOURCE_TYPE, info="Expected a lexicon resource"
        )
    return cast(KarpJob, job)


# ------------------------------------------------------------------------------
# Resource management
# ------------------------------------------------------------------------------

@router.post(
    "/create",
    operation_id="create-lexicon",
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
async def create_lexicon(auth_data: dict = Depends(AUTH_NO_ID)) -> JSONResponse:
    """Create a new lexicon.

    ### Example

    ```bash
    curl -X POST '{{host}}/lexicon/create' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    resource_id = await route_utils.create_resource_id(
        auth_token=auth_data["auth_token"],
        resource_type=get_spec(LEXICON).sbauth_resource_type,
        existing_ids_fn=jobs_cache.get_all_resources,
        resource_prefix=settings.RESOURCE_PREFIX,
    )
    resource_dir = storage.get_resource_dir(resource_id)

    try:
        # Create info object in registry
        res = Resource(id=resource_id, type=LEXICON)
        info_obj = Info(resource_id, resource=res, owner=auth_data["user"])
        info_obj.create()

        # Create resource dir with subdirs
        storage.get_resource_dir(resource_id, mkdir=True)
        storage.get_source_dir(resource_id, mkdir=True)

        return utils.response(return_code=return_codes.CREATED_RESOURCE, resource_id=resource_id)

    # If anything fails, try to remove from storage, auth system, and registry
    except Exception as e:
        await route_utils.cleanup_partial_resource(
            resource_id=resource_id,
            auth_token=auth_data["auth_token"],
            info_obj=info_obj or None,
            remove_from_storage_fn=lambda: storage.remove_dir(resource_dir, resource_id),
        )
        raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_CREATING_RESOURCE, info=str(e)) from e


@router.get(
    "/list",
    operation_id="list-lexicons",
    response_model=karp_models.ListResourcesResponse,
    responses={**models.common_auth_error_responses},
)
async def list_lexicons(auth_data: dict = Depends(AUTH_NO_ID)) -> JSONResponse:
    """List the IDs of all available lexicons.

    ### Example

    ```bash
    curl '{{host}}/lexicon/list' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    return utils.response(
        return_code=return_codes.LISTING_CONTENT,
        info="Listing available lexicons",
        resources=auth_data.get("resources", []),
    )


@router.delete(
    "/remove/{resource_id}",
    operation_id="remove-lexicon",
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
                        "info": "Failed to remove resource from KarpS",
                    }
                }
            },
        },
    },
)
async def remove_lexicon(auth_data: dict = Depends(AUTH_ADMIN)) -> JSONResponse:
    """Remove a lexicon from the storage server.

    Will attempt to abort any running job for this lexicon and also remove it from the Karp server.

    ### Example

    ```bash
    curl -X DELETE '{{host}}/lexicon/remove/<resource_id>' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    resource_id = auth_data["resource_id"]
    info_obj = registry.get(resource_id)
    job = _require_job(info_obj.job)

    # Uninstall lexicon from KarpS
    if job.installed_karps:
        try:
            job.uninstall_karps()
        except Exception as e:
            raise exceptions.MinkHTTPException(
                return_code=return_codes.FAILED_REMOVING_CONTENT, info=f"Failed to remove resource from KarpS: {e}"
            ) from e

    return await route_utils.remove_resource(
        resource_id=resource_id,
        auth_token=auth_data["auth_token"],
        info_obj=info_obj,
        remove_from_storage_fn=lambda: storage.remove_dir(storage.get_resource_dir(resource_id), resource_id),
        abort_job=True,
    )


# ------------------------------------------------------------------------------
# Source file operations
# ------------------------------------------------------------------------------

@router.put(
    "/sources/upload/{resource_id}",
    operation_id="upload-lexicon-sources",
    response_model=models.BaseResponse,
    responses={
        status.HTTP_201_CREATED: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": return_codes.FILE_UPLOADED.message,
                        "return_code": return_codes.FILE_UPLOADED.code,
                        "warnings": ["File 'example.jsonl' already existed and was replaced during upload."],
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
    source_file: UploadFile = File(..., alias="file", description="The file to upload"),
    auth_data: dict = Depends(AUTH_WRITE),
) -> JSONResponse:
    """Upload the attached file as source file.

    ### Example

    ```bash
    curl -X PUT '{{host}}/lexicon/sources/upload/<resource_id>' -H 'Authorization: Bearer YOUR_JWT' \
-F 'file=@path_to_file'
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
            info="max resource size exceeded",
            max_size_mb=max_size_mb,
        )

    # Check if resource already has a source file and abort if if does
    existing_files = storage.list_contents(source_dir)
    if existing_files:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.METHOD_NOT_ALLOWED,
            info="Only one source file is allowed per resource. Remove the existing source file before uploading a new "
            "one or create a new resource.",
        )

    max_file_size_mb = int(settings.MAX_FILE_LENGTH / (1024 * 1024))
    spec = get_spec(LEXICON)

    # Check if file has a name
    if source_file.filename is None:
        raise exceptions.MinkHTTPException(return_code=return_codes.INVALID_FILE, info="missing filename")
    name = utils.secure_filename(source_file.filename)

    # Check if file extension is allowed for this resource type
    if spec.allowed_extensions and not any(name.suffix.lower() == i.lower() for i in spec.allowed_extensions):
        raise exceptions.MinkHTTPException(
            return_code=return_codes.INVALID_FILE, file=source_file.filename, info="invalid file extension"
        )

    # Check file size constraint
    file_contents = await source_file.read()
    if len(file_contents) > settings.MAX_FILE_LENGTH:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.CONTENT_TOO_LARGE,
            file=source_file.filename,
            info="max file size exceeded",
            max_size_mb=max_file_size_mb,
        )

    # Upload data
    storage.write_file_contents(source_dir / name, file_contents, resource_id)

    res = registry.get(resource_id).resource
    res.set_source_files()

    return utils.response(return_code=return_codes.FILE_UPLOADED)


@router.get(
    "/sources/list/{resource_id}",
    operation_id="list-lexicon-sources",
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
async def list_sources(auth_data: dict = Depends(AUTH_LEXICON)) -> JSONResponse:
    """List the available source files.

    ### Example

    ```bash
    curl '{{host}}/lexicon/sources/list/<resource_id>' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    try:
        objlist = storage.list_contents(storage.get_source_dir(auth_data["resource_id"]))
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
    "/sources/remove/{resource_id}",
    operation_id="remove-lexicon-sources",
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
    remove: str = Query(..., description="File to remove, given as path relative to the source directory"),
    auth_data: dict = Depends(AUTH_WRITE),
) -> JSONResponse:
    """Remove the source file given in the `remove` parameter from the resource.

    The file is provided as path relative to the source directory.

    ### Example

    ```bash
    curl -X DELETE '{{host}}/lexicon/sources/remove/<resource_id>?remove=<file1.jsonl>' \
-H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    # Remove files
    resource_id = auth_data["resource_id"]
    storage_path = storage.get_source_dir(resource_id) / remove
    success = True
    try:
        storage.remove_file(storage_path, resource_id)
    except Exception:
        success = False

    if not success:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.FAILED_REMOVING_CONTENT, info="Failed to remove source file"
        )

    res = registry.get(resource_id).resource
    res.set_source_files(deleted_sources=True)

    return utils.response(return_code=return_codes.REMOVED_CONTENT, info="Removed source files")


@router.get(
    "/sources/download/{resource_id}",
    operation_id="download-lexicon-sources",
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
    zipped: bool = Query(False, alias="zip", description="Whether to zip the file or not"),
    auth_data: dict = Depends(AUTH_LEXICON),
) -> FileResponse:
    """Download the source file.

    Download as zip if the `zip` query parameter is set to `true`.

    ### Example

    ```bash
    curl '{{host}}/lexicon/sources/download/<resource_id>&zip=true' -H 'Authorization: Bearer YOUR_JWT'
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
    local_resource_dir = storage.get_local_resource_dir(resource_id, mkdir=True)

    # Download and zip source file
    download_file = source_contents[0]
    download_file_name = download_file.get("name")
    download_file_path = storage_source_dir / download_file.get("path")
    download_file_type = download_file.get("type")

    try:
        local_path = local_source_dir / download_file_name
        storage.download_file(download_file_path, local_path, resource_id)
        if zipped:
            outfile_path = local_resource_dir / f"{resource_id}_{download_file_name}.zip"
            utils.create_zip(local_path, outfile_path, zip_rootdir=resource_id)
            return FileResponse(outfile_path, media_type="application/zip", filename=outfile_path.name)
        # Unzippped download
        return FileResponse(local_path, media_type=download_file_type, filename=local_path.name)

    except FileNotFoundError as e:
        raise exceptions.MinkHTTPException(return_code=return_codes.FILE_NOT_FOUND, info=str(e)) from e
    except Exception as e:
        raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_DOWNLOADING, info=str(e)) from e


# ------------------------------------------------------------------------------
# Config file operations
# ------------------------------------------------------------------------------

@router.put(
    "/config/upload/{resource_id}",
    operation_id="upload-lexicon-config",
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
    custom_config: bool = Query(
        True,
        alias="custom-config",
        description="Whether this upload should be marked as a custom config upload",
    ),
    auth_data: dict = Depends(AUTH_WRITE),
) -> JSONResponse:
    """Upload a lexicon configuration as file or plain text (using the `config` parameter).

    The config must be in yaml format. If a config file already exists for the given resource it will be replaced by the
    newly uploaded one.

    Please note that any yaml comments may be removed from your config upon upload.

    ### Example

    ```bash
    curl -X PUT '{{host}}/lexicon/config/upload/<resource_id>' -H 'Authorization: Bearer YOUR_JWT' \
-F 'file=@path_to_config_file'
    ```
    """
    resource_id = auth_data["resource_id"]
    info_obj = route_utils.get_info_from_auth(auth_data)
    config_path = storage.get_config_file(resource_id)

    response = await route_utils.upload_yaml_file(
        yaml_file=yaml_file,
        yaml_txt=yaml_txt,
        res_obj=info_obj.resource,
        standardize_fn=lambda contents: karp_utils.standardize_config(contents, resource_id),
        write_fn=lambda data: storage.write_file_contents(config_path, data, resource_id)
    )
    info_obj.resource.set_custom_config(custom_config)
    return response


@router.get(
    "/config/download/{resource_id}",
    operation_id="download-lexicon-config",
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
async def download_config(auth_data: dict = Depends(AUTH_LEXICON)) -> FileResponse:
    """Download the lexicon config file in YAML format.

    ### Example

    ```bash
    curl '{{host}}/lexicon/config/download/<resource_id>' -H 'Authorization: Bearer YOUR_JWT'
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
