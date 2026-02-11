"""Registry for resource type specifications."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
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
    info_builder: Callable[[], dict[str, Any]] | None = None


_SPEC_REGISTRY: dict[ResourceType, ResourceSpec] = {}


def register_spec(resource_type: ResourceType, spec: ResourceSpec) -> None:
    """Register a spec for a resource type."""
    if resource_type in _SPEC_REGISTRY:
        raise ValueError(f"Resource spec already registered: {resource_type}")
    _SPEC_REGISTRY[resource_type] = spec


def get_spec(resource_type: ResourceType) -> ResourceSpec:
    """Get a registered spec for a resource type."""
    return _SPEC_REGISTRY[resource_type]


def get_all_specs() -> dict[ResourceType, ResourceSpec]:
    """Get all registered resource specs."""
    return _SPEC_REGISTRY
