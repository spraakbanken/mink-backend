"""Routes related to storage on Sparv server."""

from pathlib import Path
from xml.etree import ElementTree

import shortuuid
from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse

from mink.cache import cache_utils
from mink.core import exceptions, models, registry, utils
from mink.core.config import settings
from mink.core.info import Info
from mink.core.logging import logger
from mink.sb_auth import login
from mink.sparv import models as sparv_models
from mink.sparv import storage
from mink.sparv import utils as sparv_utils

router = APIRouter()


# ------------------------------------------------------------------------------
# Corpus operations
# ------------------------------------------------------------------------------


@router.post(
    "/create-corpus",
    tags=["Manage Corpora"],
    status_code=status.HTTP_201_CREATED,
    response_model=sparv_models.CreateCorpusResponse,
    responses={
        **models.common_auth_error_responses,
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": models.ErrorResponse500,
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "Failed to create corpus",
                        "return_code": "failed_creating_corpus",
                        "info": "BaseException",
                    }
                }
            },
        },
    },
)
async def create_corpus(auth_data: dict = Depends(login.AuthDependencyNoResourceId())) -> JSONResponse:
    """Create a new corpus.

    ### Example

    ```bash
    curl -X POST '{{host}}/create-corpus' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    # Create corpus ID
    resource_id = None
    prefix = settings.RESOURCE_PREFIX
    tries = 1
    max_tries = 3
    while resource_id is None:
        # Give up after max_tries tries
        if tries > max_tries:
            raise exceptions.MinkHTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                message="Failed to create corpus",
                return_code="failed_creating_corpus",
            )
        tries += 1
        resource_id = f"{prefix}{shortuuid.uuid()[:10]}".lower()
        if resource_id in cache_utils.get_all_resources():
            resource_id = None
        else:
            try:
                await login.create_resource(auth_data.get("auth_token"), resource_id, resource_type="corpora")
            except exceptions.CorpusExistsError:
                # Corpus ID is in use in authentication system, try to create another one
                resource_id = None
            except Exception as e:
                raise exceptions.MinkHTTPException(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    message="Failed to create corpus",
                    return_code="failed_creating_corpus",
                    info=str(e),
                ) from e

    info_obj = Info(resource_id, owner=auth_data.get("user"))
    info_obj.create()

    # Create corpus dir with subdirs
    try:
        corpus_dir = storage.get_corpus_dir(resource_id, mkdir=True)
        storage.get_source_dir(resource_id, mkdir=True)
        return utils.response(
            status.HTTP_201_CREATED,
            message=f"Corpus '{resource_id}' created successfully",
            return_code="created_corpus",
            resource_id=resource_id,
        )
    except Exception as e:
        try:
            # Try to remove partially uploaded corpus data
            storage.remove_dir(corpus_dir, resource_id)
        except Exception:
            logger.exception("Failed to remove partially uploaded corpus data for '%s'.", resource_id)
        try:
            await login.remove_resource(auth_data.get("auth_token"), resource_id)
        except Exception:
            logger.exception("Failed to remove corpus '%s' from auth system.", resource_id)
        try:
            info_obj.remove()
        except Exception:
            logger.exception("Failed to remove job '%s'.", resource_id)
        raise exceptions.MinkHTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to create corpus dir",
            return_code="failed_creating_corpus_dir",
            info=str(e),
        ) from e


@router.get(
    "/list-corpora",
    tags=["Manage Corpora"],
    response_model=sparv_models.ListCorporaResponse,
    responses=models.common_auth_error_responses,
)
async def list_corpora(auth_data: dict = Depends(login.AuthDependencyNoResourceId())) -> JSONResponse:
    """List the IDs of all available corpora.

    ### Example

    ```bash
    curl '{{host}}/list-corpora' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    return utils.response(
        message="Listing available corpora", return_code="listing_corpora", corpora=auth_data.get("resources")
    )


@router.get(
    "/list-korp-corpora",
    tags=["Manage Corpora"],
    response_model=sparv_models.ListCorporaResponse,
    responses={
        status.HTTP_200_OK: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "Listing corpora installed in Korp",
                        "return_code": "listing_korp_corpora",
                        "corpora": ["mink-dxh6e6wtff", "mink-j86tfreaf9"],
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
                        "message": "Failed to list corpora installed in Korp",
                        "return_code": "failed_listing_korp_corpora",
                        "info": "Internal server error",
                    }
                }
            },
        },
    },
)
async def list_korp_corpora(
    auth_data: dict = Depends(login.AuthDependencyNoResourceId(include_read=True)),
) -> JSONResponse:
    """List the IDs of the user's Mink corpora that are installed in Korp.

    ### Example

    ```bash
    curl '{{host}}/list-korp-corpora' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    installed_corpora = []
    try:
        # Get resource infos beloning to corpora that the user may edit
        resources = registry.filter_resources(auth_data.get("resources"))
        installed_corpora = [res.id for res in resources if res.job.installed_korp]
    except Exception as e:
        raise exceptions.MinkHTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to list corpora installed in Korp",
            return_code="failed_listing_korp_corpora",
            info=str(e),
        ) from e
    return utils.response(
        message="Listing corpora installed in Korp", return_code="listing_korp_corpora", corpora=installed_corpora
    )


