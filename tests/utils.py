"""Utility functions for testing routes."""

import json
import logging
import time
import typing

import httpx
import pytest
from fastapi import status
from fastapi.testclient import TestClient

from mink.core.config import settings
from mink.main import app

from .conftest import ROUTE_INFO

# ------------------------------------------------------------------------------
# Setup
# ------------------------------------------------------------------------------

logger = logging.getLogger("mink_test")
HEADERS = {"X-Api-Key": settings.SBAUTH_PERSONAL_API_KEY}


# ------------------------------------------------------------------------------
# Utilities
# ------------------------------------------------------------------------------

def call_route(
    method: str,
    path: str,
    *,
    query: str | None = None,
    status_code: int = status.HTTP_200_OK,
    headers: dict | None = None,
    files: list | None = None,
    cookies: dict | None = None,
    fail_ok: bool = False,
    log: bool = True,
) -> httpx._models.Response:
    """Call a route with the specified method, path and query and check if it returns the expected status code.

    Args:
        method (str): HTTP method to use (e.g., "GET", "POST", "PUT", "DELETE").
        path (str): Path of the route to call.
        query (str | None): Query string to append to the path, if any.
        status_code (int): Expected status code of the response.
        headers (dict | None): Headers to include in the request.
        files (list | None): Files to upload with the request, if any.
        cookies (dict | None): Cookies to include in the request, if any.
        fail_ok (bool): If True, do not fail the test if the status code does not match.
        log (bool): Whether to log the request and response.

    Returns:
        The response from the route call.
    """
    with TestClient(app) as client:
        if cookies:
            client.cookies.update(cookies)
        try:
            if log:
                log_request(method, path, query)
            url = f"{path}?{query}" if query else path
            response = client.request(method, url, headers=headers, files=files)
            if log:
                log_response(response, method)
        except Exception as e:
            pytest.fail(f"Route {method} {path} raised exception: {e}")
        if not fail_ok:
            assert response.status_code == status_code, (
                f"Route {method} {path} failed with status code {response.status_code}"
            )
    ROUTE_INFO.set_tested(path)
    return response


def log_request(method: str, path: str, query: str | None) -> None:
    """Log the request being tested."""
    if query:
        logger.info("Calling %s %s?%s ...", method, path, query)
    else:
        logger.info("Calling %s %s ...", method, path)


def log_response(response: typing.Any, method: str, loglevel: int = logging.DEBUG) -> None:
    """Log the response."""
    url = f"{response.url.path}?{response.url.query.decode()}" if response.url.query else response.url.path

    # Check if response is JSON
    response_json = None
    if response.headers.get("Content-Type") == "application/json":
        try:
            response_json = response.json()
        except ValueError:
            pass
    if response_json is not None:
        content = json.dumps(response_json, indent=4)
        logger.log(loglevel, "Response from %s %s:\n%s", method, url, content)
    else:
        logger.log(loglevel, "Response from %s %s:\n%s...", method, url, response.text[:100])


def check_resource_loop(resource_id: str, process_name: str, timeout: int = 60) -> typing.Any:
    """Call /resource/status/get and /queue/advance until the resource is processed, abort if it takes too long.

    Returns:
        A tuple containing the JSON response from /resource/status/get
        and a boolean indicating if the timeout was reached.
    """
    start = time.time()
    process_status = None
    while True:
        call_route("PUT", "/queue/advance", query=f"secret_key={settings.MINK_SECRET_KEY}", headers=HEADERS, log=False)
        response = call_route("GET", f"/resource/status/get/{resource_id}", headers=HEADERS)
        json_data = response.json()
        process_status = json_data.get("job", {}).get("status", {}).get(process_name)
        progress = json_data.get("job", {}).get("progress", {})
        sparv_output = json_data.get("job", {}).get("sparv_output", {})
        if not sparv_output or progress == "100%":
            logger.info("Process status: %s, progress: %s", process_status, progress)
        else:
            logger.info("Process status: %s, progress: %s, sparv_output: %s", process_status, progress, sparv_output)
        if process_status in {"done", "error", "aborted"}:
            return json_data
        if time.time() - start > timeout:
            pytest.fail(f"{process_status} processing timed out after {timeout} seconds. Last status: {process_status}")
        time.sleep(5)
