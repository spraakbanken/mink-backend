"""Login functions."""

import functools
import inspect
import json
import re
import time
import traceback
from pathlib import Path
from typing import Callable, Optional

import jwt
import requests
import shortuuid
from flask import Blueprint, Response, g, request, session
from flask import current_app as app

from mink.core import exceptions, registry, utils
from mink.core.user import User

bp = Blueprint("sb_auth_login", __name__)


def login(
    include_read: bool = False,
    require_resource_id: bool = True,
    require_resource_exists: bool = True,
    require_admin: bool = False,
) -> Callable:
    """Attempt to login on sb-auth.

    Args:
        include_read: Include resources that the user has read access to.
        require_resource_id: This route requires the user to supply a resource ID.
        require_resource_exists: This route requires that the supplied resource ID occurs in the JWT.
        require_admin: This route requires the user to be a mink admin.

    Returns:
        A decorator function.
    """

    def decorator(function: Callable) -> Callable:
        @functools.wraps(function)  # Copy original function's information, needed by Flask
        def wrapper() -> tuple[Response, int]:
            # Get the function's params
            params = inspect.signature(function).parameters.keys()

            auth_header = request.headers.get("Authorization")
            apikey = request.headers.get("X-Api-Key")

            auth_token = None

            # Look for JWT
            if auth_header:
                try:
                    auth_token = auth_header.split(" ")[1]
                except Exception:
                    return utils.response(
                        "No authorization token provided", err=True, return_code="missing_auth_token"
                    ), 401

                try:
                    auth = JwtAuthentication(auth_token)
                except exceptions.JwtExpiredError:
                    return utils.response("The provided JWT has expired", err=True, return_code="jwt_expired"), 401
                except Exception as e:
                    return utils.response(
                        "Failed to authenticate", err=True, info=str(e), return_code="failed_authenticating"
                    ), 401

            # Look for API key
            elif apikey:
                try:
                    auth = ApikeyAuthentication(apikey)
                    auth_token = None
                except exceptions.ApikeyNotFoundError:
                    return utils.response("API key not recognized", err=True, return_code="apikey_not_found"), 401
                except exceptions.ApikeyExpiredError:
                    return utils.response("API key expired", err=True, return_code="apikey_expired"), 401
                except exceptions.ApikeyCheckFailedError:
                    return utils.response("API key check failed", err=True, return_code="apikey_check_failed"), 500
                except Exception as e:
                    app.logger.exception("API key authentication failed")
                    return utils.response(
                        "API key authentication failed", err=True, info=str(e), return_code="apikey_error"
                    ), 500

            # No authentication provided
            else:
                return utils.response(
                    "No login credentials provided", err=True, return_code="missing_login_credentials"
                ), 401

            resources = auth.get_resource_ids(include_read)
            user = auth.get_user()

            if require_admin and not auth.is_admin():
                return utils.response(
                    "Mink admin status could not be confirmed", err=True, return_code="not_admin"
                ), 401

            # Give access to all resources if admin mode is on and user is mink admin
            if session.get("admin_mode") and auth.is_admin():
                resources = registry.get_all_resources()
            else:
                # Turn off admin mode if user is not admin
                session["admin_mode"] = False

            if "auth_token" in params and auth_token is None:
                return utils.response(
                    "This route requires authentication by JWT", err=True, return_code="route_requires_jwt"
                ), 400

            try:
                # Store random ID in app context, used for temporary storage
                g.request_id = shortuuid.uuid()

                if not require_resource_id:
                    return function(
                        **{
                            k: v
                            for k, v in {
                                "user_id": user.id,
                                "user": user,
                                "corpora": resources,
                                "auth_token": auth_token,
                            }.items()
                            if k in params
                        }
                    )

                # Check if resource ID was provided
                # TODO: change param name from corpus_id to resource_id!
                resource_id = request.args.get("corpus_id") or request.form.get("resource_id")
                if not resource_id:
                    return utils.response("No resource ID provided", err=True, return_code="missing_corpus_id"), 400

                # Check if resource exists
                if not require_resource_exists:
                    return function(
                        **{
                            k: v
                            for k, v in {
                                "user_id": user.id,
                                "user": user,
                                "corpora": resources,
                                "resource_id": resource_id,
                                "auth_token": auth_token,
                            }.items()
                            if k in params
                        }
                    )

                # Check if user is admin for resource
                if resource_id not in resources:
                    return utils.response(
                        f"Corpus '{resource_id}' does not exist or you do not have access to it",
                        err=True,
                        return_code="corpus_not_found",
                    ), 404
                return function(
                    **{
                        k: v
                        for k, v in {
                            "user_id": user.id,
                            "user": user,
                            "corpora": resources,
                            "resource_id": resource_id,
                            "auth_token": auth_token,
                        }.items()
                        if k in params
                    }
                )

            # Catch everything else and return a traceback
            except Exception as e:
                traceback_str = f"{e}: {''.join(traceback.format_tb(e.__traceback__))}"
                return utils.response(
                    "Something went wrong", err=True, info=traceback_str, return_code="something_went_wrong"
                ), 500

        return wrapper

    return decorator


