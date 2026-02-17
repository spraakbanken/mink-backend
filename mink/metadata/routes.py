"""Routes related to storing metadata files."""

import httpx
from fastapi import APIRouter, Depends, Query, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse

from mink.cache import jobs_cache
from mink.core import exceptions, models, registry, route_utils, utils
from mink.core.config import settings
from mink.core.info import Info
from mink.core.resource import Resource, ResourceType
from mink.metadata import utils as metadata_utils
from mink.metadata.config import metadata_settings
from mink.metadata.storage import storage
from mink.sb_auth import login

router = APIRouter(tags=["Manage Metadata"])


# ------------------------------------------------------------------------------
# Resource creation and removal
# ------------------------------------------------------------------------------


@router.post(
    "/create-metadata",
    status_code=status.HTTP_201_CREATED,
    response_model=models.BaseResponse,
    responses={
        status.HTTP_201_CREATED: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "Resource created successfully",
                        "return_code": "created_resource",
                        "resource_id": "mink-dxh6e6wtff",
                    }
                }
            }
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": models.ErrorResponse500,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": "Failed to create resource: ID not available",
                        "return_code": "failed_creating_resource",
                        "info": "BaseException",
                    }
                }
            },
        },
    },
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
    user = auth_data["user"]
    org_prefix = metadata_settings.METADATA_ORG_PREFIXES.get(user.id)
    if org_prefix is None:
        raise exceptions.MinkHTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="No organization prefix was found for user",
            return_code="failed_getting_org_prefix",
        )
    org_prefix = org_prefix.lower()
    if not public_id.startswith(f"{org_prefix}-"):
        raise exceptions.MinkHTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to create resource: chosen public ID does not contain the correct organization prefix",
            return_code="failed_creating_resource",
        )

    # Check availability of ID in SBX metadata and the Mink backend resource registry
    check_id_url = metadata_settings.METADATA_ID_AVAILABLE_URL + public_id
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(check_id_url)
            id_available = response.json().get("available", False)
    except Exception as e:
        raise exceptions.MinkHTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to create resource: failed to check ID availability",
            return_code="failed_creating_resource",
            info=str(e),
        ) from e
    if not id_available or public_id in jobs_cache.get_all_resources():
        raise exceptions.MinkHTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to create resource: ID not available",
            return_code="failed_creating_resource",
        )

    resource_id = await route_utils.create_resource_id(
        auth_token=auth_data["auth_token"],
        resource_type="metadata",
        existing_ids_fn=jobs_cache.get_all_resources,
        resource_prefix=settings.RESOURCE_PREFIX,
    )

    try:
        # Create info object in registry
        res = Resource(resource_id, type=ResourceType.metadata, public_id=public_id)
        info_obj = Info(resource_id, resource=res, owner=user)
        info_obj.create()

        # Create metadata resource dir with sources subdir
        resource_dir = storage.get_resource_dir(resource_id, mkdir=True)
        storage.get_source_dir(resource_id, mkdir=True)

        return utils.response(
            status.HTTP_201_CREATED,
            message="Resource created successfully",
            return_code="created_resource",
            resource_id=resource_id,
        )

    # If anything fails, try to remove from storage, auth system, and registry
    except Exception as e:
        await route_utils.cleanup_partial_resource(
            resource_id=resource_id,
            auth_token=auth_data["auth_token"],
            info_obj=info_obj,
            remove_from_storage_fn=lambda: storage.remove_dir(resource_dir, resource_id),
        )
        raise exceptions.MinkHTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to create resource",
            return_code="failed_creating_resource",
            info=str(e),
        ) from e