@router.delete(
    "/remove-corpus",
    tags=["Manage Corpora"],
    response_model=models.BaseResponse,
    responses={
        status.HTTP_200_OK: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "Corpus removed successfully",
                        "return_code": "removing_corpora",
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
                        "message": "Failed to remove corpus 'mink-dxh6e6wtff' from Korp",
                        "return_code": "failed_removing_korp",
                        "info": "BaseException",
                    }
                }
            },
        },
    },
)
async def remove_corpus(auth_data: dict = Depends(login.AuthDependency())) -> JSONResponse:
    """Remove a corpus from the storage server.

    Will attempt to abort any running job for this corpus and also remove it from the Sparv server.

    ### Example

    ```bash
    curl -X DELETE '{{host}}/remove-corpus?resource_id=some_resource_id' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    resource_id = auth_data.get("resource_id")
    # Get job
    info_obj = registry.get(resource_id)

    if info_obj.job.installed_korp:
        try:
            # Uninstall corpus from Korp using Sparv
            info_obj.job.uninstall_korp()
        except Exception as e:
            raise exceptions.MinkHTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                message=f"Failed to remove corpus '{resource_id}' from Korp",
                return_code="failed_removing_korp",
                info=str(e),
            ) from e
    if info_obj.job.installed_strix:
        try:
            # Uninstall corpus from Strix using Sparv
            info_obj.job.uninstall_strix()
        except Exception as e:
            raise exceptions.MinkHTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                message=f"Failed to remove corpus '{resource_id}' from Strix",
                return_code="failed_removing_strix",
                info=str(e),
            ) from e

    try:
        # Remove from storage
        storage.remove_dir(storage.get_corpus_dir(resource_id), resource_id)
    except Exception as e:
        raise exceptions.MinkHTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to remove corpus '{resource_id}' from storage",
            return_code="failed_removing_storage",
            info=str(e),
        ) from e

    try:
        # Remove from auth system
        await login.remove_resource(auth_data.get("auth_token"), resource_id)
    except Exception as e:
        raise exceptions.MinkHTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to remove corpus '{resource_id}' from authentication system",
            return_code="failed_removing_auth",
            info=str(e),
        ) from e

    # Remove from Mink registry
    try:
        info_obj.remove(abort_job=True)
    except Exception:
        logger.exception("Failed to remove job '%s'.", resource_id)
    return utils.response(message=f"Corpus '{resource_id}' successfully removed", return_code="removed_corpus")


# ------------------------------------------------------------------------------
# Source file operations
# ------------------------------------------------------------------------------


@router.put(
    "/upload-sources",
    tags=["Manage Sources"],
    response_model=models.BaseResponseWithWarnings,
    responses={
        status.HTTP_200_OK: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "Source files successfully added to 'mink-dxh6e6wtff'",
                        "return_code": "uploaded_sources",
                        "warnings": ["File 'example.txt' already existed and was replaced during upload."],
                    }
                }
            }
        },
        **models.common_auth_error_responses,
        status.HTTP_400_BAD_REQUEST: {
            "model": models.BaseResponseWithInfo,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": "No corpus files provided for upload",
                        "return_code": "missing_sources_upload",
                    }
                }
            },
        },
        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: {
            "model": models.ErrorResponse413,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": "Failed to upload some source files to 'mink-dxh6e6wtff'. Max file size (10 MB) "
                        "exceeded",
                        "return_code": "failed_uploading_sources_file_size",
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
                        "message": "Failed to upload some source files to 'mink-dxh6e6wtff'",
                        "return_code": "failed_uploading_sources",
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
    auth_data: dict = Depends(login.AuthDependency()),
) -> JSONResponse:
    """Upload the attached files as corpus source files.

    Attached files will be added to the corpus or replace existing ones. Files identical in name, size and md5 checksum
    will not be uploaded again.

    ### Example

    ```bash
    curl -X PUT '{{host}}/upload-sources?resource_id=some_resource_id' -H 'Authorization: Bearer YOUR_JWT' \
-F 'files=@path_to_file1' -F 'files=@path_to_file2'
    ```
    """
    resource_id = auth_data.get("resource_id")
    # Check if corpus files were provided
    if not files:
        raise exceptions.MinkHTTPException(
            status.HTTP_400_BAD_REQUEST,
            message="No corpus files provided for upload",
            return_code="missing_sources_upload",
        )

    # Check request size constraint
    try:
        content_length = int(request.headers.get("content-length", "0"))
        source_dir = storage.get_source_dir(resource_id)
    except Exception as e:
        raise exceptions.MinkHTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to upload source files to '{resource_id}'",
            return_code="failed_uploading_sources",
            info=str(e),
        ) from e
    if not utils.size_ok(source_dir, content_length):
        max_size_mb = int(settings.MAX_CORPUS_LENGTH / (1024 * 1024))
        raise exceptions.MinkHTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            message=f"Failed to upload source files to '{resource_id}'. Max corpus size ({max_size_mb} MB) exceeded",
            return_code="failed_uploading_sources_corpus_size",
            info="max corpus size exceeded",
            max_size_mb=max_size_mb,
        )

    existing_files = storage.list_contents(source_dir)
    max_file_size_mb = int(settings.MAX_FILE_LENGTH / (1024 * 1024))
    warnings = []
    # Upload data
    for f in files:
        name = sparv_utils.secure_filename(f.filename)
        original_name = name

        # Make sure the file suffix is lower case (issue warning later if name was changed)
        if name.suffix.lower() != name.suffix:
            name = Path(name.stem + name.suffix.lower())

        # Check if file can be processed by Sparv
        if not utils.file_ext_valid(name, settings.SPARV_IMPORTER_MODULES.keys()):
            raise exceptions.MinkHTTPException(
                status.HTTP_400_BAD_REQUEST,
                message=f"Failed to upload some source files to '{resource_id}' due to invalid file extension",
                return_code="failed_uploading_sources_invalid_file_extension",
                file=f.filename,
                info="invalid file extension",
            )

        # Check if file extension is compatible with existing files
        compatible, current_ext, existing_ext = utils.file_ext_compatible(name, source_dir)
        if not compatible:
            raise exceptions.MinkHTTPException(
                status.HTTP_400_BAD_REQUEST,
                message=(f"Failed to upload some source files to '{resource_id}' due to incompatible file extensions"),
                return_code="failed_uploading_sources_incompatible_file_extension",
                file=f.filename,
                info="incompatible file extensions",
                current_file_extension=current_ext,
                existing_file_extension=existing_ext,
            )

        # Check file size constraint
        file_contents = await f.read()
        if len(file_contents) > settings.MAX_FILE_LENGTH:
            raise exceptions.MinkHTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                message=(
                    f"Failed to upload some source files to '{resource_id}'. "
                    f"Max file size ({max_file_size_mb} MB) exceeded"
                ),
                return_code="failed_uploading_sources_file_size",
                file=f.filename,
                info="max file size exceeded",
                max_size_mb=max_file_size_mb,
            )

        # Skip uploading existing files (identical in name, size and md5 checksum)
        if str(name) in [i.get("name") for i in existing_files]:
            if utils.identical_file_exists(file_contents, source_dir / name):
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
                    status.HTTP_400_BAD_REQUEST,
                    message=f"Failed to upload some source files to '{resource_id}' due to invalid XML",
                    return_code="failed_uploading_sources_invalid_xml",
                    file=f.filename,
                    info=f"invalid XML: {e}",
                ) from e
        storage.write_file_contents(source_dir / name, file_contents, resource_id)

    res = registry.get(resource_id).resource
    res.set_source_files()

    # Check if file extensions were changed during the upload process and produce a warning
    if warnings:
        logger.warning("Warnings occurred during upload:\n%s", "\n".join(warnings))
    return utils.response(
        message=f"Source files successfully added to '{resource_id}'",
        return_code="uploaded_sources",
        warnings=warnings,
    )


@router.get(
    "/list-sources",
    tags=["Manage Sources"],
    response_model=models.BaseResponseWithContents,
    responses={
        status.HTTP_200_OK: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "Current source files for 'mink-dxh6e6wtff'",
                        "return_code": "listing_sources",
                        "contents": models.FileModel.model_config["json_schema_extra"]["examples"],
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
                        "message": "Failed to list source files in 'mink-dxh6e6wtff'",
                        "return_code": "failed_listing_sources",
                        "info": "BaseException",
                    }
                }
            },
        },
    },
)
async def list_sources(auth_data: dict = Depends(login.AuthDependency())) -> JSONResponse:
    """List the available corpus source files.

    ### Example

    ```bash
    curl '{{host}}/list-sources?resource_id=some_resource_id' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    resource_id = auth_data.get("resource_id")
    try:
        objlist = storage.list_contents(storage.get_source_dir(resource_id))
        return utils.response(
            message=f"Listing current source files for '{resource_id}'", contents=objlist, return_code="listing_sources"
        )
    except Exception as e:
        raise exceptions.MinkHTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to list source files in '{resource_id}'",
            return_code="failed_listing_sources",
            info=str(e),
        ) from e


@router.delete(
    "/remove-sources",
    tags=["Manage Sources"],
    response_model=models.BaseResponse,
    responses={
        status.HTTP_200_OK: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "Source files for 'mink-dxh6e6wtff' successfully removed",
                        "return_code": "removed_sources",
                    }
                }
            }
        },
        **models.common_auth_error_responses,
        status.HTTP_400_BAD_REQUEST: {
            "model": models.BaseErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": "No files provided for removal",
                        "return_code": "missing_sources_remove",
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
                        "message": "Failed to remove some source files from 'mink-dxh6e6wtff'",
                        "return_code": "failed_removing_some_sources",
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
    auth_data: dict = Depends(login.AuthDependency()),
) -> JSONResponse:
    """Remove the source files given in the `remove` parameter from the corpus.

    Files are provided as a comma-separated list of paths relative to the source directory. If any files could not be
    removed they will be listed in the error response.

    ### Example

    ```bash
    curl -X DELETE '{{host}}/remove-sources?resource_id=some_resource_id&remove=file1,file2' \
