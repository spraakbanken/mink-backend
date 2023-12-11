"""Class defining user objects."""

from typing import Optional


class User():
    """A user item holding information about some user data and settings."""

    def __init__(self,
                 id: str,
                 name: str,
                 email: str,
                 ui_language: Optional[str] = None
                ):
        self.id = id
        self.name = name
        self.email = email
        self.ui_language = ui_language or "swe"

    def __str__(self):
        return str(self.serialize())

    def serialize(self):
        """Convert class data into dict."""
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "ui_language": self.ui_language
            }

    def set_parent(self, parent):
        """Save reference to parent class."""
        self.parent = parent