@router.delete(
    "/remove-metadata",
    response_model=models.BaseResponse,
    responses={
        status.HTTP_200_OK: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "Resource successfully removed",
                        "return_code": "removed_resource",
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
                        "message": "Resource 'mink-dxh6e6wtff' is not a metadata resource",
                        "return_code": "wrong_resource_type",
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
                        "message": "Failed to remove resource from storage",
                        "return_code": "failed_removing_storage",
                        "info": "BaseException",
                    }
                }
            },
        },
    },
)
async def remove_metadata(auth_data: dict = Depends(login.AuthDependency(min_level="ADMIN"))) -> JSONResponse:
    """Remove a metadata resource.

    ### Example

    ```bash
    curl -X DELETE '{{host}}/remove-metadata?resource_id=resource-id' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    resource_id = auth_data["resource_id"]
    info_obj = registry.get(resource_id)

    # Check for correct resource type
    # TODO: Maybe this should be done in login.AuthDependency()?
    if info_obj.resource.type != ResourceType.metadata:
        raise exceptions.MinkHTTPException(
            status.HTTP_400_BAD_REQUEST,
            message=f"Resource '{resource_id}' is not a metadata resource",
            return_code="wrong_resource_type",
        )

    return await route_utils.remove_resource(
        resource_id=resource_id,
        auth_token=auth_data["auth_token"],
        info_obj=info_obj,
        remove_from_storage_fn=lambda: storage.remove_dir(storage.get_resource_dir(resource_id), resource_id),
    )


# ------------------------------------------------------------------------------
# Metadata (yaml) file operations
# ------------------------------------------------------------------------------


@router.put(
    "/upload-metadata-yaml",
    status_code=status.HTTP_201_CREATED,
    response_model=models.BaseResponse,
    responses={
        status.HTTP_201_CREATED: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "File successfully uploaded",
                        "return_code": "uploaded_file",
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
                        "message": "File needs to be YAML",
                        "return_code": "wrong_format",
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
                        "message": "Failed to upload file",
                        "return_code": "failed_uploading_file",
                        "info": "BaseException",
                    }
                }
            },
        },
    },
)
async def upload_metadata_yaml(
    yaml_file: UploadFile = models.upload_file_opt_param,
    yaml_txt: str | None = Query(None, alias="yaml", description="The yaml metadata in plain text"),
    auth_data: dict = Depends(login.AuthDependency(min_level="WRITE")),
) -> JSONResponse:
    """Upload a YAML metadata file or provide metadata as plain text.

    ### Example

    ```bash
    curl -X PUT '{{host}}/upload-metadata-yaml?resource_id=some_resource_id' -H 'Authorization: Bearer YOUR_JWT' \
-F 'file=@path_to_metadata.yaml'
    ```
    """
    resource_id = auth_data["resource_id"]
    yaml_path = storage.get_yaml_file(resource_id)

    return await route_utils.upload_yaml_file(
        yaml_file=yaml_file,
        yaml_txt=yaml_txt,
        res_obj=registry.get(resource_id).resource,
        standardize_fn=metadata_utils.standardize_yaml,
        write_fn=lambda data: storage.write_file_contents(yaml_path, data, resource_id),
    )


@router.get(
    "/download-metadata-yaml",
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
                        "message": "File not found",
                        "return_code": "file_not_found",
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
                        "message": "Failed to download file",
                        "return_code": "failed_downloading_file",
                        "info": "BaseException",
                    }
                }
            },
        },
    },
)
async def download_metadata_yaml(auth_data: dict = Depends(login.AuthDependency())) -> FileResponse:
    """Download the metadata yaml file for a specific resource.

    ### Example

    ```bash
    curl -X GET '{{host}}/download-metadata-yaml?resource_id=some_resource_id' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    resource_id = auth_data["resource_id"]
    remote_yaml_file = storage.get_yaml_file(resource_id)
    local_yaml_file = storage.get_local_metadata_yaml_file(resource_id)
    return route_utils.download_file_response(
        local_path=local_yaml_file,
        ensure_local_dir_fn=lambda: storage.get_local_resource_dir(resource_id, mkdir=True),
        download_fn=lambda: storage.download_file(remote_yaml_file, local_yaml_file, resource_id, ignore_missing=True),
        media_type="text/yaml",
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
