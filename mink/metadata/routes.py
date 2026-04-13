"""Routes related to storing metadata files."""

import httpx
from fastapi import APIRouter, Depends, Query, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse

from mink.cache import jobs_cache
from mink.core import exceptions, models, registry, return_codes, route_utils, utils
from mink.core.config import settings
from mink.core.info import Info
from mink.core.resource import Resource
from mink.core.resource_specs import get_spec
from mink.metadata import utils as metadata_utils
from mink.metadata.config import metadata_settings
from mink.metadata.spec import METADATA
from mink.metadata.storage import storage
from mink.sb_auth import login

router = APIRouter(tags=["Manage Metadata"], prefix="/metadata")
SBAUTH_METADATA = get_spec(METADATA).sbauth_resource_type
AUTH_METADATA = login.AuthDependency(sbauth_resource_type=SBAUTH_METADATA)
AUTH_METADATA_WRITE = login.AuthDependency(min_level="WRITE", sbauth_resource_type=SBAUTH_METADATA)
AUTH_METADATA_ADMIN = login.AuthDependency(min_level="ADMIN", sbauth_resource_type=SBAUTH_METADATA)
AUTH_METADATA_NO_ID = login.AuthDependencyNoResourceId(sbauth_resource_type=SBAUTH_METADATA)


# ------------------------------------------------------------------------------
# Resource creation and removal
# ------------------------------------------------------------------------------

@router.post(
    "/create",
    status_code=status.HTTP_201_CREATED,
    response_model=models.CreateResourceResponse,
    responses={
        status.HTTP_201_CREATED: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": return_codes.CREATED_RESOURCE.message,
                        "return_code": return_codes.CREATED_RESOURCE.code,
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
                        "message": return_codes.FAILED_CREATING_RESOURCE.message,
                        "return_code": return_codes.FAILED_CREATING_RESOURCE.code,
                        "info": "ID not available",
                    }
                }
            },
        },
    },
)
async def create_metadata(
    public_id: str = Query(..., description="Public resource ID"),
    auth_data: dict = Depends(AUTH_METADATA_NO_ID),
) -> JSONResponse:
    """Create a new metadata resource.

    A `public_id` must be supplied, containing the correct organization prefix for the user making the request.

    ### Example

    ```bash
    curl -X POST '{{host}}/metadata/create?public_id=org-prefix-resource-id' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    # TODO: better solution for getting user's organization prefix!
    user = auth_data["user"]
    org_prefix = metadata_settings.METADATA_ORG_PREFIXES.get(user.id)
    if org_prefix is None:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.FAILED_CREATING_RESOURCE,
            info=f"No organization prefix found for user with ID '{user.id}'",
        )
    org_prefix = org_prefix.lower()
    if not public_id.startswith(f"{org_prefix}-"):
        raise exceptions.MinkHTTPException(
            return_code=return_codes.FAILED_CREATING_RESOURCE,
            info=f"Public ID '{public_id}' does not start with organization prefix '{org_prefix}'",
        )

    # Check availability of ID in SBX metadata and the Mink backend resource registry
    check_id_url = metadata_settings.METADATA_ID_AVAILABLE_URL + public_id
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(check_id_url)
            id_available = response.json().get("available", False)
    except Exception as e:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.FAILED_CREATING_RESOURCE, info=f"Error when checking ID availability: {e}"
        ) from e
    if not id_available or public_id in jobs_cache.get_all_resources():
        raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_CREATING_RESOURCE, info="ID not available")

    resource_id = await route_utils.create_resource_id(
        auth_token=auth_data["auth_token"],
        resource_type=get_spec(METADATA).sbauth_resource_type,
        existing_ids_fn=jobs_cache.get_all_resources,
        resource_prefix=settings.RESOURCE_PREFIX,
    )

    try:
        # Create info object in registry
        res = Resource(resource_id, type=METADATA, public_id=public_id)
        info_obj = Info(resource_id, resource=res, owner=user)
        info_obj.create()

        # Create metadata resource dir with sources subdir
        resource_dir = storage.get_resource_dir(resource_id, mkdir=True)
        storage.get_source_dir(resource_id, mkdir=True)

        return utils.response(return_code=return_codes.CREATED_RESOURCE, resource_id=resource_id)

    # If anything fails, try to remove from storage, auth system, and registry
    except Exception as e:
        await route_utils.cleanup_partial_resource(
            resource_id=resource_id,
            auth_token=auth_data["auth_token"],
            info_obj=info_obj,
            remove_from_storage_fn=lambda: storage.remove_dir(resource_dir, resource_id),
        )
        raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_CREATING_RESOURCE, info=str(e)) from e


@router.delete(
    "/remove/{resource_id}",
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
        status.HTTP_400_BAD_REQUEST: {
            "model": models.BaseErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.INVALID_RESOURCE_TYPE.message,
                        "return_code": return_codes.INVALID_RESOURCE_TYPE.code,
                        "info": "Expected a metadata resource",
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
                        "info": "Failed to remove resource from storage",
                    }
                }
            },
        },
    },
)
async def remove_metadata(auth_data: dict = Depends(AUTH_METADATA_ADMIN)) -> JSONResponse:
    """Remove a metadata resource.

    ### Example

    ```bash
    curl -X DELETE '{{host}}/metadata/remove/<resource_id>' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    resource_id = auth_data["resource_id"]
    info_obj = registry.get(resource_id)
    return await route_utils.remove_resource(
        resource_id=resource_id,
        auth_token=auth_data["auth_token"],
        info_obj=info_obj,
        remove_from_storage_fn=lambda: storage.remove_dir(storage.get_resource_dir(resource_id), resource_id),
    )


@router.get(
    "/list",
    response_model=models.ListResourcesResponse,
    responses={**models.common_auth_error_responses},
)
async def list_metadata(auth_data: dict = Depends(AUTH_METADATA_NO_ID)) -> JSONResponse:
    """List the IDs of all available metadata resources.

    ### Example

    ```bash
    curl '{{host}}/metadata/list' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    return utils.response(
        return_code=return_codes.LISTING_CONTENT,
        info="Listing available metadata resources",
        resources=auth_data.get("resources"),
    )


