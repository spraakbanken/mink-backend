"""Test lexicon routes."""

import typing
from pathlib import Path

import pytest
from fastapi import status

from mink.core import return_codes
from tests.utils import HEADERS, call_route


@pytest.fixture(scope="module")
def lexicon() -> typing.Generator[str, None, None]:
    """Test creating a lexicon."""
    response = call_route("POST", "/lexicon/create", status_code=status.HTTP_201_CREATED, headers=HEADERS)
    json_data = response.json()
    assert json_data.get("return_code") == return_codes.CREATED_RESOURCE.code, f"Lexicon creation failed: {json_data}"
    resource_id = json_data.get("resource_id")
    assert json_data.get("resource_id") is not None, "Resource ID should not be None"
    yield resource_id

    # Teardown: remove resource after all tests are done
    # call_route("POST", f"/lexicon/job/abort/{resource_id}", headers=HEADERS, fail_ok=True)
    response = call_route("DELETE", f"/lexicon/remove/{resource_id}", headers=HEADERS)
    json_data = response.json()
    assert json_data.get("return_code") == return_codes.REMOVED_RESOURCE.code, f"Lexicon removal failed: {json_data}"


@pytest.mark.lexicon
def test_list_lexicons(lexicon: str) -> None:
    """Test listing lexicons."""
    routes = [
        ("GET", "/lexicon/list"),
        # ("GET", "/lexicon/karp/list"),
    ]
    for method, path in routes:
        response = call_route(method, path, headers=HEADERS)
        json_data = response.json()
        assert isinstance(json_data.get("resources"), list), "Response should be a list of resources"
        if path == "/lexicon/list":
            assert lexicon in json_data.get("resources", []), f"Lexicon {lexicon} should be in the list of lexicons"


@pytest.fixture(scope="module")
def lexicon_with_data(lexicon: str) -> str:
    """Ensure a lexicon exists and a data file is uploaded."""
    with (
        Path("tests/test_data/test_lexicon_data.jsonl").open("rb") as f1,
    ):
        call_route(
            "PUT",
            f"/lexicon/sources/upload/{lexicon}",
            status_code=status.HTTP_201_CREATED,
            headers=HEADERS,
            files=[
                ("file", ("test_lexicon.jsonl", f1)),
            ],
        )
    return lexicon


@pytest.mark.lexicon
def test_manage_lexicon_sources(lexicon_with_data: str) -> None:
    """Test manage lexicon sources routes."""
    routes = [
        ("GET", f"/lexicon/sources/list/{lexicon_with_data}", None),
        ("GET", f"/lexicon/sources/download/{lexicon_with_data}", None),
        ("DELETE", f"/lexicon/sources/remove/{lexicon_with_data}", "remove=test_lexicon.jsonl"),
    ]
    for method, path, query in routes:
        response = call_route(method, path, query=query, headers=HEADERS)
        if path.startswith("/lexicon/sources/list/"):
            json_data = response.json()
            assert isinstance(json_data.get("contents"), list), "Response should be a list of sources"
            assert len(json_data.get("contents", [])) > 0, "There should be at least one source file in the list"
        elif path.startswith("/lexicon/sources/download/"):
            assert response.headers.get("Content-Disposition") is not None, (
                "Download response should have Content-Disposition header"
            )
            assert len(response.content) > 0, "Downloaded file should not be empty"
        elif path.startswith("/lexicon/sources/remove/"):
            json_data = response.json()
            assert json_data.get("return_code") == return_codes.REMOVED_CONTENT.code, (
                f"Source removal failed: {json_data}"
            )


@pytest.fixture(scope="module")
def lexicon_with_data_and_config(lexicon: str) -> str:
    """Ensure a lexicon exists and data and config are uploaded."""
    with (
        Path("tests/test_data/test_lexicon_data.jsonl").open("rb") as f1,
    ):
        call_route(
            "PUT",
            f"/lexicon/sources/upload/{lexicon}",
            status_code=status.HTTP_201_CREATED,
            headers=HEADERS,
            files=[
                ("file", ("test_lexicon.jsonl", f1)),
            ],
        )

    with Path("tests/test_data/test_lexicon_config.yaml").open("rb") as f:
        call_route(
            "PUT",
            f"/lexicon/config/upload/{lexicon}",
            status_code=status.HTTP_201_CREATED,
            headers=HEADERS,
            files=[("file", ("config.yaml", f))],
        )
    return lexicon


@pytest.mark.lexicon
def test_download_lexicon_config(lexicon_with_data_and_config: str) -> None:
    """Test download config route."""
    response = call_route("GET", f"/lexicon/config/download/{lexicon_with_data_and_config}", headers=HEADERS)
    assert len(response.content) > 0, "Downloaded file should not be empty"
