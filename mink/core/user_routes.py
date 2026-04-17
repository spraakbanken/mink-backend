"""Routes related to jobs status and information."""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from mink.core import exceptions, models, return_codes, route_utils, utils
from mink.sb_auth import login

router = APIRouter(prefix="/user", tags=["User Management"])


@router.get(
    "/info/get",
    operation_id="get-user-info",
    response_model=models.UserInfoResponse,
    responses={**models.common_auth_error_responses},
)
async def get_user_info(auth_data: dict = Depends(login.AuthDependencyNoResourceId())) -> JSONResponse:
    """Return all user related info for the authenticated user.

    ### Example

    ```bash
    curl -X GET '{{host}}/user/info/get' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    try:
        # whether user is able to be admin? app_grant
        user = auth_data["user"].serialize() if auth_data.get("user") else {}
        user["is_admin"] = auth_data.get("is_admin", False)
        user["admin_mode"] = auth_data.get("admin_mode", False)
        user["organization_prefix"] = route_utils.get_user_organization_prefix(auth_data["user"])

        return utils.response(
            return_code=return_codes.LISTING_CONTENT, info="Listing user info", user=user
        )
    except Exception as e:
        raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_LISTING_CONTENT, info=str(e)) from e
