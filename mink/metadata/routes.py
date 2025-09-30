"""Routes related to storing metadata files."""

import httpx
import shortuuid
from fastapi import APIRouter, Depends, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from mink.cache import cache_utils
from mink.core import exceptions, models, registry, utils
from mink.core.config import settings
from mink.core.info import Info
from mink.core.logging import logger
from mink.core.resource import Resource, ResourceType
from mink.metadata import storage
from mink.sb_auth import login

router = APIRouter(tags=["Manage Metadata"])


# ------------------------------------------------------------------------------
# Corpus operations
# ------------------------------------------------------------------------------


@router.post(
    "/create-metadata",
    status_code=201,
    response_model=models.BaseResponse,
    responses={
        201: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "Resource 'mink-dxh6e6wtff' created successfully",
                        "return_code": "created_resource",
                        "resource_id": "mink-dxh6e6wtff",
                    }
                }
            }
        },
        500: {
            "model": models.ErrorResponse500,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": "Failed to create resource: ID not available",
                        "return_code": "failed_creating_resource",
                        "info": "BaseException"
                    }
                }
            }
        }
    }
)
async def create_metadata(
    public_id: str = Query(..., description="Public resource ID"),
    auth_data: dict = Depends(login.AuthDependencyNoResourceId()),
) -> JSONResponse:
    """Create a new metadata resource.

    A `public_id` must be supplied, containing the correct organization prefix for the user making the request.

    ### Example

    ```bash
    curl -X GET '{{host}}/create-metadata?public_id=org-prefix-resource-id' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    # TODO: better solution for getting user's organization prefix!
    user = auth_data.get("user")
    org_prefix = settings.METADATA_ORG_PREFIXES.get(user.id)
    if org_prefix is None:
        raise exceptions.MinkHTTPException(
            500, message="No organization prefix was found for user", return_code="failed_getting_org_prefix"
        )
    org_prefix = org_prefix.lower()
    if not public_id.startswith(f"{org_prefix}-"):
        raise exceptions.MinkHTTPException(
            500,
            message="Failed to create resource: chosen public ID does not contain the correct organization prefix",
            return_code="failed_creating_resource",
        )

    # Check availability of ID in SBX metadata and the Mink backend resource registry
    check_id_url = settings.METADATA_ID_AVAILABLE_URL + public_id
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(check_id_url)
            id_available = response.json().get("available", False)
    except Exception as e:
        raise exceptions.MinkHTTPException(
            500,
            message="Failed to create resource: failed to check ID availability",
            return_code="failed_creating_resource",
            info=str(e),
        ) from e
    if not id_available or public_id in cache_utils.get_all_resources():
        raise exceptions.MinkHTTPException(
            500, message="Failed to create resource: ID not available", return_code="failed_creating_resource"
        )

    # Create internal resource ID
    resource_id = None
    prefix = settings.RESOURCE_PREFIX
    tries = 1
    while resource_id is None:
        # Give up after 3 tries
        if tries > 3:
            raise exceptions.MinkHTTPException(
                500, message="Failed to create resource", return_code="failed_creating_resource"
            )
        tries += 1
        resource_id = f"{prefix}{shortuuid.uuid()[:10]}".lower()
        if resource_id in cache_utils.get_all_resources():
            resource_id = None
        else:
            try:
                await login.create_resource(auth_data.get("auth_token"), resource_id, resource_type="metadata")
            except exceptions.CorpusExistsError:
                # Resource ID is in use in authentication system, try to create another one
                resource_id = None
            except Exception as e:
                raise exceptions.MinkHTTPException(
                    500, message="Failed to create resource", return_code="failed_creating_resource", info=str(e)
                ) from e

    try:
        res = Resource(resource_id, type=ResourceType.metadata, public_id=public_id)
        info_obj = Info(resource_id, resource=res, owner=user)
        info_obj.create()
    except Exception as e:
        raise exceptions.MinkHTTPException(
            500, message="Failed to create resource", return_code="failed_creating_resource", info=str(e)
        ) from e

    # Create metadata resource dir with sources subdir
    try:
        resource_dir = storage.get_resource_dir(resource_id, mkdir=True)
        storage.get_source_dir(resource_id, mkdir=True)
        return utils.response(
            201,
            message=f"Resource '{resource_id}' created successfully",
            return_code="created_resource",
            resource_id=resource_id,
        )
    except Exception as e:
        try:
            # Try to remove partially uploaded resource data
            storage.remove_dir(resource_dir, resource_id)
        except Exception:
            logger.exception("Failed to remove partially uploaded corpus data for '%s'.", resource_id)
        try:
            await login.remove_resource(auth_data.get("auth_token"), resource_id)
        except Exception:
            logger.exception("Failed to remove corpus '%s' from auth system.", resource_id)
        try:
            info_obj.remove()
        except Exception:
            logger.exception("Failed to remove object '%s' from registry.", resource_id)
        raise exceptions.MinkHTTPException(
            500, message="Failed to create resource dir", return_code="failed_creating_resource_dir", info=str(e)
        ) from e


@router.delete(
    "/remove-metadata",
    response_model=models.BaseResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "Resource 'mink-dxh6e6wtff' successfully removed",
                        "return_code": "removed_resource",
                    }
                }
            }
        },
        **models.common_auth_error_responses,
        400: {
            "model": models.BaseErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": "Resource 'mink-dxh6e6wtff' is not a metadata resource",
                        "return_code": "wrong_resource_type",
                    }
                }
            }
        },
        500: {
            "model": models.ErrorResponse500,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": "Failed to remove resource 'mink-dxh6e6wtff' from storage",
                        "return_code": "failed_removing_storage",
                        "info": "BaseException"
                    }
                }
            },
        },
    },
)
async def remove_metadata(auth_data: dict = Depends(login.AuthDependency())) -> JSONResponse:
    """Remove a metadata resource.

    ### Example

    ```bash
    curl -X DELETE '{{host}}/remove-metadata?resource_id=resource-id' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    resource_id = auth_data.get("resource_id")
    info_obj = registry.get(resource_id)

    # Check for correct resource type
    # TODO: Maybe this should be done in login.AuthDependency()?
    if info_obj.resource.type != ResourceType.metadata:
        raise exceptions.MinkHTTPException(
            400,
            message=f"Resource '{resource_id}' is not a metadata resource",
            return_code="wrong_resource_type",
        )

    try:
        # Remove from storage
        storage.remove_dir(storage.get_resource_dir(resource_id), resource_id)
    except Exception as e:
        raise exceptions.MinkHTTPException(
            500,
            message=f"Failed to remove resource '{resource_id}' from storage",
            return_code="failed_removing_storage",
            info=str(e),
        ) from e

    try:
        # Remove from auth system
        await login.remove_resource(auth_data.get("auth_token"), resource_id)
    except Exception as e:
        raise exceptions.MinkHTTPException(
            500,
            message=f"Failed to remove resource '{resource_id}' from authentication system",
            return_code="failed_removing_auth",
            info=str(e),
        ) from e

    try:
        # Remove from Mink registry
        info_obj.remove()
    except Exception:
        logger.exception("Failed to remove job '%s'.", resource_id)
    return utils.response(message=f"Resource '{resource_id}' successfully removed", return_code="removed_resource")


# ------------------------------------------------------------------------------
# Metadata (yaml) file operations
# ------------------------------------------------------------------------------


@router.put(
    "/upload-metadata-yaml",
    status_code=201,
    response_model=models.BaseResponse,
    responses={
        201: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "Metadata file successfully uploaded for 'mink-dxh6e6wtff'",
                        "return_code": "uploaded_yaml",
                    }
                }
            }
        },
        **models.common_auth_error_responses,
        400: {
            "model": models.BaseErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": "Metadata file needs to be YAML",
                        "return_code": "wrong_metadata_format",
                    }
                }
            }
        },
        500: {
            "model": models.ErrorResponse500,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": "Failed to upload metadata file for 'mink-dxh6e6wtff",
                        "return_code": "failed_uploading_metadata",
                        "info": "BaseException",
                    }
                }
            },
        },
    },
)
async def upload_metadata_yaml(
    metadata_txt: str | None = Query(None, alias="yaml", description="The yaml metadata in plain text"),
    yaml_file: UploadFile = models.upload_file_opt_param,
    auth_data: dict = Depends(login.AuthDependency()),
) -> JSONResponse:
    """Upload a YAML metadata file or provide metadata as plain text.

    ### Example

    ```bash
    curl -X PUT '{{host}}/upload-metadata-yaml?resource_id=some_resource_id' -H 'Authorization: Bearer YOUR_JWT' \
