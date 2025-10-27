"""Classes defining resource objects."""

from enum import Enum
from typing import Any

from mink.core import exceptions, utils
from mink.sparv import storage


class ResourceType(Enum):
    """Class for representing the different resource types."""

    corpus = "corpus"
    metadata = "metadata"

    def serialize(self) -> str:
        """Convert class data into a string.

        Returns:
            The serialized resource type as a string.
        """
        return self.name


class Resource:
    """A resource item holding information about some important metadata."""

    def __init__(
        self,
        id: str,  # noqa: A002
        public_id: str | None = "",
        name: dict | None = None,
        type: ResourceType | str = ResourceType.corpus,  # noqa: A002
        source_files: list | None = None,
        sources_deleted: str = "",
    ) -> None:
        """Init resource by setting class variables.

        Args:
            id: The resource ID.
            public_id: The public ID of the resource.
            name: The name of the resource.
            type: The type of the resource.
            source_files: List of source files.
            sources_deleted: Timestamp of when sources were last deleted (used for knowing what to re-annotate).
        """
        self.id = id
        self.public_id = public_id or self.id
        self.name = name or {"swe": "", "eng": ""}
        if isinstance(type, ResourceType):
            self.type = type
        elif isinstance(type, str):
            try:
                self.type = ResourceType[type]
            except KeyError:
                raise exceptions.InvalidResourceTypeError(type) from None
        else:
            raise exceptions.InvalidResourceTypeError(type)
        self.source_files = source_files or []
        self.sources_deleted = sources_deleted or ""

    def __str__(self) -> str:
        """Return a string representation of the object by serializing it.

        Returns:
            str: The serialized representation of the object as a string.
        """
        return str(self.serialize())

    def serialize(self) -> dict:
        """Convert class data into dict.

        Returns:
            The serialized resource as a dictionary.
        """
        return {
            "id": self.id,
            "public_id": self.public_id,
            "name": self.name,
            "type": self.type,
            "source_files": self.source_files,
            "sources_deleted": self.sources_deleted,
        }

    def set_parent(self, parent: Any) -> None:
        """Save reference to parent class.

        Args:
            parent: The parent class.
        """
        self.parent = parent

    def set_resource_name(self, name: dict) -> None:
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
        self.source_files = storage.list_contents(storage.get_source_dir(self.id))
        if deleted_sources:
            self.sources_deleted = utils.get_current_time()
        self.parent.update()
