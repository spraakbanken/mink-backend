"""Tests for non-resource specific routes."""

from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from mink.cache.memcached import cache
from mink.core import info as info_module
from mink.core import registry, return_codes
from mink.core.config import settings
from mink.core.resource import Resource
from mink.core.status import Status
from mink.core.user import User
from mink.sparv.spec import CORPUS, ProcessName
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


@pytest.fixture
def create_queue_job() -> Iterator[Callable[..., info_module.Info]]:
    """Create queued test jobs and clean them up after the test."""
    created_jobs: list[info_module.Info] = []

    def _create(*, job_status: Status, started: str = "", queued: str = "") -> info_module.Info:
        cache.initialize(settings.CACHE_CLIENT)
        registry.initialize_if_needed()

        resource_id = f"{settings.RESOURCE_PREFIX}{uuid4().hex[:10]}"
        info_obj = info_module.Info(
            resource_id,
            resource=Resource(resource_id, type=CORPUS),
            owner=User(id="pytest-user", name="Pytest User", email="pytest@example.com"),
        )
        info_obj.create()
        created_jobs.append(info_obj)

        job = registry.add_to_queue(info_obj.job)
        job.set_status(job_status, ProcessName.sparv)
        if queued:
            job.set_attribute("queued", queued)
        if started:
            job.set_attribute("started", started)
        return info_obj

    yield _create

    for info_obj in reversed(created_jobs):
        info_obj.remove(abort_job=True)


@pytest.mark.general
def test_queue_health_healthy(create_queue_job: Callable[..., info_module.Info]) -> None:
    """Test queue health route for a healthy running job."""
    started = (datetime.now().astimezone() - timedelta(minutes=5)).isoformat(timespec="seconds")
    info_obj = create_queue_job(job_status=Status.running, started=started)
    response = call_route(
        "GET",
        "/queue/health",
        query=f"secret_key={settings.MINK_SECRET_KEY}",
    )
    json_data = response.json()
    assert json_data.get("return_code") == return_codes.QUEUE_HEALTHY.code
    assert json_data.get("healthy") is True
    assert json_data.get("running_jobs") >= 1
    assert json_data.get("waiting_jobs") == 0
    assert json_data.get("oldest_running_seconds", 0) >= 240  # noqa: PLR2004
    assert any(job.get("resource_id") == info_obj.id for job in json_data.get("queue_jobs", []))


@pytest.mark.general
def test_queue_health_degraded_for_stale_waiting_job(create_queue_job: Callable[..., info_module.Info]) -> None:
    """Test queue health route for a stale waiting job."""
    queued = (
        datetime.now().astimezone() - timedelta(seconds=settings.QUEUE_HEALTH_WARNING_SECONDS + 120)
    ).isoformat(timespec="seconds")
    info_obj = create_queue_job(job_status=Status.waiting, queued=queued)
    response = call_route(
        "GET",
        "/queue/health",
        query=f"secret_key={settings.MINK_SECRET_KEY}",
        status_code=return_codes.QUEUE_DEGRADED.status_code,
    )
    json_data = response.json()
    assert json_data.get("return_code") == return_codes.QUEUE_DEGRADED.code
    assert json_data.get("healthy") is False
    assert json_data.get("running_jobs") == 0
    assert json_data.get("waiting_jobs") >= 1
    assert json_data.get("oldest_waiting_seconds", 0) >= settings.QUEUE_HEALTH_WARNING_SECONDS
    assert json_data.get("warnings")
    assert any("queued for" in warning for warning in json_data["warnings"])
    assert any(job.get("resource_id") == info_obj.id for job in json_data.get("queue_jobs", []))
