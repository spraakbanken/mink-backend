"""Login functions."""

import re
from contextvars import ContextVar
from pathlib import Path

import httpx
import jwt
import shortuuid
from fastapi import Cookie, Query, Request, Security, status
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer

from mink.cache import cache_utils
from mink.core import exceptions
from mink.core.config import settings
from mink.core.logging import logger
from mink.core.user import User

# Setup security schemes
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="", auto_error=False)
api_key_scheme = APIKeyHeader(name="X-Api-Key", auto_error=False)

# Context variable to store request ID
request_id_var = ContextVar("request_id_var", default=None)


async def get_auth_data(
    request: Request,
    session_id: str | None = Cookie(None),
    corpus_id: str | None = Query(None, description="Resource ID (deprecated, use resource_id instead)"),
    resource_id: str | None = Query(None, description="Resource ID"),
    jwt_token: str | None = Security(oauth2_scheme),
    api_key: str | None = Security(api_key_scheme),
    include_read: bool = False,
    require_resource_id: bool = True,
    require_resource_exists: bool = True,
    require_admin: bool = False,
) -> dict:
    """Attempt to login on SB Auth and check for different conditions required by the route.

    Args:
        request: The request object.
        session_id: The session ID from the cookie.
        corpus_id: The resource ID from the query parameter (deprecated).
        resource_id: The resource ID from the query parameter.
        jwt_token: The JWT token from the request.
        api_key: The API key from the request.
        include_read: Include resources that the user has read access to.
        require_resource_id: The route requires the user to supply a resource ID.
        require_resource_exists: The route requires that the supplied resource ID occurs in the JWT.
        require_admin: The route requires the user to be a mink admin.

    Returns:
        A dictionary containing user information, resource IDs, and an optional authentication token.
    """
    # TODO: For backwards compatibility, use corpus_id if resource_id is not provided
    if not resource_id:
        resource_id = corpus_id

    # Look for JWT
    if jwt_token:
        try:
            auth = JwtAuthentication(jwt_token)
            auth_token = jwt_token
        except jwt.ExpiredSignatureError as e:
            raise exceptions.MinkHTTPException(
                status.HTTP_401_UNAUTHORIZED, message="The provided JWT has expired", return_code="jwt_expired"
            ) from e
        except Exception as e:
            raise exceptions.MinkHTTPException(
                status.HTTP_401_UNAUTHORIZED,
                message="Failed to authenticate",
                return_code="failed_authenticating",
                info=str(e),
            ) from e

    # Look for API key
    elif api_key:
        try:
            auth = await ApikeyAuthentication.create(api_key)
            auth_token = api_key
        except exceptions.ApikeyNotFoundError as e:
            raise exceptions.MinkHTTPException(
                status.HTTP_401_UNAUTHORIZED, message="API key not recognized", return_code="apikey_not_found"
            ) from e
        except exceptions.ApikeyExpiredError as e:
            raise exceptions.MinkHTTPException(
                status.HTTP_401_UNAUTHORIZED, message="API key expired", return_code="apikey_expired"
            ) from e
        except exceptions.ApikeyCheckFailedError as e:
            raise exceptions.MinkHTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR, message="API key check failed", return_code="apikey_check_failed"
            ) from e
        except Exception as e:
            logger.exception("API key authentication failed")
            raise exceptions.MinkHTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                message="API key authentication failed",
                return_code="apikey_error",
                info=str(e),
            ) from e

    # No authentication provided
    else:
        raise exceptions.MinkHTTPException(
            status.HTTP_401_UNAUTHORIZED,
            message="No login credentials provided",
            return_code="missing_login_credentials",
        )

    # Store random ID in contextvar and in request state (used for temporary file storage and cookies)
    request_id = shortuuid.uuid()
    request.state.request_id = request_id
    request_id_var.set(request_id)
    if session_id is None:
        session_id = request_id

    # Get user info and which resources the user has access to from SB Auth
    user = auth.get_user()
    is_admin = auth.is_admin()
    sb_auth_resources = auth.get_resource_ids(include_read)
    all_resources = cache_utils.get_all_resources()
    # Get intersection between resources in SB Auth and resources in Mink-backend
    # (in case SB Auth is used for multiple backends)
    resources = list(set(sb_auth_resources) & set(all_resources))

    # Check admin mode in cache with cookie (session_id) and turn it off if user is not admin according to SB Auth
    admin_mode = cache_utils.get_cookie_data(session_id, {}).get("admin_mode", False)
    if not is_admin:
        cache_utils.set_cookie_data(session_id, {"admin_mode": False})
        # Raise exception if admin mode is required by the route
        if require_admin:
            raise exceptions.MinkHTTPException(
                status.HTTP_401_UNAUTHORIZED,
                message="Mink admin status could not be confirmed",
                return_code="not_admin",
            )

    # Give access to all resources if admin mode is on and user is mink admin
    if admin_mode and is_admin:
        resources = all_resources

    # Check if resource ID was provided
    if require_resource_id and not resource_id:
        raise exceptions.MinkHTTPException(
            status.HTTP_400_BAD_REQUEST, message="No resource ID provided", return_code="missing_resource_id"
        )

    auth_data = {
        "user_id": user.id,
        "user": user,
        "auth_token": auth_token,
        "session_id": session_id,
        "resources": resources,
        "resource_id": resource_id,
    }

    # Routes does not require resource ID, so we can skip the last check
    if not require_resource_id:
        return auth_data

    # Check if user has access to the requested resource
    if require_resource_exists and resource_id not in resources:
        raise exceptions.MinkHTTPException(
            status.HTTP_404_NOT_FOUND,
            message=f"Resource '{resource_id}' does not exist or you do not have access to it",
            return_code="resource_not_found",
        )

    return auth_data


