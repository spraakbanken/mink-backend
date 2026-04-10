"""Helpers for working with Mink settings classes and environment variables."""

from __future__ import annotations

import importlib
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from dotenv import dotenv_values
from pydantic_settings import BaseSettings

from mink.core.config import settings
from mink.core.logging import logger


def discover_settings_classes(
    main_settings_class: type[BaseSettings], config_modules: Sequence[str]
) -> tuple[list[type[BaseSettings]], list[tuple[str, Exception]]]:
    """Collect the main settings class together with configured module settings classes.

    Args:
        main_settings_class: The primary application settings class.
        config_modules: Module names that may contain additional settings classes.

    Returns:
        A tuple containing the discovered settings classes and any import errors.
    """
    classes = [main_settings_class]
    seen = {main_settings_class}
    import_errors: list[tuple[str, Exception]] = []

    for module_name in config_modules:
        try:
            module = importlib.import_module(module_name)
            for attr in module.__dict__.values():
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BaseSettings)
                    and attr is not BaseSettings
                    and attr not in seen
                ):
                    classes.append(attr)
                    seen.add(attr)
        except Exception as exc:
            import_errors.append((module_name, exc))

    return classes, import_errors


def normalize_env_keys(keys: Iterable[str]) -> set[str]:
    """Normalize env keys for case-insensitive comparisons."""
    return {key.lower() for key in keys if key}


def collect_defined_env_var_names(settings_classes: Iterable[type[BaseSettings]]) -> set[str]:
    """Collect normalized env-variable names defined by one or more settings classes."""
    defined_vars: set[str] = set()
    for settings_class in settings_classes:
        defined_vars.update(normalize_env_keys(settings_class.model_fields.keys()))
    return defined_vars


def find_unused_env_vars(env_values: Mapping[str, str | None], defined_var_names: set[str]) -> list[str]:
    """Find env variables that are not defined by any known settings class.

    Args:
        env_values: Mapping of env-variable names to values.
        defined_var_names: Normalized env-variable names defined by settings classes.

    Returns:
        Sorted list of original env-variable names that are not recognized.
    """
    # Keep the original key for output, but normalize keys for comparison.
    normalized_to_original = {key.lower(): key for key in env_values if key}
    return sorted(
        original_name
        for normalized_name, original_name in normalized_to_original.items()
        if normalized_name not in defined_var_names
    )


def check_unused_env_vars() -> None:
    """Check for .env variables that are not used by any config class and log warnings."""
    model_config = type(settings).model_config
    env_file = model_config.get("env_file")
    if not env_file:
        return

    env_vars: dict[str, str | None] = {}

    # env_file can be a string or a list of strings; handle both cases
    env_files = env_file if isinstance(env_file, (list, tuple)) else [env_file]
    for env_path_value in env_files:
        env_path = Path(str(env_path_value)).expanduser()
        if not env_path.is_absolute():
            env_path = Path.cwd() / env_path
        if not env_path.is_file():
            continue

        # Parse the .env file and add the variable names to env_vars
        env_values = dotenv_values(dotenv_path=env_path, encoding=model_config.get("env_file_encoding", "utf-8"))
        env_vars.update({key: value for key, value in env_values.items() if key})

    if not env_vars:
        return

    # Collect known settings classes before comparing env vars to defined config fields.
    settings_classes, import_errors = discover_settings_classes(type(settings), settings.CONFIG_MODULES)
    for module_name, error in import_errors:
        logger.warning("Could not import config module %s: %s", module_name, error)

    # Add fields from the main settings class and discovered config modules.
    defined_vars = collect_defined_env_var_names(settings_classes)

    # Compare env vars with defined config fields and log any unused vars as warnings
    unused_vars = find_unused_env_vars(env_vars, defined_vars)
    if unused_vars:
        logger.warning(
            "Found %d environment variable(s) not defined in any config: %s",
            len(unused_vars),
            ", ".join(unused_vars),
        )
