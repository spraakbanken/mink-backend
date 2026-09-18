"""Test metadata routes."""

import typing

import pytest
from fastapi import status

from mink.core import return_codes
from mink.core.config import settings
from mink.sparv.demo import DEMO_ID_PATTERN
from tests.utils import call_route, check_resource_loop

INPUT_TEXT = "Detta är en mening."


@pytest.fixture(scope="module")
def demo_corpus() -> typing.Generator[str, None, None]:
    """Test creating a demo corpus."""
    response = call_route("POST", "/demo/corpus/run", status_code=status.HTTP_200_OK, query=f"text={INPUT_TEXT}")
    json_data = response.json()
    resource_id = json_data.get("resource", {}).get("id")
    assert resource_id is not None, "Resource ID should not be None"
    assert DEMO_ID_PATTERN.match(resource_id), f"Resource ID should match the demo ID pattern: {resource_id}"
    assert json_data.get("return_code") == return_codes.CHECKED_STATUS.code, f"Running demo corpus failed: {json_data}"
    yield resource_id

    # Teardown: remove resource after all tests are done
    call_route("POST", f"/demo/corpus/job/abort/{resource_id}", fail_ok=True)
    response = call_route(
        "DELETE", f"/demo/corpus/remove/{resource_id}", query=f"secret_key={settings.MINK_SECRET_KEY}"
    )
    json_data = response.json()
    assert json_data.get("return_code") == return_codes.REMOVED_RESOURCE.code, f"Corpus removal failed: {json_data}"


@pytest.mark.demo_corpus
def test_get_demo_corpus_input(demo_corpus: str) -> None:
    """Test getting demo corpus input text and config."""
    response = call_route("GET", f"/demo/corpus/input/get/{demo_corpus}")
    json_data = response.json()
    assert json_data.get("return_code") == return_codes.RETRIEVED_CONTENT.code, (
        f"Getting demo corpus input failed: {json_data}"
    )
    assert json_data.get("input_text") == INPUT_TEXT, (
        f"Input text does not match. Expected: {INPUT_TEXT}, Got: {json_data.get('input_text')}"
    )
    assert json_data.get("config"), "Config should not be empty"


@pytest.fixture(scope="module")
def demo_corpus_processed(demo_corpus: str) -> str:
    """Ensure a demo corpus is processed."""
    json_data = check_resource_loop(resource_id=demo_corpus, process_name="sparv", timeout=120, demo_corpus=True)
    sparv_status = json_data.get("job", {}).get("status", {}).get("sparv")
    assert sparv_status == "done", f"Corpus processing failed. Sparv status: {sparv_status}"
    return demo_corpus


@pytest.mark.demo_corpus
def test_get_demo_corpus_output(demo_corpus_processed: str) -> None:
    """Test getting demo corpus output."""
    response = call_route("GET", f"/demo/corpus/export/get/{demo_corpus_processed}")
    json_data = response.json()
    assert json_data.get("return_code") == return_codes.RETRIEVED_CONTENT.code, (
        f"Getting demo corpus output failed: {json_data}"
    )
    assert json_data.get("output"), "Output should not be empty"


@pytest.mark.demo_corpus
def test_get_demo_corpus_exports(demo_corpus_processed: str) -> None:
    """Test getting demo corpus exports routes."""
    response = call_route("GET", f"/demo/corpus/exports/list/{demo_corpus_processed}")
    json_data = response.json()
    assert isinstance(json_data.get("contents"), list), "Response should be a list of exports"
    assert len(json_data.get("contents")) > 0, "Response should contain at least one export"
    # Not specifying a file should return 422
    response = call_route("GET", f"/demo/corpus/exports/download/{demo_corpus_processed}", fail_ok=True)
    assert response.status_code == return_codes.VALIDATION_ERROR.status_code, (
        f"Download without specifying a file should return 422, got {response.status_code}"
    )
    # Requesting a file outside the allowed directories should return 404
    response = call_route(
        "GET", f"/demo/corpus/exports/download/{demo_corpus_processed}?file=something_forbidden/abc.xml", fail_ok=True
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND, (
        f"Download of a file outside the allowed directories should return 404, got {response.status_code}"
    )
    # Test downloading a valid export file
    response = call_route(
        "GET",
        f"/demo/corpus/exports/download/{demo_corpus_processed}?file=xml_export.pretty/input_export.xml",
    )
    assert response.headers.get("Content-Disposition") is not None, (
        "Download response should have Content-Disposition header"
    )
    assert response.headers.get("Content-Type") == "application/xml", (
        f"Download response should be an xml file, found: {response.headers.get('Content-Type')}"
    )
    assert len(response.content) > 0, "Downloaded exports file should not be empty"


@pytest.mark.demo_corpus
def test_remove_expired_demo_corpora() -> None:
    """Test removing expired demo corpora."""
    response = call_route(
        "DELETE",
        "/demo/corpus/remove-expired",
        query=f"secret_key={settings.MINK_SECRET_KEY}",
        status_code=status.HTTP_200_OK,
    )
    json_data = response.json()
    assert json_data.get("return_code") == return_codes.REMOVED_RESOURCES.code, (
        f"Removing expired demo corpora failed: {json_data}"
    )
    assert isinstance(json_data.get("removed_resources"), list), "Response should contain a list of removed resources"
