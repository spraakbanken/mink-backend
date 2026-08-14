"""Registry for resource type specifications."""

# ruff: file-ignore[import-outside-top-level], avoids circular import

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from mink.core.resource import ResourceType


@dataclass(frozen=True)
class ResourceSpec:
    """Configuration for a resource type."""

    storage: Any
    """Storage class for this resource type, must implement the BaseStorage interface"""

    job_cls: type[Any]
    """Job class for this resource type, must implement the BaseJob interface"""

    allowed_extensions: tuple[str, ...]
    """File extensions allowed for upload, e.g. ('.txt', '.xml')"""

    config_filename: str
    """Name of the config file for this resource type"""

    process_names: tuple[str, ...]
    """Process names for this resource type"""

    router_modules: tuple[str, ...] = ()
    """Modules to import routers from for this resource type"""

    queue_handlers: dict[str, Callable[[Any], None]] = field(default_factory=dict)
    """Functions to call to advance the job queue for this resource type, keyed by process name"""

    process_running: Callable[[Any], bool] | None = None
    """Function to check if a process is still running (e.g. for /queue/advance)"""

    sync_processes: tuple[str, ...] = ()
    """Processes which handle file syncing"""

    no_output_processes: tuple[str, ...] = ()
    """Processes for which no output is expected"""

    on_done_sync: Callable[[Any, bool], dict[str, Any] | None] | None = None
    """Function to call when a job is done, for syncing results"""

    startup_check: Callable[[], None] | None = None
    """Startup check hook (e.g. validate module-specific settings)"""

    openapi_examples: dict[str, list[dict[str, Any]]] | None = None
    """OpenAPI examples to inject into the schema for this resource type"""

    info_builder: Callable[[], dict[str, Any]] | None = None
    """Function to build resource-type-specific info dict for `/info` route"""

    sbauth_resource_type: str = ""
    """SB Auth scope key for this resource type"""


_SPEC_REGISTRY: dict[ResourceType, ResourceSpec] = {}
_SPECS_STATE = {"loading": False, "loaded": False}


def load_specs() -> None:
    """Import and register specs from configured modules."""
    if _SPECS_STATE["loaded"] or _SPECS_STATE["loading"]:
        return
    _SPECS_STATE["loading"] = True
    try:
        from importlib import import_module

        from mink.core.config import settings

        # Find all modules containing resource specs and call their register function
        for module in settings.SPEC_MODULES:
            mod = import_module(module)
            register = getattr(mod, "register", None)
            if callable(register):
                register()
        _SPECS_STATE["loaded"] = True
    finally:
        _SPECS_STATE["loading"] = False


def register_spec(resource_type: ResourceType, spec: ResourceSpec) -> None:
    """Register a spec for a resource type."""
    from mink.core.config import settings

    # Check if spec for this resource type is already registered
    if resource_type in _SPEC_REGISTRY:
        raise ValueError(f"Resource spec already registered: {resource_type}")
    # Check if sbauth_resource_type is valid (i.e. defined in settings.SBAUTH_RESOURCE_TYPES)
    if spec.sbauth_resource_type not in settings.SBAUTH_RESOURCE_TYPES:
        raise ValueError(
            f"Invalid sbauth_resource_type '{spec.sbauth_resource_type}' "
            f"for {resource_type}. Allowed: {settings.SBAUTH_RESOURCE_TYPES}"
        )

    _SPEC_REGISTRY[resource_type] = spec


def get_spec(resource_type: ResourceType) -> ResourceSpec:
    """Get a registered spec for a resource type."""
    if resource_type not in _SPEC_REGISTRY:
        load_specs()
    return _SPEC_REGISTRY[resource_type]


def get_all_specs() -> dict[ResourceType, ResourceSpec]:
    """Get all registered resource specs."""
    load_specs()
    return _SPEC_REGISTRY


def get_resource_routers() -> list[Any]:
    """Load and return APIRouter instances from registered resource specs."""
    load_specs()
    from importlib import import_module

    routers: list[Any] = []
    seen_modules: set[str] = set()
    for spec in _SPEC_REGISTRY.values():
        for module_path in spec.router_modules:
            if module_path in seen_modules:
                continue
            seen_modules.add(module_path)
            mod = import_module(module_path)
            router = getattr(mod, "router", None)
            if router is None:
                raise ValueError(f"Router not found in module '{module_path}'")
            routers.append(router)
    return routers


def run_startup_checks() -> None:
    """Run startup checks for all registered resource specs."""
    load_specs()
    for spec in _SPEC_REGISTRY.values():
        if spec.startup_check:
            spec.startup_check()