# ------------------------------------------------------------------------------
# Metadata (yaml) file operations
# ------------------------------------------------------------------------------

@router.put(
    "/config/upload/{resource_id}",
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
        status.HTTP_400_BAD_REQUEST: {
            "model": models.BaseErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.INVALID_FILE.message,
                        "return_code": return_codes.INVALID_FILE.code,
                        "info": "File format needs to be YAML",
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
async def upload_metadata_yaml(
    yaml_file: UploadFile = models.upload_file_opt_param,
    yaml_txt: str | None = Query(None, alias="yaml", description="The yaml metadata in plain text"),
    auth_data: dict = Depends(AUTH_METADATA_WRITE),
) -> JSONResponse:
    """Upload a YAML metadata file or provide metadata as plain text.

    ### Example

    ```bash
    curl -X PUT '{{host}}/metadata/config/upload/<resource_id>' -H 'Authorization: Bearer YOUR_JWT' \
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
    "/config/download/{resource_id}",
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
async def download_metadata_yaml(auth_data: dict = Depends(AUTH_METADATA)) -> FileResponse:
    """Download the metadata yaml file for a specific resource.

    ### Example

    ```bash
    curl -X GET '{{host}}/metadata/config/download/<resource_id>' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    resource_id = auth_data["resource_id"]
    remote_yaml_file = storage.get_yaml_file(resource_id)
    local_yaml_file = storage.get_local_metadata_yaml_file(resource_id)
    return route_utils.download_file_response(
        local_path=local_yaml_file,
        ensure_local_dir_fn=lambda: storage.get_local_resource_dir(resource_id, mkdir=True),
        download_fn=lambda: storage.download_file(remote_yaml_file, local_yaml_file, resource_id),
        media_type="text/yaml",
    )
