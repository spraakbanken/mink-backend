"""Routes for the sb-auth module."""


from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from mink.core import exceptions, models, return_codes, utils
from mink.sb_auth import cache
from mink.sb_auth.login import AuthDependencyNoResourceId

router = APIRouter(tags=["User Management"])


@router.post("/admin-mode-on", deprecated=True, name="admin-mode-on-deprecated")
@router.post(
    "/user/admin-mode/activate",
    operation_id="activate-admin-mode",
    response_model=models.BaseResponse,
    responses={
        status.HTTP_200_OK: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": return_codes.ADMIN_ON.message,
                        "return_code": return_codes.ADMIN_ON.code,
                    }
                }
            },
        },
        status.HTTP_400_BAD_REQUEST: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.MISSING_SESSION_ID.message,
                        "return_code": return_codes.MISSING_SESSION_ID.code,
                    }
                }
            }
        },
        **models.common_auth_error_responses,
    },
)
async def activate_admin_mode(
    auth_data: dict = Depends(AuthDependencyNoResourceId(require_admin=True)),
) -> JSONResponse:
    """Turn on admin mode for the user if the user can be verified as a Mink admin in the authentication system.

    When admin mode is activated the user will have full access to all resources in Mink. This works by setting a
    session cookie in the client. Admin mode will be activated until [turned off](#deactivate-admin-mode) or until the
    session expires.

    ### Example

    ```bash
    curl -X POST '{{host}}/user/admin-mode/activate' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    session_id = auth_data["session_id"]
    if session_id is None:
        raise exceptions.MinkHTTPException(return_code=return_codes.MISSING_SESSION_ID)
    cache.set_cookie_data(session_id, {"admin_mode": True})
    return utils.response(
        return_code=return_codes.ADMIN_ON, cookie=(True, "session_id", session_id)
    )


@router.post("/admin-mode-off", deprecated=True, name="admin-mode-off-deprecated")
@router.post(
    "/user/admin-mode/deactivate",
    operation_id="deactivate-admin-mode",
    response_model=models.BaseResponse,
    responses={
        status.HTTP_200_OK: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": return_codes.ADMIN_OFF.message,
                        "return_code": return_codes.ADMIN_OFF.code,
                    }
                }
            }
        },
        status.HTTP_400_BAD_REQUEST: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.MISSING_SESSION_ID.message,
                        "return_code": return_codes.MISSING_SESSION_ID.code,
                    }
                }
            }
        },
        **models.common_auth_error_responses
    }
)
async def deactivate_admin_mode(
    auth_data: dict = Depends(AuthDependencyNoResourceId())) -> JSONResponse:
    """Turn off admin mode for the user by removing the session cookie from the client.

    ### Example

    ```bash
    curl -X POST '{{host}}/user/admin-mode/deactivate' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    session_id = auth_data["session_id"]
    if session_id is None:
        raise exceptions.MinkHTTPException(return_code=return_codes.MISSING_SESSION_ID)
    # For now we can remove the cookie data because admin mode is the only data stored in the session
    cache.remove_cookie_data(session_id)
    return utils.response(return_code=return_codes.ADMIN_OFF, cookie=(False, "session_id", ""))


@router.get(
    "/admin-mode-status",
    deprecated=True,
    operation_id="admin-mode-status",
    response_model=models.BaseResponse,
    responses={
        status.HTTP_200_OK: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": return_codes.ADMIN_STATUS.message,
                        "return_code": return_codes.ADMIN_STATUS.code,
                        "admin_mode_status": True,
                    }
                }
            }
        },
        **models.common_auth_error_responses,
    },
)
async def admin_mode_status(auth_data: dict = Depends(AuthDependencyNoResourceId())) -> JSONResponse:
    """Check whether admin mode is activated.

    ### Example

    ```bash
    curl -X GET '{{host}}/admin-mode-status' -H 'Authorization: Bearer YOUR_JWT'
    ```
    """
    admin_status = cache.get_cookie_data(auth_data["session_id"], {}).get("admin_mode", False)
    return utils.response(return_code=return_codes.ADMIN_STATUS, admin_mode_status=admin_status)
