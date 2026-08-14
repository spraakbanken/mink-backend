"""Classes defining resource objects."""

from dataclasses import dataclass
from typing import Any

from mink.core import exceptions, utils


@dataclass(frozen=True, slots=True)
class ResourceType:
    """Value object representing a resource type."""

    value: str

    def __post_init__(self) -> None:
        """Validate the resource type name."""
        if not isinstance(self.value, str) or not self.value:
            raise exceptions.InvalidResourceTypeError(self.value)

    def __str__(self) -> str:
        """Return a string representation of the resource type."""
        return self.value


class Resource:
    """A resource item holding information about some important metadata."""

    def __init__(
        self,
        id: str,  # ruff: ignore[builtin-argument-shadowing]
        type: ResourceType,  # ruff: ignore[builtin-argument-shadowing]
        *,
        public_id: str | None = "",
        name: dict | None = None,
        source_files: list | None = None,
        sources_deleted: str = "",
        custom_config: bool = False,
    ) -> None:
        """Init resource by setting class variables.

        Args:
            id: The resource ID.
            public_id: The public ID of the resource.
            name: The name of the resource.
            type: The type of the resource.
            source_files: List of source files.
            sources_deleted: Timestamp of when sources were last deleted (used for knowing what to re-annotate).
            custom_config: Whether the current config was uploaded as a custom config.
        """
        self.id = id
        self.public_id = public_id or self.id
        self.name = name or {"swe": "", "eng": ""}
        if isinstance(type, ResourceType):
            resource_type = type
        elif isinstance(type, str):
            resource_type = ResourceType(type)
        else:
            raise exceptions.InvalidResourceTypeError(type)
        from mink.core.resource_specs import get_spec  # ruff: ignore[import-outside-top-level]

        try:
            get_spec(resource_type)
        except KeyError:
            raise exceptions.InvalidResourceTypeError(resource_type.value) from None
        self.type = resource_type
        self.source_files = source_files or []
        self.sources_deleted = sources_deleted or ""
        self.custom_config = custom_config

    def __str__(self) -> str:
        """Return a string representation of the resource instance."""
        return f"Resource(id={self.id}, type={self.type}, public_id={self.public_id})"

    def serialize(self, depth: int | None = None) -> dict:
        """Return a serialized dict representation of the resource instance."""
        raw = {
            "id": self.id,
            "public_id": self.public_id,
            "name": self.name,
            "type": self.type,
            "source_files": self.source_files,
            "sources_deleted": self.sources_deleted,
            "custom_config": self.custom_config,
        }
        return utils.serialize_obj(raw, depth=depth)

    def set_parent(self, parent: Any) -> None:
        """Save reference to parent class.

        Args:
            parent: The parent class.
        """
        self.parent = parent

    def set_resource_name(self, name: str) -> None:
        """Set name for resource and save.

        Args:
            name: The name of the resource.
        """
        self.name = name
        self.parent.update()

    def set_source_files(self, deleted_sources: bool = False) -> None:
        """Set 'source_files' list (and 'sources_deleted' timestamp) and save.

        Args:
            deleted_sources: Whether source files have been deleted.
        """
        from mink.core.resource_specs import get_spec  # ruff: ignore[import-outside-top-level]

        spec = get_spec(self.type)
        self.source_files = spec.storage.list_contents(spec.storage.get_source_dir(self.id))
        if deleted_sources:
            self.sources_deleted = utils.get_current_time()
        self.parent.update()

    def set_custom_config(self, custom_config: bool) -> None:
        """Set whether the resource currently has a custom config and save."""
        self.custom_config = custom_config
        self.parent.update()
