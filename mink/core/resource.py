"""Classes defining resource objects."""

from enum import Enum
from typing import Optional

from mink.sparv import storage


class ResourceType(Enum):
    """Class for representing the different resource types."""

    corpus = "corpus"
    metadata = "metadata"

    def serialize(self):
        """Convert class data into a string."""
        return self.name


class Resource():
    """A resource item holding information about some important metadata."""

    def __init__(self,
                 id: str,
                 public_id: Optional[str] = "",
                 name: dict = {"swe": "", "eng": ""},
                 type: ResourceType = ResourceType.corpus,
                 source_files: Optional[list] = None
                ):
        self.id = id
        self.public_id = public_id or self.id
        self.name = name
        self.type = type
        self.source_files = source_files or []

    def __str__(self):
        return str(self.serialize())

    def serialize(self):
        """Convert class data into dict."""
        return {
            "id": self.id,
            "public_id": self.public_id,
            "name": self.name,
            "type": self.type,
            "source_files": self.source_files
            }

    def set_parent(self, parent):
        """Save reference to parent class."""
        self.parent = parent

    def set_resource_name(self, name: dict):
        """Set name for resource and save."""
        self.name = name
        self.parent.update()

    def set_source_files(self):
        source_dir = str(storage.get_source_dir(self.id))
        self.source_files = storage.list_contents(source_dir)
        self.parent.update()