class AuthDependency:
    """Dependency to get authentication data."""

    def __init__(
        self,
        include_read: bool = False,
        require_resource_id: bool = True,
        require_resource_exists: bool = True,
        require_admin: bool = False,
    ) -> None:
        """Initialize the AuthDependency class."""
        self.include_read = include_read
        self.require_resource_id = require_resource_id
        self.require_resource_exists = require_resource_exists
        self.require_admin = require_admin

    async def __call__(
        self,
        request: Request,
        session_id: str | None = Cookie(None, description="Session ID"),
        jwt_token: str | None = Security(oauth2_scheme),
        api_key: str | None = Security(api_key_scheme),
        corpus_id: str | None = Query(None, description="Resource ID (deprecated, use resource_id instead)"),
        # TODO: make resource_id required by replacing "None" with "..." when corpus_id has been removed
        resource_id: str = Query(None, description="Resource ID"),
    ) -> dict:
        """Call the authentication dependency."""
        return await get_auth_data(
            request,
            session_id,
            corpus_id,
            resource_id,
            jwt_token,
            api_key,
            self.include_read,
            self.require_resource_id,
            self.require_resource_exists,
            self.require_admin,
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
            include_read=self.include_read,
            require_resource_id=False,
            require_resource_exists=False,
            require_admin=self.require_admin,
        )


def read_jwt_key() -> None:
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
        """Return user."""
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
            return level >= self.levels[min_level] and resource_id.startswith(settings.RESOURCE_PREFIX)

        grants = {**self.scope.get("corpora", {}), **self.scope.get("metadata", {})}.items()
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
        data = cache_utils.get_apikey_data(apikey)
        if not data:
            data = await cls.check_apikey(apikey)
        cache_utils.set_apikey_data(apikey, data)

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


async def create_resource(auth_token: str, resource_id: str, resource_type: str | None = None) -> None:
    """Create a new resource in SB Auth.

    Args:
        auth_token: The authentication token (JWT or API key).
        resource_id: The resource ID.
        resource_type: The resource type.

    Raises:
        exceptions.CorpusExistsError: If the corpus already exists.
        exceptions.CreateResourceError: If creating the resource fails.
    """
    # API documented at https://github.com/spraakbanken/sb-auth#api
    # TODO: specify resource_type when SB Auth is ready
    url = settings.SBAUTH_URL + f"resource/{resource_id}"
    headers = {"Authorization": f"apikey {settings.SBAUTH_API_KEY}", "Content-Type": "application/json"}
    data = {"jwt": auth_token} if is_jwt(auth_token) else {"apikey": auth_token}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=data)
        except Exception:
            logger.exception("Could not create resource")
            raise

    if response.status_code == status.HTTP_400_BAD_REQUEST:
        raise exceptions.CorpusExistsError(resource_id)
    if response.status_code != status.HTTP_201_CREATED:
        message = response.content
        logger.error("Could not create resource, SB Auth returned status %s: %s", response.status_code, message)
        raise exceptions.CreateResourceError(resource_id, message)

    if not is_jwt(auth_token):
        # Remove cached API key data to force refresh next time
        cache_utils.remove_apikey_data(auth_token)


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
            cache_utils.remove_apikey_data(auth_token)

        return True
    if response.status_code == status.HTTP_400_BAD_REQUEST:
        # Corpus does not exist
        return False
    message = response.content
    raise exceptions.RemoveResourceError(resource_id, message)