-H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    if not remove:
        raise exceptions.MinkHTTPException(
            status.HTTP_400_BAD_REQUEST,
            message="No files provided for removal",
            return_code="missing_sources_remove",
        )

    # Remove files
    resource_id = auth_data.get("resource_id")
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
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to remove some source files from '{resource_id}'",
            return_code="failed_removing_some_sources",
            failed=fails,
            succeeded=successes,
        )
    if fails:
        raise exceptions.MinkHTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to remove source files from '{resource_id}'",
            return_code="failed_removing_sources",
        )

    res = registry.get(resource_id).resource
    res.set_source_files(deleted_sources=True)

    return utils.response(
        message=f"Source files for '{resource_id}' successfully removed", return_code="removed_sources"
    )


@router.get(
    "/download-sources",
    tags=["Manage Sources"],
    response_model=models.FileResponse,
    response_class=FileResponse,
    responses={
        status.HTTP_200_OK: {"content": {"application/octet-stream": {}}, "description": "A file download response"},
        **models.common_auth_error_responses,
        status.HTTP_400_BAD_REQUEST: {
            "model": models.BaseErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": "The source file you are trying to download does not exist",
                        "return_code": "source_not_found",
                    }
                }
            },
        },
        status.HTTP_404_NOT_FOUND: {
            "model": models.BaseErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": "You have not uploaded any source files for corpus 'mink-dxh6e6wtff'",
                        "return_code": "missing_sources_download",
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
                        "message": "Failed to download source files for corpus 'mink-dxh6e6wtff'",
                        "return_code": "failed_downloading_sources",
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
    auth_data: dict = Depends(login.AuthDependency()),
) -> FileResponse:
    """Download the corpus source files as a zip file.

    The parameter `file` may be used to download a specific source file. This parameter must either be a file name or an
    absolute path on the Storage server. The `zip` parameter may be set to `false` in combination with the file param to
    avoid zipping the file to be downloaded.

    ### Example

    ```bash
    curl '{{host}}/download-sources?resource_id=some_resource_id&file=some_file_name&zip=true' \
-H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    resource_id = auth_data.get("resource_id")
    try:
        # Check if there are any source files
        storage_source_dir = storage.get_source_dir(resource_id)
        source_contents = storage.list_contents(storage_source_dir, exclude_dirs=False)
    except Exception as e:
        raise exceptions.MinkHTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to list source files in '{resource_id}'",
            return_code="failed_listing_sources",
            info=str(e),
        ) from e
    if source_contents == []:
        raise exceptions.MinkHTTPException(
            status.HTTP_404_NOT_FOUND,
            message=f"You have not uploaded any source files for corpus '{resource_id}'",
            return_code="missing_sources_download",
        )

    local_source_dir = utils.get_source_dir(resource_id, mkdir=True)
    local_corpus_dir = utils.get_resource_dir(resource_id, mkdir=True)

    # Download and zip file specified in args
    if download_file:
        download_file_name = Path(download_file).name
        download_file_path = storage_source_dir / download_file
        if download_file not in [i.get("path") for i in source_contents]:
            raise exceptions.MinkHTTPException(
                status.HTTP_404_NOT_FOUND,
                message="The source file you are trying to download does not exist",
                return_code="source_not_found",
            )
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
        except Exception as e:
            raise exceptions.MinkHTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                message="Failed to download file",
                return_code="failed_downloading_file",
                info=str(e),
            ) from e

    # Download all files as zip archive
    try:
        zip_out = local_corpus_dir / f"{resource_id}_source.zip"
        # Get files from storage server
        storage.download_dir(storage_source_dir, local_source_dir, resource_id, zipped=True, zippath=zip_out)
        return FileResponse(zip_out, media_type="application/zip", filename=zip_out.name)
    except Exception as e:
        raise exceptions.MinkHTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to download source files for corpus '{resource_id}'",
            return_code="failed_downloading_sources",
            info=str(e),
        ) from e


# ------------------------------------------------------------------------------
# Config file operations
# ------------------------------------------------------------------------------


@router.put(
    "/upload-config",
    tags=["Manage Config"],
    status_code=status.HTTP_201_CREATED,
    response_model=models.BaseResponse,
    responses={
        status.HTTP_201_CREATED: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "Config file successfully uploaded for 'mink-dxh6e6wtff'",
                        "return_code": "uploaded_config",
                    }
                }
            }
        },
        **models.common_auth_error_responses,
        status.HTTP_400_BAD_REQUEST: {
            "model": models.BaseErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": "Found both a config file and a plain text config but can only process one of these",
                        "return_code": "too_many_params_upload_config",
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
                        "message": "Failed to upload config file for 'mink-dxh6e6wtff'",
                        "return_code": "failed_uploading_config",
                        "info": "BaseException",
                    }
                }
            },
        },
    },
)
async def upload_config(
    upload_file: UploadFile | None = models.upload_file_opt_param,
    config_txt: str | None = Query(None, alias="config", description="The config file as plain text"),
    auth_data: dict = Depends(login.AuthDependency()),
) -> JSONResponse:
    """Upload a corpus configuration as file or plain text (using the `config` parameter).

    The config must be in yaml format. Read more about corpus config files in the [Sparv Pipeline
    documentation](https://spraakbanken.gu.se/sparv/#/user-manual/corpus-configuration).

    If a config file already exists for the given corpus it will be replaced by the newly uploaded one.

    Please note that any yaml comments may be removed from your config upon upload.

    ### Example

    ```bash
    curl -X PUT '{{host}}/upload-config?resource_id=some_resource_id' -H 'Authorization: Bearer YOUR_JWT' \
-F 'file=@path_to_config_file'
    ```
    """
    resource_id = auth_data.get("resource_id")

    def set_corpus_name(corpus_name: str) -> None:
        res = registry.get(resource_id).resource
        res.set_resource_name(corpus_name)

    if upload_file and config_txt:
        raise exceptions.MinkHTTPException(
            status.HTTP_400_BAD_REQUEST,
            message="Found both a config file and a plain text config but can only process one of these",
            return_code="too_many_params_upload_config",
        )

    source_files = storage.list_contents(storage.get_source_dir(resource_id))

    # Process uploaded config file
    if upload_file:
        # Check if config file is YAML
        if upload_file.content_type not in {"application/yaml", "application/x-yaml", "text/yaml"}:
            raise exceptions.MinkHTTPException(
                status.HTTP_400_BAD_REQUEST,
                message="Config file needs to be YAML",
                return_code="wrong_config_format",
            )

        config_contents = await upload_file.read()

        # Check if config file is compatible with the uploaded source files
        if source_files:
            compatible, current_importer, expected_importer = utils.config_compatible(config_contents, source_files[0])
            if not compatible:
                raise exceptions.MinkHTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    message="The importer in your config file is incompatible with your source files",
                    return_code="incompatible_config_importer",
                    current_importer=current_importer,
                    expected_importer=expected_importer,
                )

        try:
            new_config, corpus_name = utils.standardize_config(config_contents, resource_id)
            set_corpus_name(corpus_name)
            storage.write_file_contents(storage.get_config_file(resource_id), new_config.encode("UTF-8"), resource_id)
            return utils.response(
                status.HTTP_201_CREATED,
                message=f"Config file successfully uploaded for '{resource_id}'",
                return_code="uploaded_config",
            )
        except Exception as e:
            raise exceptions.MinkHTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                message=f"Failed to upload config file for '{resource_id}'",
                return_code="failed_uploading_config",
                info=str(e),
            ) from e

    elif config_txt:
        if source_files:
            try:
                # Check if config file is compatible with the uploaded source files
                compatible, current_importer, expected_importer = utils.config_compatible(config_txt, source_files[0])
            except Exception as e:
                raise exceptions.MinkHTTPException(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    message=f"Failed to upload config file for '{resource_id}'",
                    return_code="failed_uploading_config",
                    info=str(e),
                ) from e
            if not compatible:
                raise exceptions.MinkHTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    message="The importer in your config file is incompatible with your source files",
                    return_code="incompatible_config_importer",
                    current_importer=current_importer,
                    expected_importer=expected_importer,
                )
        try:
            # Standardize config (e.g. ensure that the resource_id is correct)
            new_config, corpus_name = utils.standardize_config(config_txt, resource_id)
            set_corpus_name(corpus_name)
            storage.write_file_contents(storage.get_config_file(resource_id), new_config.encode("UTF-8"), resource_id)
        except Exception as e:
            raise exceptions.MinkHTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                message=f"Failed to upload config file for '{resource_id}'",
                return_code="failed_uploading_config",
                info=str(e),
            ) from e
        return utils.response(
            status.HTTP_201_CREATED,
            message=f"Config file successfully uploaded for '{resource_id}'",
            return_code="uploaded_config",
        )

    else:
        raise exceptions.MinkHTTPException(
            status.HTTP_400_BAD_REQUEST,
            message="No config file provided for upload",
            return_code="missing_config_upload",
        )


@router.get(
    "/download-config",
    tags=["Manage Config"],
    response_model=models.FileResponse,
    response_class=FileResponse,
    responses={
        status.HTTP_200_OK: {"content": {"application/octet-stream": {}}, "description": "A file download response"},
        **models.common_auth_error_responses,
        status.HTTP_404_NOT_FOUND: {
            "model": models.ErrorResponse404,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": "No config file found for corpus 'mink-dxh6e6wtff'",
                        "return_code": "config_not_found",
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
                        "message": "Failed to download config file for 'mink-dxh6e6wtff'",
                        "return_code": "failed_downloading_config",
                        "info": "BaseException",
                    }
                }
            },
        },
    },
)
async def download_config(auth_data: dict = Depends(login.AuthDependency())) -> FileResponse:
    """Download the corpus config file in YAML format.

    ### Example

    ```bash
    curl '{{host}}/download-config?resource_id=some_resource_id' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    resource_id = auth_data.get("resource_id")
    # Create directory for the current resource locally (on Mink backend server)
    utils.get_source_dir(resource_id, mkdir=True)
    local_config_file = utils.get_config_file(resource_id)

    try:
        # Get file from storage
        download_ok = storage.download_file(
            storage.get_config_file(resource_id), local_config_file, resource_id, ignore_missing=True
        )
    except Exception as e:
        raise exceptions.MinkHTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to download config file for '{resource_id}'",
            return_code="failed_downloading_config",
            info=str(e),
        ) from e
    if not download_ok:
        raise exceptions.MinkHTTPException(
            status.HTTP_404_NOT_FOUND,
            message=f"No config file found for corpus '{resource_id}'",
            return_code="config_not_found",
        )
    return FileResponse(local_config_file, media_type="text/yaml", filename=local_config_file.name)


# ------------------------------------------------------------------------------
# Export file operations
# ------------------------------------------------------------------------------


@router.get(
    "/list-exports",
    tags=["Manage Exports"],
    response_model=models.BaseResponseWithContents,
    responses={
        status.HTTP_200_OK: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "Current export files for 'mink-dxh6e6wtff'",
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
                        "return_code": "listing_exports",
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
                        "message": "Failed to list export files in 'mink-dxh6e6wtff'",
                        "return_code": "failed_listing_exports",
                        "info": "BaseException",
                    }
                }
            },
        },
    },
)
async def list_exports(auth_data: dict = Depends(login.AuthDependency())) -> JSONResponse:
    """List the available export files created by Sparv.

    ### Example

    ```bash
    curl '{{host}}/list-exports?resource_id=some_resource_id' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    resource_id = auth_data.get("resource_id")
    try:
        objlist = storage.list_contents(storage.get_export_dir(resource_id), blacklist=settings.SPARV_EXPORT_BLACKLIST)
        return utils.response(
            message=f"Listing current export files for '{resource_id}'", contents=objlist, return_code="listing_exports"
        )
    except Exception as e:
        raise exceptions.MinkHTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to list export files in '{resource_id}'",
            return_code="failed_listing_exports",
            info=str(e),
        ) from e