@bp.route("/admin-mode-on", methods=["POST"])
@login(require_resource_exists=False, require_resource_id=False, require_admin=True)
def admin_mode_on() -> Response:
    """Turn on admin mode.

    Returns:
        A response indicating the status of the operation.
    """
    session["admin_mode"] = True
    return utils.response("Admin mode turned on", return_code="admin_on")


@bp.route("/admin-mode-off", methods=["POST"])
@login(require_resource_exists=False, require_resource_id=False)
def admin_mode_off() -> Response:
    """Turn off admin mode.

    Returns:
        A response indicating the status of the operation.
    """
    session["admin_mode"] = False
    return utils.response("Admin mode turned off", return_code="admin_off")


@bp.route("/admin-mode-status", methods=["GET"])
@login(require_resource_exists=False, require_resource_id=False)
def admin_mode_status() -> Response:
    """Return status of admin mode.

    Returns:
        A response indicating the status of the operation.
    """
    admin_status = session.get("admin_mode", False)
    return utils.response(
        "Returning status of admin mode", admin_mode_status=admin_status, return_code="returning_admin_status"
    )


def read_jwt_key() -> None:
    """Read and return the public key for validating JWTs."""
    app.config["JWT_KEY"] = (
        (Path(app.instance_path) / app.config.get("SBAUTH_PUBKEY_FILE")).open(encoding="utf-8").read()
    )


class Authentication:
    """Abstract class for an authentication method."""

    def set_user(self, idp: str, sub: str, name: str, email: str) -> None:
        """Set user attributes.

        Args:
            idp: Identity provider.
            sub: Subject.
            name: User's name.
            email: User's email.
        """
        user_id = re.sub(r"[^\w\-_\.]", "", (f"{idp}-{sub}"))
        self.user = User(id=user_id, name=name, email=email)

    def set_resources(self, scope: dict, levels: dict) -> None:
        """Set scope and levels of resource grants.

        Args:
            scope: Scope of the resources.
            levels: Levels of access.
        """
        self.scope = scope
        self.levels = levels

    def get_user(self) -> User:
        """Return user.

        Returns:
            The user object.
        """
        return self.user

    def get_resource_ids(self, include_read: bool = False) -> list[str]:
        """Get a list of all resource IDs the user has access to.

        Args:
            include_read: Include resources that the user has read access to.

        Returns:
            A list of resource IDs.
        """
        min_level = "READ" if include_read else "WRITE"

        def is_relevant(resource_id: str, level: int) -> bool:
            return level >= self.levels[min_level] and resource_id.startswith(app.config.get("RESOURCE_PREFIX"))

        grants = {**self.scope.get("corpora", {}), **self.scope.get("metadata", {})}.items()
        return [resource_id for resource_id, level in grants if is_relevant(resource_id, level)]

    def is_admin(self) -> bool:
        """Check whether user has admin rights.

        Returns:
            True if the user has admin rights, False otherwise.
        """
        mink_app_name = app.config.get("SBAUTH_MINK_APP_RESOURCE", "")
        return self.scope.get("other", {}).get(mink_app_name, 0) >= self.levels["ADMIN"]


