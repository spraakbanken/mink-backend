"""Macros for MkDocs documentation."""

import os
from typing import Any


def define_env(env: Any) -> None:
    """Define environment variables for MkDocs."""
    env.variables["base_url"] = os.getenv("BASE_URL", "")
