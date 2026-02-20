"""Routes related to jobs status and information."""

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse

from mink.core import exceptions, models, registry, route_utils, utils
from mink.core.resource_specs import get_spec
from mink.core.status import JobStatuses
from mink.sb_auth import login

router = APIRouter()


@router.get(
    "/resource-info",
    tags=["Process Corpus"],
    response_model=models.StatusResponse | models.StatusesResponse,
    responses={
        **models.common_auth_error_responses,
        status.HTTP_404_NOT_FOUND: {
            "model": models.ErrorResponse404,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": "Resource does not exist or you do not have access to it",
                        "return_code": "resource_not_found",
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
                        "message": "Failed to get job status for resource",
                        "return_code": "failed_getting_job_status",
                        "info": "BaseException",
                    }
                }
            },
        },
    },
)
async def resource_info(
    # Parameter is defined again here to allow for None (since it is optional in this route)
    resource_id: str | None = Query(None, description="Resource ID"),
    auth_data: dict = Depends(login.AuthDependency(require_resource_id=False)),
) -> JSONResponse:
    """Return the status of the current job for a corpus or all corpora belonging to the user.

    If the resource ID is provided, the status of the specific resource is returned. Otherwise, the statuses of all
    resources are returned.

    If admin mode is turned on, the owner information is included for each resource.

    ### Example

    ```bash
    curl -X GET '{{host}}/resource-info?resource_id=some_resource_id' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    resource_id = auth_data.get("resource_id")
    resources = auth_data.get("resources", [])
    admin_mode = auth_data.get("admin_mode", False)

    if resource_id:
        # Check if resource exists
        if resource_id not in resources:
            raise exceptions.MinkHTTPException(
                status.HTTP_404_NOT_FOUND,
                message="Resource does not exist or you do not have access to it",
                return_code="resource_not_found",
            )
        try:
            info = registry.get(resource_id)
        except Exception as e:
            raise exceptions.MinkHTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                message="Failed to get job status for resource",
                return_code="failed_getting_job_status",
                info=str(e),
            ) from e
        if not info:
            return utils.response(
                message="There is no active job for this resource",
                return_code="no_active_job",
                job_status=JobStatuses(
                    status=None,
                    processes=list(get_spec(info.resource.type).process_names),
                ).serialize(),
            )
        return utils.response(**route_utils.make_status_response(info, admin=admin_mode))

    try:
        # Get all job statuses for this user's resources
        res_list = []
        resources = registry.filter_resources(resources)
        for res in resources:
            resp_dict = route_utils.make_status_response(res, admin=admin_mode)
            res_list.append(resp_dict)
        return utils.response(message="Listing resource infos", resources=res_list, return_code="listing_jobs")
    except Exception as e:
        raise exceptions.MinkHTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to get job statuses",
            return_code="failed_getting_job_statuses",
            info=str(e),
        ) from e
