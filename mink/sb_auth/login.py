"""Login functions."""

from abc import ABC, abstractmethod
import functools
import inspect
import json
import re
import time
import traceback
from pathlib import Path
from typing import List

import jwt
import requests
import shortuuid
from flask import Blueprint
from flask import current_app as app
from flask import g, request, session

from mink.core import exceptions, registry, utils
from mink.core.user import User

bp = Blueprint("sb_auth_login", __name__)


def login(include_read=False, require_resource_id=True, require_resource_exists=True, require_admin=False):
    """Attempt to login on sb-auth.

    Args:
        include_read (bool, optional): Include resources that the user has read access to. Defaults to False.
        require_resource_id (bool, optional): This route requires the user to supply a resource ID. Defaults to True.
        require_resource_exists (bool, optional): This route requires that the supplied resource ID occurs in the JWT.
            Defaults to True.
        require_admin (bool, optional): This route requires the user to be a mink admin. Defaults to False.
    """
    def decorator(function):
        @functools.wraps(function)  # Copy original function's information, needed by Flask
        def wrapper():
            # Get the function's params
            params = inspect.signature(function).parameters.keys()

            auth_header = request.headers.get("Authorization")
            apikey = request.headers.get("X-Api-Key")

            # Look for JWT
            if auth_header:
                try:
                    auth_token = auth_header.split(" ")[1]
                except Exception:
                    return utils.response("No authorization token provided", err=True,
                                        return_code="missing_auth_token"), 401

                try:
                    auth = JwtAuthentication(auth_token)
                except exceptions.JwtExpired:
                    return utils.response("The provided JWT has expired", err=True, return_code="jwt_expired"), 401
                except Exception as e:
                    return utils.response("Failed to authenticate", err=True, info=str(e),
                                        return_code="failed_authenticating"), 401
            
            # Look for API key
            elif apikey:
                try:
                    auth = ApikeyAuthentication(apikey)
                except exceptions.ApikeyNotFound:
                    return utils.response("API key not recognized", err=True, return_code="apikey_not_found"), 401
                except exceptions.ApikeyExpired:
                    return utils.response("API key expired", err=True, return_code="apikey_expired"), 401
                except exceptions.ApikeyCheckFailed:
                    return utils.response("API key check failed", err=True, return_code="apikey_check_failed"), 500
                except Exception as e:
                    app.logger.error("API key authentication failed: %s", str(e))
                    return utils.response("API key authentication failed", err=True, info=str(e), return_code="apikey_error"), 500

            # No authentication provided
            else:
                return utils.response("No login credentials provided", err=True,
                                      return_code="missing_login_credentials"), 401

            resources = auth.get_resource_ids()
            user = auth.get_user()

            if require_admin and not auth.is_admin():
                    return utils.response("Mink admin status could not be confirmed", err=True,
                                          return_code="not_admin"), 401

            # Give access to all resources if admin mode is on and user is mink admin
            if session.get("admin_mode") and auth.is_admin():
                resources = registry.get_all_resources()
            else:
                # Turn off admin mode if user is not admin
                session["admin_mode"] = False

            try:
                # Store random ID in app context, used for temporary storage
                g.request_id = shortuuid.uuid()

                if not require_resource_id:
                    return function(**{k: v for k, v in {"user_id": user.id, "user": user,
                                                         "corpora": resources, "auth_token": auth_token
                                                        }.items() if k in params})

                # Check if resource ID was provided
                # TODO: change param name from corpus_id to resource_id!
                resource_id = request.args.get("corpus_id") or request.form.get("resource_id")
                if not resource_id:
                    return utils.response("No resource ID provided", err=True, return_code="missing_corpus_id"), 400

                # Check if resource exists
                if not require_resource_exists:
                    return function(**{k: v for k, v in {"user_id": user.id, "user": user,
                                                         "corpora": resources, "resource_id": resource_id,
                                                         "auth_token": auth_token
                                                        }.items() if k in params})

                # Check if user is admin for resource
                if resource_id not in resources:
                    return utils.response(f"Corpus '{resource_id}' does not exist or you do not have access to it",
                                          err=True, return_code="corpus_not_found"), 404
                return function(**{k: v for k, v in {"user_id": user.id, "user": user,
                                                     "corpora": resources, "resource_id": resource_id,
                                                     "auth_token": auth_token}.items() if k in params})

            # Catch everything else and return a traceback
            except Exception as e:
                traceback_str = f"{e}: {''.join(traceback.format_tb(e.__traceback__))}"
                return utils.response("Something went wrong", err=True, info=traceback_str,
                                      return_code="something_went_wrong"), 500

        return wrapper
    return decorator


@bp.route("/admin-mode-on", methods=["POST"])
@login(require_resource_exists=False, require_resource_id=False, require_admin=True)
def admin_mode_on():
    session["admin_mode"] = True
    return utils.response("Admin mode turned on", return_code="admin_on")


@bp.route("/admin-mode-off", methods=["POST"])
@login(require_resource_exists=False, require_resource_id=False)
def admin_mode_off():
    session["admin_mode"] = False
    return utils.response("Admin mode turned off", return_code="admin_off")


