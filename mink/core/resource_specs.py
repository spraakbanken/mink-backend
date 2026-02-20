"""Registry for resource type specifications."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from mink.core.resource import ResourceType


@dataclass(frozen=True)
class ResourceSpec:
    """Configuration for a resource type."""

    storage: Any
    job_cls: type[Any]
    allowed_extensions: tuple[str, ...]
    max_files: int
    config_filename: str
    process_names: tuple[str, ...]
    router_modules: tuple[str, ...] = ()
    queue_handlers: dict[str, Callable[[Any], None]] = field(default_factory=dict)
    process_running: Callable[[Any], bool] | None = None
    sync_processes: tuple[str, ...] = ()
    # Processes for which no output is expected
    no_output_processes: tuple[str, ...] = ()
    # Function to call when a job is done, for syncing results
    on_done_sync: Callable[[Any, bool], dict[str, Any] | None] | None = None
    # OpenAPI examples to inject into the schema for this resource type
    openapi_examples: dict[str, list[dict[str, Any]]] | None = None
    # Function to build resource-type-specific info dict for `/info` route
    info_builder: Callable[[], dict[str, Any]] | None = None


_SPEC_REGISTRY: dict[ResourceType, ResourceSpec] = {}
_SPECS_STATE = {"loading": False, "loaded": False}


def load_specs() -> None:
    """Import and register specs from configured modules."""
    if _SPECS_STATE["loaded"] or _SPECS_STATE["loading"]:
        return
    _SPECS_STATE["loading"] = True
    try:
        from importlib import import_module  # noqa: PLC0415

        from mink.core.config import settings  # noqa: PLC0415

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
    if resource_type in _SPEC_REGISTRY:
        raise ValueError(f"Resource spec already registered: {resource_type}")
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
    from importlib import import_module  # noqa: PLC0415

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
