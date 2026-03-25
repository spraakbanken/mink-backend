"""Test all routes in the FastAPI app.

This module contains tests for all routes in the Mink FastAPI application.
It uses pytest for testing and FastAPI's TestClient for making requests to the app.
"""

import json
import logging
import time
import typing
from pathlib import Path

import httpx
import pytest
from fastapi import status
from fastapi.testclient import TestClient

from mink.core import return_codes
from mink.core.config import settings
from mink.main import app

from .conftest import ROUTE_INFO

# ------------------------------------------------------------------------------
# Setup
# ------------------------------------------------------------------------------

logger = logging.getLogger("mink_test")
HEADERS = {"X-Api-Key": settings.SBAUTH_PERSONAL_API_KEY}


# ------------------------------------------------------------------------------
# General tests
# ------------------------------------------------------------------------------


def test_untagged_routes() -> None:
    """Test that all routes are tagged."""
    logger.debug("Found %d routes", ROUTE_INFO.routes)
    assert len(ROUTE_INFO.untagged_routes) == 0, (
        f"Found {len(ROUTE_INFO.untagged_routes)} untagged routes: {ROUTE_INFO.untagged_routes}"
    )


def test_documentation_route() -> None:
    """Test documentation routes."""
    for method, path in ROUTE_INFO.tag_dict.get("Documentation", []):
        call_route(method, path)


def test_admin_mode() -> None:
    """Test admin mode routes."""
    routes = [
        ("1", "POST", "/admin-mode-on"),
        ("2", "GET", "/admin-mode-status"),
        ("3", "POST", "/admin-mode-off"),
        ("4", "GET", "/admin-mode-status"),
    ]
    admin_cookie = None
    for n, method, path in routes:
        response = call_route(
            method, path, headers=HEADERS, cookies={"session_id": admin_cookie} if admin_cookie else None
        )
        if n == "1":
            assert response.json().get("return_code") == return_codes.ADMIN_ON.code, (
                f"Route {method} {path} did not enable admin mode"
            )
            admin_cookie = response.cookies.get("session_id")
            assert admin_cookie is not None, "No session_id cookie set when enabling admin mode"
        elif n == "2":
            assert response.json().get("admin_mode_status") is True, (
                f"Admin mode should be on after enabling, but got {response.json().get('admin_mode_status')}"
            )
        if n == "3":
            assert response.json().get("return_code") == return_codes.ADMIN_OFF.code, (
                f"Route {method} {path} did not disable admin mode"
            )
        elif n == "4":
            assert response.json().get("admin_mode_status") is False, (
                f"Admin mode should be off after disabling, but got {response.json().get('admin_mode_status')}"
            )


def test_list_resources() -> None:
    """Test listing all resources regardless of type."""
    response = call_route("GET", "/resource/list", headers=HEADERS)
    json_data = response.json()
    assert isinstance(json_data.get("resources"), list), "Response should be a list of resources"


def test_list_resource_statuses() -> None:
    """Test listing all resource statuses."""
    response = call_route("GET", "/resource/status/list", headers=HEADERS)
    json_data = response.json()
    assert isinstance(json_data.get("resources"), list), "Response should be a list of resources"


# ------------------------------------------------------------------------------
# Corpus tests
# ------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def corpus() -> typing.Generator[str, None, None]:
    """Test creating a corpus."""
    response = call_route("POST", "/corpus/create", status_code=status.HTTP_201_CREATED, headers=HEADERS)
    json_data = response.json()
    assert json_data.get("return_code") == return_codes.CREATED_RESOURCE.code, f"Corpus creation failed: {json_data}"
    resource_id = json_data.get("resource_id")
    assert json_data.get("resource_id") is not None, "Resource ID should not be None"
    yield resource_id

    # Teardown: remove resource after all tests are done
    call_route("POST", f"/corpus/job/abort/{resource_id}", headers=HEADERS, fail_ok=True)
    response = call_route("DELETE", f"/corpus/remove/{resource_id}", headers=HEADERS)
    json_data = response.json()
    assert json_data.get("return_code") == return_codes.REMOVED_RESOURCE.code, f"Corpus removal failed: {json_data}"


