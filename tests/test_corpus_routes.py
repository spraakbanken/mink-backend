"""Test metadata routes."""

import typing
from pathlib import Path

import pytest
from fastapi import status

from mink.core import return_codes
from tests.utils import HEADERS, call_route, check_resource_loop


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


@pytest.mark.corpus
def test_list_corpora(corpus: str) -> None:
    """Test listing corporaa."""
    routes = [
        ("GET", "/corpus/list"),
        ("GET", "/corpus/korp/list"),
    ]
    for method, path in routes:
        response = call_route(method, path, headers=HEADERS)
        json_data = response.json()
        assert isinstance(json_data.get("resources"), list), "Response should be a list of resources"
        if path == "/corpus/list":
            assert corpus in json_data.get("resources", []), f"Corpus {corpus} should be in the list of resources"


@pytest.fixture(scope="module")
def corpus_with_sources(corpus: str) -> str:
    """Ensure a corpus exists and sources are uploaded."""
    with (
        Path("tests/test_data/test_corpus_source.txt").open("rb") as f1,
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


@pytest.mark.corpus
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
    with Path("tests/test_data/test_corpus_config.yaml").open("rb") as f:
        call_route(
            "PUT",
            f"/corpus/config/upload/{corpus_with_sources}",
            status_code=status.HTTP_201_CREATED,
            headers=HEADERS,
            files=[("file", ("config.yaml", f))],
        )
    return corpus_with_sources


@pytest.mark.corpus
def test_download_corpus_config(corpus_with_sources_and_config: str) -> None:
    """Test download config route."""
    response = call_route("GET", f"/corpus/config/download/{corpus_with_sources_and_config}", headers=HEADERS)
    assert len(response.content) > 0, "Downloaded file should not be empty"


@pytest.fixture(scope="module")
def corpus_processed(corpus_with_sources_and_config: str) -> str:
    """Ensure a corpus is processed."""
    call_route("PUT", f"/corpus/job/run/{corpus_with_sources_and_config}", headers=HEADERS)
    json_data = check_resource_loop(resource_id=corpus_with_sources_and_config, process_name="sparv")
    sparv_status = json_data.get("job", {}).get("status", {}).get("sparv")
    assert sparv_status == "done", f"Corpus processing failed. Sparv status: {sparv_status}"
    return corpus_with_sources_and_config


@pytest.mark.corpus
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


@pytest.mark.corpus
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
