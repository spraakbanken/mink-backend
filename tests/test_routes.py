"""Tests for non-resource specific routes."""

import pytest

from mink.core import return_codes
from tests.utils import HEADERS, call_route, logger

from .conftest import ROUTE_INFO


@pytest.mark.general
def test_untagged_routes() -> None:
    """Test that all routes are tagged."""
    logger.debug("Found %d routes", ROUTE_INFO.routes)
    assert len(ROUTE_INFO.untagged_routes) == 0, (
        f"Found {len(ROUTE_INFO.untagged_routes)} untagged routes: {ROUTE_INFO.untagged_routes}"
    )


@pytest.mark.general
def test_documentation_route() -> None:
    """Test documentation routes."""
    for method, path in ROUTE_INFO.tag_dict.get("Documentation", []):
        call_route(method, path)


@pytest.mark.general
@pytest.mark.admin
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


@pytest.mark.general
def test_list_resources() -> None:
    """Test listing all resources regardless of type."""
    response = call_route("GET", "/resource/list", headers=HEADERS)
    json_data = response.json()
    assert isinstance(json_data.get("resources"), list), "Response should be a list of resources"


@pytest.mark.general
def test_list_resource_statuses() -> None:
    """Test listing all resource statuses."""
    response = call_route("GET", "/resource/status/list", headers=HEADERS)
    json_data = response.json()
    assert isinstance(json_data.get("resources"), list), "Response should be a list of resources"
