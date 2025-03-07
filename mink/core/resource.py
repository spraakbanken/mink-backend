"""Classes defining resource objects."""

from enum import Enum
from typing import Any, Optional

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
        public_id: Optional[str] = "",
        name: Optional[dict] = None,
        type: ResourceType = ResourceType.corpus,  # noqa: A002
        source_files: Optional[list] = None,
    ) -> None:
        """Init resource by setting class variables.

        Args:
            id: The resource ID.
            public_id: The public ID of the resource.
            name: The name of the resource.
            type: The type of the resource.
            source_files: List of source files.
        """
        self.id = id
        self.public_id = public_id or self.id
        self.name = name or {"swe": "", "eng": ""}
        self.type = type
        self.source_files = source_files or []

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

    def set_source_files(self) -> None:
        """Set source files and save."""
        source_dir = str(storage.get_source_dir(self.id))
        self.source_files = storage.list_contents(source_dir)
        self.parent.update()