class JwtAuthentication(Authentication):
    """Handles JWT authentication."""

    def __init__(self, token: str) -> None:
        """Do authentication with JWT.

        Args:
            token: The JWT token.

        Raises:
            JwtExpiredError: If the JWT has expired.
        """
        self.payload = jwt.decode(token, key=app.config.get("JWT_KEY"), algorithms=["RS256"])
        if self.payload["exp"] < time.time():
            raise exceptions.JwtExpiredError

        self.set_user(
            self.payload["idp"], self.payload["sub"], self.payload.get("name", ""), self.payload.get("email", "")
        )
        self.set_resources(self.payload.get("scope", {}), self.payload.get("levels", {}))


class ApikeyAuthentication(Authentication):
    """Handles authentication using an API key."""

    def __init__(self, apikey: str) -> None:
        """Do authentication with API key.

        Args:
            apikey: The API key.

        Raises:
            ApikeyNotFoundError: If the API key is not recognized.
            ApikeyExpiredError: If the API key has expired.
            ApikeyCheckFailedError: If the API key check failed.
        """
        # Make a cached HTTP request
        data = g.cache.get_apikey_data(apikey)
        if not data:
            data = self.check_apikey(apikey)
            g.cache.set_apikey_data(apikey, data)

        self.set_user(**data["user"])
        self.set_resources(data["scope"], data["levels"])

    @staticmethod
    def check_apikey(apikey: str) -> dict:
        """Check the given API key against SB-Auth.

        Args:
            apikey: The API key.

        Returns:
            A dictionary containing the user and scope information.

        Raises:
            ApikeyNotFoundError: If the API key is not recognized.
            ApikeyExpiredError: If the API key has expired.
            ApikeyCheckFailedError: If the API key check failed.
        """
        # API documented at https://github.com/spraakbanken/sb-auth#api
        url = app.config.get("SBAUTH_URL") + "apikey-check"
        headers = {
            "Authorization": f"apikey {app.config.get('SBAUTH_API_KEY')}",
            "Content-Type": "application/json",
        }
        data = {"apikey": apikey}

        r = requests.post(url, headers=headers, data=json.dumps(data))

        if r.status_code == 404:  # noqa: PLR2004
            raise exceptions.ApikeyNotFoundError
        if r.status_code == 410:  # noqa: PLR2004
            raise exceptions.ApikeyExpiredError
        if r.status_code != 200:  # noqa: PLR2004
            app.logger.error("API key check had unexpected status %s and content: %s", r.status_code, r.content)
            raise exceptions.ApikeyCheckFailedError

        return json.loads(r.content)


def create_resource(auth_token: str, resource_id: str, resource_type: Optional[str] = None) -> None:
    """Create a new resource in sb-auth.

    Args:
        auth_token: The authentication token.
        resource_id: The resource ID.
        resource_type: The resource type.

    Raises:
        CorpusExistsError: If the corpus already exists.
        Exception: If creating the resource fails.
    """
    # API documented at https://github.com/spraakbanken/sb-auth#api
    # TODO: specify resource_type when sbauth is ready
    url = app.config.get("SBAUTH_URL") + f"resource/{resource_id}"
    api_key = app.config.get("SBAUTH_API_KEY")
    headers = {"Authorization": f"apikey {api_key}", "Content-Type": "application/json"}
    data = {"jwt": auth_token}
    try:
        r = requests.post(url, headers=headers, data=json.dumps(data))
        status = r.status_code
    except Exception as e:
        app.logger.exception("Could not create resource")
        raise e
    if status == 400:  # noqa: PLR2004
        raise exceptions.CorpusExistsError
    if status != 201:  # noqa: PLR2004
        message = r.content
        app.logger.error("Could not create resource, sb-auth returned status %s: %s", status, message)
        raise Exception(message)


def remove_resource(resource_id: str) -> bool:
    """Remove a resource from sb-auth.

    Args:
        resource_id: The resource ID.

    Returns:
        True if the resource was removed successfully, False otherwise.

    Raises:
        Exception: If removing the resource fails.
    """
    # API documented at https://github.com/spraakbanken/sb-auth#api
    url = app.config.get("SBAUTH_URL") + f"resource/{resource_id}"
    api_key = app.config.get("SBAUTH_API_KEY")
    headers = {"Authorization": f"apikey {api_key}"}
    try:
        r = requests.delete(url, headers=headers)
        status = r.status_code
    except Exception as e:
        raise e
    if status == 204:  # noqa: PLR2004
        return True
    if status == 400:  # noqa: PLR2004
        # Corpus does not exist
        return False
    message = r.content
    raise Exception(message)
