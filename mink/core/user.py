"""Class defining user objects."""

from typing import Any


class User:
    """A user item holding information about some user data and settings."""

    def __init__(
        self,
        id: str,  # noqa: A002
        name: str,
        email: str,
        ui_language: str | None = None,
    ) -> None:
        """Init user by setting class variables.

        Args:
            id: The user ID.
            name: The user's name.
            email: The user's email.
            ui_language: The user's UI language.
        """
        self.id = id
        self.name = name
        self.email = email
        self.ui_language = ui_language or "swe"

    def __str__(self) -> str:
        """Return a string representation of the serialized object.

        Returns:
            str: The serialized object as a string.
        """
        return str(self.serialize())

    def serialize(self) -> dict:
        """Convert class data into dict.

        Returns:
            The serialized user as a dictionary.
        """
        return {"id": self.id, "name": self.name, "email": self.email, "ui_language": self.ui_language}

    def set_parent(self, parent: Any) -> None:
        """Save reference to parent class.

        Args:
            parent: The parent class.
        """
        self.parent = parent