def test_list_corpora(corpus: str) -> None:
    """Test listing corporaa."""
    routes = [
        ("GET", "/corpus/list"),
        ("GET", "/corpus/korp/list"),
    ]
    for method, path in routes:
        response = call_route(method, path, headers=HEADERS)
        json_data = response.json()
        assert isinstance(json_data.get("corpora"), list), "Response should be a list of resources"
        if path == "/corpus/list":
            assert corpus in json_data.get("corpora", []), f"Corpus {corpus} should be in the list of corpora"


@pytest.fixture(scope="module")
def corpus_with_sources(corpus: str) -> str:
    """Ensure a corpus exists and sources are uploaded."""
    with (
        Path("tests/test_data/test_source.txt").open("rb") as f1,
    ):
        call_route(
            "PUT",
            f"/corpus/sources/upload/{corpus}",
            status_code=status.HTTP_201_CREATED,
            headers=HEADERS,
            files=[
                ("files", ("test_source1.txt", f1)),
                ("files", ("test_source2.txt", f1)),
            ],
        )
    return corpus


def test_manage_corpus_sources(corpus_with_sources: str) -> None:
    """Test manage corpus sources routes."""
    routes = [
        ("GET", f"/corpus/sources/list/{corpus_with_sources}", None),
        ("GET", f"/corpus/sources/download/{corpus_with_sources}", None),
        ("DELETE", f"/corpus/sources/remove/{corpus_with_sources}", "remove=test_source2.txt"),
    ]
    for method, path, query in routes:
        response = call_route(method, path, query=query, headers=HEADERS)
        if path.startswith("/corpus/sources/list/"):
            json_data = response.json()
            assert isinstance(json_data.get("contents"), list), "Response should be a list of sources"
            assert len(json_data.get("contents", [])) > 0, "There should be at least one source file in the list"
        elif path.startswith("/corpus/sources/download/"):
            assert response.headers.get("Content-Disposition") is not None, (
                "Download response should have Content-Disposition header"
            )
            assert response.headers.get("Content-Type") == "application/zip", "Download response should be a zip file"
            assert len(response.content) > 0, "Downloaded file should not be empty"
        elif path.startswith("/corpus/sources/remove/"):
            json_data = response.json()
            assert json_data.get("return_code") == return_codes.REMOVED_CONTENT.code, (
                f"Source removal failed: {json_data}"
            )


@pytest.fixture(scope="module")
def corpus_with_sources_and_config(corpus_with_sources: str) -> str:
    """Ensure a corpus exists and sources are uploaded."""
    with Path("tests/test_data/test_config.yaml").open("rb") as f:
        call_route(
            "PUT",
            f"/corpus/config/upload/{corpus_with_sources}",
            status_code=status.HTTP_201_CREATED,
            headers=HEADERS,
            files=[("file", ("config.yaml", f))],
        )
    return corpus_with_sources


def test_download_corpus_config(corpus_with_sources_and_config: str) -> None:
    """Test download config route."""
    response = call_route("GET", f"/corpus/config/download/{corpus_with_sources_and_config}", headers=HEADERS)
    assert len(response.content) > 0, "Downloaded file should not be empty"


@pytest.fixture(scope="module")
def corpus_processed(corpus_with_sources_and_config: str) -> str:
    """Ensure a corpus is processed."""
    call_route("PUT", f"/corpus/job/run/{corpus_with_sources_and_config}", headers=HEADERS)
    json_data = check_resource_loop(resource_id=corpus_with_sources_and_config)
    sparv_status = json_data.get("job", {}).get("status", {}).get("sparv")
    assert sparv_status == "done", f"Corpus processing failed. Sparv status: {sparv_status}"
    return corpus_with_sources_and_config


