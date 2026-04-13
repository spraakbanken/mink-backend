"""Login functions."""

import re
from contextvars import ContextVar
from pathlib import Path

import httpx
import jwt
import shortuuid
from fastapi import Cookie, Request, Security, status
from fastapi import Path as FastAPIPath
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer

from mink.cache import jobs_cache
from mink.core import exceptions, return_codes
from mink.core.config import settings
from mink.core.logging import logger
from mink.core.user import User
from mink.sb_auth import cache as auth_cache

# Setup security schemes
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="", auto_error=False)
api_key_scheme = APIKeyHeader(name="X-Api-Key", auto_error=False)

# Context variable to store request ID
request_id_var = ContextVar("request_id_var", default="")


async def get_auth_data(
    request: Request,
    *,
    session_id: str | None = Cookie(None),
    resource_id: str | None = FastAPIPath(description="Resource ID"),
    jwt_token: str | None = Security(oauth2_scheme),
    api_key: str | None = Security(api_key_scheme),
    min_level: str = "READ",
    sbauth_resource_type: str | None = None,
    require_resource_id: bool = True,
    require_resource_exists: bool = True,
    require_admin: bool = False,
) -> dict:
    """Attempt to login on SB Auth and check for different conditions required by the route.

    Args:
        request: The request object.
        session_id: The session ID from the cookie.
        resource_id: The resource ID from the path parameter.
        jwt_token: The JWT token from the request.
        api_key: The API key from the request.
        min_level: Minimum access level to filter user's resources by.
        sbauth_resource_type: Optional SB Auth resource type key to filter accessible resources by.
        require_resource_id: The route requires the user to supply a resource ID.
        require_resource_exists: The route requires that the supplied resource ID occurs in the JWT.
        require_admin: The route requires the user to be a mink admin.

    Returns:
        A dictionary containing user information, resource information and the session ID.
    """
    # Look for JWT
    if jwt_token:
        try:
            auth = JwtAuthentication(jwt_token)
            auth_token = jwt_token
        except jwt.ExpiredSignatureError as e:
            raise exceptions.MinkHTTPException(return_code=return_codes.JWT_EXPIRED) from e
        except Exception as e:
            raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_AUTH, info=str(e)) from e

    # Look for API key
    elif api_key:
        try:
            auth = await ApikeyAuthentication.create(api_key)
            auth_token = api_key
        except exceptions.ApikeyNotFoundError as e:
            raise exceptions.MinkHTTPException(return_code=return_codes.API_KEY_NOT_FOUND) from e
        except exceptions.ApikeyExpiredError as e:
            raise exceptions.MinkHTTPException(return_code=return_codes.API_KEY_EXPIRED) from e
        except exceptions.ApikeyCheckFailedError as e:
            raise exceptions.MinkHTTPException(return_code=return_codes.API_KEY_CHECK_FAILED) from e
        except Exception as e:
            logger.exception("API key authentication failed")
            raise exceptions.MinkHTTPException(return_code=return_codes.API_KEY_ERROR, info=str(e)) from e

    # No authentication provided
    else:
        raise exceptions.MinkHTTPException(return_code=return_codes.MISSING_LOGIN_CREDENTIALS)

    # Store random ID in contextvar and in request state (used for temporary file storage and cookies)
    request_id = shortuuid.uuid()
    request.state.request_id = request_id
    request_id_var.set(request_id)
    if session_id is None:
        session_id = request_id

    # Get user info and which resources the user has access to from SB Auth
    user = auth.get_user()
    is_admin = auth.is_admin()
    sb_auth_resources = auth.get_resource_ids(min_level, resource_type=sbauth_resource_type)
    all_resources = jobs_cache.get_all_resources()
    # Get intersection between resources in SB Auth and resources in Mink-backend
    # (in case SB Auth is used for multiple backends)
    resources = list(set(sb_auth_resources) & set(all_resources))

    # Check admin mode in cache with cookie (session_id) and turn it off if user is not admin according to SB Auth
    admin_mode = auth_cache.get_cookie_data(session_id, {}).get("admin_mode", False)
    if not is_admin:
        admin_mode = False
        if session_id is not None:
            auth_cache.set_cookie_data(session_id, {"admin_mode": False})
        # Raise exception if admin mode is required by the route
        if require_admin:
            raise exceptions.MinkHTTPException(return_code=return_codes.NOT_ADMIN)

    # Give access to all resources if admin mode is on and user is mink admin
    if admin_mode and is_admin:
        resources = all_resources

    # Check if resource ID was provided
    if require_resource_id and not resource_id:
        raise exceptions.MinkHTTPException(return_code=return_codes.MISSING_RESOURCE_ID)

    auth_data = {
        "user": user,
        "auth_token": auth_token,
        "session_id": session_id,
        "resources": resources,
        "resource_id": resource_id,
        "admin_mode": admin_mode,
        "info_obj": None,
    }

    # Routes does not require resource ID, so we can skip the last check
    if not require_resource_id:
        return auth_data

    # Check if user has access to the requested resource
    if require_resource_exists and resource_id not in resources:
        raise exceptions.MinkHTTPException(return_code=return_codes.RESOURCE_NOT_FOUND)

    # Refresh persisted owner metadata for the requested resource
    try:
        from mink.core import registry  # noqa: PLC0415, Import lazily to avoid import cycle
        info_obj = registry.get(resource_id)
        info_obj.sync_owner(user)
        auth_data["info_obj"] = info_obj
    except exceptions.JobNotFoundError:
        pass
    except Exception:
        logger.exception("Failed to load/sync info object for resource '%s'.", resource_id)

    return auth_data


