"""Test metadata routes."""

import typing
from pathlib import Path

import pytest
from fastapi import status

from mink.core import return_codes
from tests.utils import HEADERS, call_route, logger


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


@pytest.mark.metadata
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