@router.get(
    "/download-exports",
    tags=["Manage Exports"],
    response_model=models.FileResponse,
    response_class=FileResponse,
    responses={
        status.HTTP_200_OK: {"content": {"application/octet-stream": {}}, "description": "A file download response"},
        **models.common_auth_error_responses,
        status.HTTP_400_BAD_REQUEST: {
            "model": models.BaseErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": "The parameters 'dir' and 'file' must not be supplied simultaneously",
                        "return_code": "too_many_params_download_exports",
                    }
                }
            },
        },
        status.HTTP_404_NOT_FOUND: {
            "model": models.ErrorResponse404,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": "The export folder you are trying to download does not exist",
                        "return_code": "export_folder_not_found",
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
                        "message": "Failed to download exports for corpus 'mink-dxh6e6wtff'",
                        "return_code": "failed_downloading_exports",
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
    auth_data: dict = Depends(login.AuthDependency()),
) -> FileResponse:
    """Download all available export files created by Sparv.

    The parameters `file` and `dir` may be used to download a specific export file or a directory of export files. These
    parameters must be supplied as  paths relative to the export directory. Only one of these parameters may be applied
    at a time.

    The `zip` parameter may be set to `false` in combination with the `file` param to avoid zipping the file to be
    downloaded. If `zip` is used without the file parameter it will have no effect.

    ### Example

    ```bash
    curl '{{host}}/download-exports?resource_id=some_resource_id&file=some_file_name&zip=true' \
-H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    if download_file and download_folder:
        raise exceptions.MinkHTTPException(
            status.HTTP_400_BAD_REQUEST,
            message="The parameters 'dir' and 'file' must not be supplied simultaneously",
            return_code="too_many_params_download_exports",
        )

    resource_id = auth_data.get("resource_id")
    storage_export_dir = storage.get_export_dir(resource_id)
    local_corpus_dir = utils.get_resource_dir(resource_id, mkdir=True)
    local_export_dir = utils.get_export_dir(resource_id, mkdir=True)
    blacklist = settings.SPARV_EXPORT_BLACKLIST

    try:
        export_contents = storage.list_contents(storage_export_dir, exclude_dirs=False, blacklist=blacklist)
    except Exception as e:
        raise exceptions.MinkHTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to download exports for corpus '{resource_id}'",
            return_code="failed_downloading_exports",
            info=str(e),
        ) from e
    if export_contents == []:
        raise exceptions.MinkHTTPException(
            status.HTTP_404_NOT_FOUND,
            message=f"There are currently no exports available for corpus '{resource_id}'",
            return_code="no_exports_available",
        )

    # Download and zip folder specified in args
    if download_folder:
        download_folder_name = "_".join(Path(download_folder).parts)
        full_download_folder = storage_export_dir / download_folder
        if download_folder not in [i.get("path") for i in export_contents]:
            raise exceptions.MinkHTTPException(
                status.HTTP_404_NOT_FOUND,
                message="The export folder you are trying to download does not exist",
                return_code="export_folder_not_found",
            )
        try:
            zip_out = local_corpus_dir / f"{resource_id}_{download_folder_name}.zip"
            (local_export_dir / download_folder).mkdir(exist_ok=True)
            storage.download_dir(
                full_download_folder, local_export_dir / download_folder, resource_id, zipped=True, zippath=zip_out
            )
            return FileResponse(zip_out, media_type="application/zip", filename=zip_out.name)
        except Exception as e:
            raise exceptions.MinkHTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                message="Failed to download export folder",
                return_code="failed_downloading_export_folder",
                info=str(e),
            ) from e

    # Download and zip file specified in args
    if download_file:
        download_file_name = Path(download_file).name
        download_file_path = storage_export_dir / download_file
        if download_file not in [i.get("path") for i in export_contents]:
            raise exceptions.MinkHTTPException(
                status.HTTP_404_NOT_FOUND,
                message=f"The file '{download_file}' you are trying to download does not exist",
                return_code="export_not_found",
                file=download_file,
            )
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
        except Exception as e:
            raise exceptions.MinkHTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                message="Failed to download file",
                return_code="failed_downloading_file",
                info=str(e),
            ) from e

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
            raise exceptions.MinkHTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                message=f"Failed to download exports for corpus '{resource_id}'",
                return_code="failed_downloading_exports",
                info=str(e),
            ) from e


@router.delete(
    "/remove-exports",
    tags=["Manage Exports"],
    response_model=models.BaseResponse,
    responses={
        status.HTTP_200_OK: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "Export files for corpus 'mink-dxh6e6wtff' successfully removed",
                        "return_code": "removed_exports",
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
                        "message": "Failed to remove export files from Sparv server for corpus 'mink-dxh6e6wtff'",
                        "return_code": "failed_removing_exports_sparv",
                        "info": "BaseException",
                    }
                }
            },
        },
    },
)
async def remove_exports(auth_data: dict = Depends(login.AuthDependency())) -> JSONResponse:
    """Remove all export files for the corpus from the storage server.

    Will attempt to remove exports from the Sparv server, too, but won't crash if this fails.

    ### Example

    ```bash
    curl -X DELETE '{{host}}/remove-exports?resource_id=some_resource_id' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    resource_id = auth_data.get("resource_id")
    if not storage.local:
        try:
            # Remove export dir from storage server and create a new empty one
            storage.remove_dir(storage.get_export_dir(resource_id), resource_id)
            storage.get_export_dir(resource_id, mkdir=True)
        except Exception as e:
            raise exceptions.MinkHTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                message=f"Failed to remove export files from storage server for corpus '{resource_id}'",
                return_code="failed_removing_exports_storage",
                info=str(e),
            ) from e

    try:
        # Remove from Sparv server
        job = registry.get(resource_id).job
        success, sparv_output = job.clean_export()
    except Exception as e:
        raise exceptions.MinkHTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to remove export files from Sparv server for corpus '{resource_id}'",
            return_code="failed_removing_exports_sparv",
            info=str(e),
        ) from e
    if not success:
        raise exceptions.MinkHTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to remove export files from Sparv server for corpus '{resource_id}'",
            return_code="failed_removing_exports_sparv",
            info=str(sparv_output),
        )

    return utils.response(
        message=f"Export files for corpus '{resource_id}' successfully removed", return_code="removed_exports"
    )


@router.get(
    "/download-source-text",
    tags=["Manage Exports"],
    response_model=models.FileResponse,
    response_class=FileResponse,
    responses={
        status.HTTP_200_OK: {"content": {"text/plain": {}}, "description": "A file download response"},
        **models.common_auth_error_responses,
        status.HTTP_400_BAD_REQUEST: {
            "model": models.BaseErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": "No source file specified for download",
                        "return_code": "missing_sources_download_text",
                    }
                }
            },
        },
        status.HTTP_404_NOT_FOUND: {
            "model": models.BaseErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": "The source text for this file does not exist",
                        "return_code": "source_text_not_found",
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
                        "message": "Failed to download source text",
                        "return_code": "failed_downloading_source_text",
                        "info": "BaseException",
                    }
                }
            },
        },
    },
)
async def download_source_text(
    download_file: str = Query(..., alias="file", description="The file name to download"),
    auth_data: dict = Depends(login.AuthDependency()),
) -> FileResponse:
    """Download one of the source files in plain text.

    The plain text is extracted by Sparv and therefore it can only be requested after a completed Sparv job.
    The source file name (including its file extension) must be specified in the `file` parameter.

    ### Example

    ```bash
    curl '{{host}}/download-source-text?resource_id=some_resource_id&file=some_file_name' \