class AuthDependency:
    """Dependency to get authentication data."""

    def __init__(
        self,
        min_level: str = "READ",
        sbauth_resource_type: str | None = None,
        require_resource_id: bool = True,
        require_resource_exists: bool = True,
        require_admin: bool = False,
    ) -> None:
        """Initialize the AuthDependency class."""
        self.min_level = min_level
        self.sbauth_resource_type = sbauth_resource_type
        self.require_resource_id = require_resource_id
        self.require_resource_exists = require_resource_exists
        self.require_admin = require_admin

    async def __call__(
        self,
        request: Request,
        resource_id: str | None = FastAPIPath(description="Resource ID"),
        session_id: str | None = Cookie(None, description="Session ID"),
        jwt_token: str | None = Security(oauth2_scheme),
        api_key: str | None = Security(api_key_scheme),
    ) -> dict:
        """Call the authentication dependency."""
        return await get_auth_data(
            request,
            session_id=session_id,
            resource_id=resource_id,
            jwt_token=jwt_token,
            api_key=api_key,
            min_level=self.min_level,
            sbauth_resource_type=self.sbauth_resource_type,
            require_resource_id=self.require_resource_id,
            require_resource_exists=self.require_resource_exists,
            require_admin=self.require_admin,
        )


class AuthDependencyNoResourceId(AuthDependency):
    """AuthDependency variant that excludes resource_id."""

    async def __call__(
        self,
        request: Request,
        session_id: str | None = Cookie(None, description="Session ID"),
        jwt_token: str | None = Security(oauth2_scheme),
        api_key: str | None = Security(api_key_scheme),
    ) -> dict:
        """Call the authentication dependency without resource_id."""
        return await get_auth_data(
            request,
            session_id=session_id,
            jwt_token=jwt_token,
            api_key=api_key,
            min_level=self.min_level,
            sbauth_resource_type=self.sbauth_resource_type,
            require_resource_id=False,
            require_resource_exists=False,
            require_admin=self.require_admin,
        )


def read_jwt_key() -> str:
    """Read and return the public key for validating JWTs."""
    return (Path(settings.INSTANCE_PATH) / settings.SBAUTH_PUBKEY_FILE).open(encoding="utf-8").read()


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
        self.user = User(id=user_id, name=name, email=email, idp=idp, sub=sub)

    def set_resources(self, scope: dict, levels: dict) -> None:
        """Set scope and levels of resource grants.

        Args:
            scope: Scope of the resources.
            levels: Levels of access.
        """
        self.scope = scope
        self.levels = levels

    def get_user(self) -> User:
        """Return user."""
        return self.user

    def get_resource_ids(self, min_level: str = "READ", resource_type: str | None = None) -> list[str]:
        """Get a list of all resource IDs the user has access to.

        Args:
            min_level: Minimum access level to filter by.
            resource_type: The type of resource to filter by.

        Returns:
            A list of resource IDs.
        """

        def is_relevant(resource_id: str, level: int) -> bool:
            return level >= self.levels[min_level] and resource_id.startswith(settings.RESOURCE_PREFIX)

        # If resource_type is specified, only return resources of that type
        if resource_type:
            grants = self.scope.get(resource_type, {}).items()
        else:
            merged_grants: dict[str, int] = {}
            for scope_resource_type in settings.SBAUTH_RESOURCE_TYPES:
                merged_grants.update(self.scope.get(scope_resource_type, {}))
            grants = merged_grants.items()

        return [resource_id for resource_id, level in grants if is_relevant(resource_id, level)]

    def is_admin(self) -> bool:
        """Check whether user has admin rights.

        Returns:
            True if the user has admin rights, False otherwise.
        """
        mink_app_name = settings.SBAUTH_MINK_APP_RESOURCE
        return self.scope.get("other", {}).get(mink_app_name, 0) >= self.levels["ADMIN"]


class JwtAuthentication(Authentication):
    """Handles JWT authentication."""

    def __init__(self, token: str) -> None:
        """Do authentication with JWT.

        FastAPI will automatically check if the token is expired.

        Args:
            token: The JWT token.
        """
        self.payload = jwt.decode(token, key=read_jwt_key(), algorithms=["RS256"])

        self.set_user(
            self.payload["idp"], self.payload["sub"], self.payload.get("name", ""), self.payload.get("email", "")
        )
        self.set_resources(self.payload.get("scope", {}), self.payload.get("levels", {}))


