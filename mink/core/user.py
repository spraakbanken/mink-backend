"""Class defining user objects."""

from typing import Any

from mink.core import utils


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
        """Return a string representation of the user instance."""
        return f"User(id={self.id}, name={self.name}, email={self.email})"

    def serialize(self, depth: int | None = None) -> dict:
        """Return a serialized dict representation of the user instance."""
        raw = {"id": self.id, "name": self.name, "email": self.email, "ui_language": self.ui_language}
        return utils.serialize_obj(raw, depth=depth)

    def set_parent(self, parent: Any) -> None:
        """Save reference to parent class.

        Args:
            parent: The parent class.
        """
        self.parent = parent
