"""Routes for the sb-auth module."""


from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from mink.cache import cache_utils
from mink.core import models, utils
from mink.sb_auth.login import AuthDependencyNoResourceId

router = APIRouter()


@router.post(
    "/admin-mode-on",
    tags=["Admin Mode"],
    response_model=models.BaseResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {"status": "success", "message": "Admin mode turned on", "return_code": "admin_on"}
                }
            },
        },
        **models.common_auth_error_responses
    },
)
async def admin_mode_on(auth_data: dict = Depends(AuthDependencyNoResourceId(require_admin=True))) -> JSONResponse:
    """Turn on admin mode for the user if the user can be verified as a Mink admin in the authentication system.

    When admin mode is activated the user will have full access to all corpora in Mink. This works by setting a session
    cookie in the client. Admin mode will be activated until [turned off](#admin-mode-off-post) or until the
    session expires.

    ### Example

    ```bash
    curl -X POST '{{host}}/admin-mode-on' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    session_id = auth_data.get("session_id")
    cache_utils.set_cookie_data(session_id, {"admin_mode": True})
    return utils.response(
        message="Admin mode turned on", return_code="admin_on", cookie=(True, "session_id", session_id)
    )


@router.post(
    "/admin-mode-off",
    tags=["Admin Mode"],
    response_model=models.BaseResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {"status": "success", "message": "Admin mode turned off", "return_code": "admin_off"}
                }
            }
        },
        **models.common_auth_error_responses
    }
)
async def admin_mode_off(
    auth_data: dict = Depends(AuthDependencyNoResourceId())) -> JSONResponse:
    """Turn off admin mode for the user by removing the session cookie from the client.

    ### Example

    ```bash
    curl -X POST '{{host}}/admin-mode-off' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    session_id = auth_data.get("session_id")
    cache_utils.set_cookie_data(session_id, {"admin_mode": False})
    return utils.response(message="Admin mode turned off", return_code="admin_off", cookie=(False, "session_id", ""))


@router.get(
    "/admin-mode-status",
    tags=["Admin Mode"],
    response_model=models.BaseResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "Returning status of admin mode",
                        "return_code": "returning_admin_status",
                        "admin_mode_status": True,
                    }
                }
            }
        },
        **models.common_auth_error_responses,
    },
)
async def admin_mode_status(
    auth_data: dict = Depends(AuthDependencyNoResourceId())) -> JSONResponse:
    """Check whether admin mode is turned on or off.

    ### Example

    ```bash
    curl -X GET '{{host}}/admin-mode-status' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    admin_status = cache_utils.get_cookie_data(auth_data.get("session_id"), {}).get("admin_mode", False)
    return utils.response(
        message="Returning status of admin mode", return_code="returning_admin_status", admin_mode_status=admin_status
    )