def is_jwt(token: str) -> bool:
    """Check if the given token is a JWT.

    Args:
        token: The token to check.

    Returns:
        True if the token is a JWT, False otherwise.
    """
    try:
        jwt.decode(token, options={"verify_signature": False})
    except jwt.DecodeError:
        return False
    return True


class ApikeyAuthentication(Authentication):
    """Handles authentication using an API key."""

    def __init__(self, user: dict, scope: dict, levels: dict) -> None:
        """Initialize the ApikeyAuthentication instance."""
        self.set_user(**user)
        self.set_resources(scope, levels)

    @classmethod
    async def create(cls, apikey: str) -> "ApikeyAuthentication":
        """Asynchronously create an instance of ApikeyAuthentication.

        Args:
            apikey: The API key.

        Returns:
            An instance of ApikeyAuthentication.
        """
        # Get cached API key data if available, otherwise get from SB Auth
        data = auth_cache.get_apikey_data(apikey)
        if not data:
            data = await cls.check_apikey(apikey)
        auth_cache.set_apikey_data(apikey, data)

        return cls(user=data["user"], scope=data["scope"], levels=data["levels"])

    @staticmethod
    async def check_apikey(apikey: str) -> dict:
        """Check the given API key against SB Auth and get user information.

        Args:
            apikey: The API key.

        Returns:
            A dictionary containing the user and scope information.

        Raises:
            exceptions.ApikeyNotFoundError: If the API key is not recognized.
            exceptions.ApikeyExpiredError: If the API key has expired.
            exceptions.ApikeyCheckFailedError: If the API key check failed.
        """
        # API documented at https://github.com/spraakbanken/sb-auth#api
        url = settings.SBAUTH_URL + "apikey-check"
        headers = {
            "Authorization": f"apikey {settings.SBAUTH_API_KEY}",
            "Content-Type": "application/json",
        }
        data = {"apikey": apikey}

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=data)

        if response.status_code == status.HTTP_404_NOT_FOUND:
            raise exceptions.ApikeyNotFoundError
        if response.status_code == status.HTTP_410_GONE:
            raise exceptions.ApikeyExpiredError
        if response.status_code != status.HTTP_200_OK:
            logger.error(
                "API key check had unexpected status %s and content: %s", response.status_code, response.content
            )
            raise exceptions.ApikeyCheckFailedError

        return response.json()


async def create_resource(auth_token: str, resource_id: str, resource_type: str) -> None:
    """Create a new resource in SB Auth.

    SB auth API documented at https://github.com/spraakbanken/sb-auth#api

    Args:
        auth_token: The authentication token (JWT or API key).
        resource_id: The resource ID.
        resource_type: The resource type.

    Raises:
        exceptions.CorpusExistsError: If the corpus already exists.
        exceptions.CreateResourceError: If creating the resource fails.
    """
    # Check if resource_type is valid according to SB Auth resource types
    if resource_type not in settings.SBAUTH_RESOURCE_TYPES:
        raise exceptions.CreateResourceError(resource_id, f"Invalid resource type: {resource_type}")

    url = settings.SBAUTH_URL + f"resource/{resource_id}?type={resource_type}"
    headers = {"Authorization": f"apikey {settings.SBAUTH_API_KEY}", "Content-Type": "application/json"}
    data = {"jwt": auth_token} if is_jwt(auth_token) else {"apikey": auth_token}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=data)
        except Exception:
            logger.exception("Could not create resource")
            raise

    if response.status_code == status.HTTP_400_BAD_REQUEST:
        raise exceptions.ResourceExistsError(resource_id)
    if response.status_code != status.HTTP_201_CREATED:
        message = str(response.content)
        logger.error("Could not create resource, SB Auth returned status %s: %s", response.status_code, message)
        raise exceptions.CreateResourceError(resource_id, message)

    if not is_jwt(auth_token):
        # Remove cached API key data to force refresh next time
        auth_cache.remove_apikey_data(auth_token)


async def remove_resource(auth_token: str, resource_id: str) -> bool:
    """Remove a resource from SB Auth.

    Args:
        auth_token: The authentication token (JWT or API key).
        resource_id: The resource ID.

    Returns:
        True if the resource was removed successfully, False otherwise.

    Raises:
        exceptions.RemoveResourceError: If removing the resource fails.
    """
    # API documented at https://github.com/spraakbanken/sb-auth#api
    url = settings.SBAUTH_URL + f"resource/{resource_id}"
    headers = {"Authorization": f"apikey {settings.SBAUTH_API_KEY}", "Content-Type": "application/json"}
    data = {"jwt": auth_token} if is_jwt(auth_token) else {"apikey": auth_token}
    async with httpx.AsyncClient() as client:
        request = httpx.Request(method="DELETE", url=url, headers=headers, json=data)
        response = await client.send(request)

    if response.status_code == status.HTTP_204_NO_CONTENT:

        if not is_jwt(auth_token):
            # Remove cached API key data to force refresh next time
            auth_cache.remove_apikey_data(auth_token)

        return True
    if response.status_code == status.HTTP_400_BAD_REQUEST:
        # Corpus does not exist
        return False
    message = str(response.content)
    raise exceptions.RemoveResourceError(resource_id, message)