-H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    resource_id = auth_data.get("resource_id")
    storage_work_dir = storage.get_work_dir(resource_id)
    local_corpus_dir = utils.get_resource_dir(resource_id, mkdir=True)

    if not download_file:
        raise exceptions.MinkHTTPException(
            status.HTTP_400_BAD_REQUEST,
            message="No source file specified for download",
            return_code="missing_sources_download_text",
        )

    try:
        source_texts = storage.list_contents(storage_work_dir, exclude_dirs=False)
    except Exception as e:
        raise exceptions.MinkHTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to download source text",
            return_code="failed_downloading_source_text",
            info=str(e),
        ) from e
    if source_texts == []:
        raise exceptions.MinkHTTPException(
            status.HTTP_404_NOT_FOUND,
            message=f"There are currently no source texts for corpus '{resource_id}'. "
            "You must run Sparv before you can view source texts.",
            return_code="no_source_texts_run_sparv",
        )

    # Download file specified in args
    download_file = Path(download_file)
    download_file_stem = Path(download_file.stem)
    short_path = str(download_file_stem / settings.SPARV_PLAIN_TEXT_FILE)
    if short_path not in [i.get("path") for i in source_texts]:
        raise exceptions.MinkHTTPException(
            status.HTTP_404_NOT_FOUND,
            message="The source text for this file does not exist",
            return_code="source_text_not_found",
        )
    try:
        download_file_path = (
            storage_work_dir / download_file.parent / download_file_stem / settings.SPARV_PLAIN_TEXT_FILE
        )
        out_file_name = str(download_file_stem) + "_plain.txt"
        local_path = local_corpus_dir / out_file_name
        storage.download_file(download_file_path, local_path, resource_id)
        utils.uncompress_gzip(local_path)
        utils.unpickle_file(local_path)
        return FileResponse(local_path, media_type="text/plain", filename=local_path.name)
    except Exception as e:
        raise exceptions.MinkHTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to download source text",
            return_code="failed_downloading_source_text",
            info=str(e),
        ) from e