-F 'file=@path_to_metadata.yaml'
    ```
    """
    resource_id = auth_data.get("resource_id")

    def set_resource_name(resource_name: str) -> None:
        res = registry.get(resource_id).resource
        res.set_resource_name(resource_name)

    if yaml_file and metadata_txt:
        raise exceptions.MinkHTTPException(
            400,
            message="Found both a file and metadata in plain text but can only process one of these",
            return_code="too_many_params_upload_metadata",
        )

    # Process uploaded metadata file
    if yaml_file:
        # Check if metadata file is YAML
        if yaml_file.content_type not in {"application/yaml", "application/x-yaml", "text/yaml"}:
            raise exceptions.MinkHTTPException(
                400, message="Metadata file needs to be YAML", return_code="wrong_metadata_format"
            )

        yaml_contents = await yaml_file.read()

        try:
            new_yaml, resource_name = utils.standardize_metadata_yaml(yaml_contents)
            set_resource_name(resource_name)
            storage.write_file_contents(storage.get_yaml_file(resource_id), new_yaml.encode("UTF-8"), resource_id)
            return utils.response(
                201, message=f"Metadata file successfully uploaded for '{resource_id}'", return_code="uploaded_yaml"
            )
        except Exception as e:
            raise exceptions.MinkHTTPException(
                500,
                message=f"Failed to upload metadata file for '{resource_id}'",
                return_code="failed_uploading_metadata",
                info=str(e),
            ) from e

    # Process metadata in plain text
    elif metadata_txt:
        try:
            new_yaml, resource_name = utils.standardize_metadata_yaml(metadata_txt)
            set_resource_name(resource_name)
            storage.write_file_contents(storage.get_yaml_file(resource_id), new_yaml.encode("UTF-8"), resource_id)
            return utils.response(
                201, message=f"Metadata file successfully uploaded for '{resource_id}'", return_code="uploaded_metadata"
            )
        except Exception as e:
            raise exceptions.MinkHTTPException(
                500,
                message=f"Failed to upload metadata file for '{resource_id}'",
                return_code="failed_uploading_metadata",
                info=str(e),
            ) from e

    else:
        raise exceptions.MinkHTTPException(
            400, message="No metadata file provided for upload", return_code="missing_metadata_upload"
        )


@router.get(
    "/download-metadata-yaml",
    response_model=models.FileResponse,
    response_class=FileResponse,
    responses={
        200: {"content": {"application/octet-stream": {}}, "description": "A file download response"},
        **models.common_auth_error_responses,
        404: {
            "model": models.ErrorResponse404,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": "Metadata file not found for resource 'mink-dxh6e6wtff'",
                        "return_code": "metadata_not_found",
                    }
                }
            },
        },
        500: {
            "model": models.ErrorResponse500,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": "Failed to download metadata file for resource 'mink-dxh6e6wtff'",
                        "return_code": "failed_downloading_metadata",
                        "info": "BaseException"
                    }
                }
            },
        }
    }
)
async def download_metadata_yaml(auth_data: dict = Depends(login.AuthDependency())) -> JSONResponse:
    """Download the metadata yaml file for a specific resource.

    ### Example

    ```bash
    curl -X GET '{{host}}/download-metadata-yaml?resource_id=some_resource_id' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    resource_id = auth_data.get("resource_id")
    # Create directory for the current resource locally (on Mink backend server)
    utils.get_resource_dir(resource_id, mkdir=True)
    local_yaml_file = utils.get_metadata_yaml_file(resource_id)

    try:
        # Get file from storage
        download_ok = storage.download_file(
            storage.get_yaml_file(resource_id), local_yaml_file, resource_id, ignore_missing=True
        )
    except Exception as e:
        raise exceptions.MinkHTTPException(
            500,
            message=f"Failed to download metadata file for resource '{resource_id}'",
            return_code="failed_downloading_metadata",
            info=str(e),
        ) from e
    if download_ok:
        return FileResponse(local_yaml_file, media_type="text/yaml", filename=local_yaml_file.name)
    raise exceptions.MinkHTTPException(
        404, message=f"Metadata file not found for resource '{resource_id}'", return_code="metadata_not_found"
    )


# # ------------------------------------------------------------------------------
# # Source file operations
# # ------------------------------------------------------------------------------

# @router.put("/upload-metadata-sources")
# async def upload_metadata_sources(auth_data: dict = Depends(login.AuthDependency())) -> JSONResponse:
#     pass


# @router.get("/list-metadata-sources")
# async def list_metadata_sources(auth_data: dict = Depends(login.AuthDependency())) -> JSONResponse:
#     pass


# @router.delete("/remove-metadata-sources")
# async def remove_metadata_sources(auth_data: dict = Depends(login.AuthDependency())) -> JSONResponse:
#     pass


# @router.get("/download-metadata-sources")
# async def download_metadata_sources(auth_data: dict = Depends(login.AuthDependency())) -> JSONResponse:
#     pass