def test_manage_corpus_exports(corpus_processed: str) -> None:
    """Test manage corpus exports routes."""
    routes = [
        ("GET", f"/corpus/exports/list/{corpus_processed}", None),
        ("GET", f"/corpus/exports/download/{corpus_processed}", None),
        ("GET", "/download-source-text", f"resource_id={corpus_processed}&file=test_source1.txt"),
        ("DELETE", f"/corpus/exports/remove/{corpus_processed}", None),
    ]
    for method, path, query in routes:
        response = call_route(method, path, query=query, headers=HEADERS)
        if path.startswith("/corpus/exports/list/"):
            json_data = response.json()
            assert isinstance(json_data.get("contents"), list), "Response should be a list of exports"
        elif path.startswith("/corpus/exports/download/"):
            assert response.headers.get("Content-Disposition") is not None, (
                "Download response should have Content-Disposition header"
            )
            assert response.headers.get("Content-Type") == "application/zip", "Download response should be a zip file"
            assert len(response.content) > 0, "Downloaded exports file should not be empty"
        elif path.startswith("/corpus/exports/remove/"):
            json_data = response.json()
            assert json_data.get("return_code") == return_codes.REMOVED_CONTENT.code, (
                f"Exports removal failed: {json_data}"
            )
        elif path == "/download-source-text":
            assert response.headers.get("Content-Type", "").startswith("text/"), (
                "Download source text should return a text content type"
            )
            assert len(response.content) > 0, "Downloaded source text should not be empty"


def test_processing_corpora(corpus_processed: str) -> None:
    """Test processing corpora routes."""
    routes = [
        ("GET", f"/corpus/job/check-input/{corpus_processed}", None),
        ("PUT", f"/corpus/job/run/{corpus_processed}", None),
        ("POST", f"/corpus/job/abort/{corpus_processed}", None),
        ("DELETE", f"/corpus/annotations/remove/{corpus_processed}", None),
        ("PUT", f"/corpus/korp/install/{corpus_processed}", "korp"),
        ("DELETE", f"/corpus/korp/uninstall/{corpus_processed}", None),
        ("PUT", f"/corpus/strix/install/{corpus_processed}", "strix"),
        ("DELETE", f"/corpus/strix/uninstall/{corpus_processed}", None),
    ]
    for method, path, process_name in routes:
        call_route(method, path, headers=HEADERS)

        if process_name:
            json_data = check_resource_loop(resource_id=corpus_processed, process_name=process_name, timeout=60)
            status = json_data.get("job", {}).get("status", {}).get(process_name)
            assert status == "done", f"{process_name} installation failed. Status: {status}"


# ------------------------------------------------------------------------------
# Metadata tests
# ------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def metadata() -> typing.Generator[str, None, None]:
    """Test creating a metadata resource."""
    response = call_route(
        "POST", "/metadata/create", query="public_id=sbx-pytest", status_code=status.HTTP_201_CREATED, headers=HEADERS
    )
    json_data = response.json()
    assert json_data.get("return_code") == return_codes.CREATED_RESOURCE.code, f"Metadata creation failed: {json_data}"
    resource_id = json_data.get("resource_id")
    assert json_data.get("resource_id") is not None, "Resource ID should not be None"
    yield resource_id

    # Teardown: remove resource after all tests are done
    response = call_route("DELETE", f"/metadata/remove/{resource_id}", headers=HEADERS)
    json_data = response.json()
    assert json_data.get("return_code") == return_codes.REMOVED_RESOURCE.code, f"Metadata removal failed: {json_data}"


def test_manage_metadata(metadata: str) -> None:
    """Test manage metadata routes."""
    routes = [
        ("PUT", f"/metadata/config/upload/{metadata}", status.HTTP_201_CREATED),
        ("GET", f"/metadata/config/download/{metadata}", status.HTTP_200_OK),
    ]
    for method, path, status_code in routes:
        if path.startswith("/metadata/config/upload/"):
            with Path("tests/test_data/test_config.yaml").open("rb") as f:
                response = call_route(
                    method,
                    path,
                    status_code=status_code,
                    headers=HEADERS,
                    files=[("file", ("test_metadata.yaml", f))],
                )
        else:
            response = call_route(method, path, status_code=status_code, headers=HEADERS)

        if path.startswith("/metadata/config/download/"):
            logger.debug(response.headers.get("Content-Type"))
            assert "text/yaml" in response.headers.get("Content-Type"), "Download should return YAML"
            assert len(response.content) > 0, "Downloaded metadata YAML should not be empty"


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


def check_resource_loop(resource_id: str, process_name: str = "sparv", timeout: int = 60) -> typing.Any:
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