@router.get(
    "/check-changes",
    tags=["Process Corpus"],
    response_model=sparv_models.CheckChangesResponse,
    responses={
        **models.common_auth_error_responses,
        status.HTTP_404_NOT_FOUND: {
            "model": models.ErrorResponse404,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": "Corpus 'mink-dxh6e6wtff' has not been run",
                        "return_code": "corpus_not_run",
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
                        "message": "Failed to check changes for corpus 'mink-dxh6e6wtff'",
                        "return_code": "failed_checking_changes",
                        "info": "BaseException",
                    }
                }
            },
        },
    },
)
async def check_changes(auth_data: dict = Depends(login.AuthDependency())) -> JSONResponse:
    """Check for any changes in the config and source files since the last Sparv job was started.

    Those changes include added and deleted source files.

    ### Example

    ```bash
    curl -X GET '{{host}}/check-changes?resource_id=some_resource_id' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    resource_id = auth_data.get("resource_id")
    try:
        info_item = registry.get(resource_id)
    except Exception as e:
        raise exceptions.MinkHTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to get job for corpus '{resource_id}'",
            return_code="failed_getting_job",
            info=str(e),
        ) from e
    try:
        sources_changed, sources_deleted, config_changed = storage.get_file_changes(resource_id, info_item)
        input_changed = sources_changed or sources_deleted or config_changed
        return utils.response(
            message=f"Your input for the corpus '{resource_id}' has {'not ' if not input_changed else ''}changed since"
            " the last run",
            return_code="input_changed" if input_changed else "input_not_changed",
            input_changed=input_changed,
            config_changed=config_changed,
            sources_changed=sources_changed,
            sources_deleted=sources_deleted,
            last_run_started=info_item.job.started,
        )

    except exceptions.JobNotFoundError as e:
        raise exceptions.MinkHTTPException(
            status.HTTP_404_NOT_FOUND,
            message=f"Corpus '{resource_id}' has not been run",
            return_code="corpus_not_run",
        ) from e

    except exceptions.CouldNotListSourcesError as e:
        raise exceptions.MinkHTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to list source files in '{resource_id}'",
            return_code="failed_listing_sources",
            info=str(e),
        ) from e

    except Exception as e:
        raise exceptions.MinkHTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to check changes for corpus '{resource_id}'",
            return_code="failed_checking_changes",
            info=str(e),
        ) from e