@bp.route("/admin-mode-status", methods=["GET"])
@login(require_resource_exists=False, require_resource_id=False)
def admin_mode_status():
    admin_status = session.get("admin_mode", False)
    return utils.response("Returning status of admin mode", admin_mode_status=admin_status,
                          return_code="returning_admin_status")


def read_jwt_key():
    """Read and return the public key for validating JWTs."""
    app.config["JWT_KEY"] = open(Path(app.instance_path) / app.config.get("SBAUTH_PUBKEY_FILE")).read()


class Authentication(ABC):
    """Interface for an authentication method"""
    @abstractmethod
    def get_user(self) -> User:
        pass

    @abstractmethod
    def get_resource_ids(self, include_read=False) -> List[str]:
        pass

    @abstractmethod
    def is_admin(self) -> bool:
        pass


class JwtAuthentication(Authentication):
    """Handles JWT authentication"""
    def __init__(self, token: str):
        self.payload = jwt.decode(token, key=app.config.get("JWT_KEY"), algorithms=["RS256"])
        if self.payload["exp"] < time.time():
            raise exceptions.JwtExpired()

    def get_user(self) -> User:
        user_id = re.sub(r"[^\w\-_\.]", "", (self.payload["idp"] + "-" + self.payload["sub"]))
        name = self.payload.get("name", "")
        email = self.payload.get("email", "")
        return User(id=user_id, name=name, email=email)

    def get_resource_ids(self, include_read=False) -> List[str]:
        resources = []
        min_level = "READ" if include_read else "WRITE"
        if "scope" in self.payload:
            # Get list of corpora
            for corpus, level in self.payload["scope"].get("corpora", {}).items():
                if level >= self.payload["levels"][min_level] and corpus.startswith(app.config.get("RESOURCE_PREFIX")):
                    resources.append(corpus)
            # Get list of metadata resources
            for metadata, level in self.payload["scope"].get("metadata", {}).items():
                if level >= self.payload["levels"][min_level] and metadata.startswith(app.config.get("RESOURCE_PREFIX")):
                    resources.append(metadata)
        return resources

    def is_admin(self) -> bool:
        mink_app_name = app.config.get("SBAUTH_MINK_APP_RESOURCE", "")
        return self.payload["scope"].get("other", {}).get(mink_app_name, 0) >= self.payload["levels"]["ADMIN"]


class ApikeyAuthentication(Authentication):
    """Handles authentication using an API key"""
    def __init__(self, apikey: str):
        # Check the given API key against SB-Auth
        # API documented at https://github.com/spraakbanken/sb-auth#api
        url = app.config.get("SBAUTH_URL") + 'apikey-check'
        headers = {
            "Authorization": f"apikey {app.config.get("SBAUTH_API_KEY")}",
            "Content-Type": "application/json",
        }
        data = {"apikey": apikey}

        r = requests.post(url, headers=headers, data=json.dumps(data))

        if r.status_code == 404:
            raise exceptions.ApikeyNotFound()
        if r.status_code == 410:
            raise exceptions.ApikeyExpired()
        if r.status_code != 200:
            app.logger.error("API key check had unexpected status %s and content: %s", r.status_code, r.content)
            raise exceptions.ApikeyCheckFailed()

        data = json.loads(r.content)
        self.user = data["user"]
        self.scope = data["scope"]
        self.levels = data["levels"]
        self.token = data["token"]

    def get_user(self) -> User:
        user_id = re.sub(r"[^\w\-_\.]", "", (self.user["idp"] + "-" + self.user["sub"]))
        name = self.user.get("name", "")
        email = self.user.get("email", "")
        return User(id=user_id, name=name, email=email)

    def get_resource_ids(self, include_read=False) -> List[str]:
        min_level = "READ" if include_read else "WRITE"
        def is_relevant(resource_id, level):
            return level >= self.levels[min_level] and resource_id.startswith(app.config.get("RESOURCE_PREFIX"))
        grants = self.scope.get("corpora", {}).items() + self.scope.get("metadata", {}).items()
        return [resource_id for resource_id, level in grants if is_relevant(resource_id, level)]
    
    def is_admin(self) -> bool:
        mink_app_name = app.config.get("SBAUTH_MINK_APP_RESOURCE", "")
        return self.scope.get("other", {}).get(mink_app_name, 0) >= self.levels["ADMIN"]


def create_resource(auth_token, resource_id, resource_type=None):
    """Create a new resource in sb-auth."""
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
        app.logger.error("Could not create resource: %s", e)
        raise (e)
    if status == 400:
        raise exceptions.CorpusExists
    elif status != 201:
        message = r.content
        app.logger.error(
            "Could not create resource, sb-auth returned status %s: %s", status, message
        )
        raise Exception(message)


def remove_resource(resource_id) -> bool:
    """Remove a resource from sb-auth."""
    # API documented at https://github.com/spraakbanken/sb-auth#api
    url = app.config.get("SBAUTH_URL") + f"resources/{resource_id}"
    api_key = app.config.get("SBAUTH_API_KEY")
    headers = {"Authorization": f"apikey {api_key}"}
    try:
        r = requests.delete(url, headers=headers)
        status = r.status_code
    except Exception as e:
        raise e
    if status == 204:
        return True
    elif status == 400:
        # Corpus does not exist
        return False
    else:
        message = r.content
        raise Exception(message)
