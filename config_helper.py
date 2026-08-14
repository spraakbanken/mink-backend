"""Generate a config report for Mink settings."""

# ruff: file-ignore[print]

from __future__ import annotations

import argparse
import importlib
import json
import os
import pkgutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from pydantic import ValidationError
from pydantic_settings import BaseSettings
from rich import box
from rich.console import Console
from rich.table import Table

import mink
from mink.core.config import Settings as CoreSettings
from mink.core.config_utils import collect_defined_env_var_names, find_unused_env_vars, normalize_env_keys


@dataclass(frozen=True)
class ReportEntry:
    """Single settings entry in the report."""

    name: str
    value: Any
    source: str
    type_name: str
    default: Any


@dataclass(frozen=True)
class ExtraEntry:
    """Config value not defined in any settings class."""

    name: str
    value: Any
    source: str


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed argparse namespace.
    """
    parser = argparse.ArgumentParser(
        description="Print a config report for Mink settings (by default: settings from .env file)."
    )
    parser.add_argument("--env-file", default=".env", help="Path to env file (default: .env)")
    parser.add_argument("--format", choices=("table", "json"), default="table", help="Output format")
    parser.add_argument(
        "--include-defaults",
        action="store_true",
        help="Include default settings (and show source column)",
    )
    parser.add_argument(
        "--include-type",
        action="store_true",
        help="Include type column in the table output",
    )
    parser.add_argument(
        "--include-env-extras",
        action="store_true",
        help="Include extra config values from environment variables",
    )
    return parser.parse_args()


def _load_settings(env_file: str) -> list[tuple[str, BaseSettings]]:
    """Load settings instances for all modules."""
    settings_instances = []

    # Append core settings first (for better readability in the report), then load settings from configured modules
    settings_instances.append(("core", _instantiate_settings(CoreSettings, env_file)))

    for module_name in _discover_config_modules():
        module = importlib.import_module(module_name)
        for cls_name, settings_class in _find_settings_classes(module).items():
            settings_instances.append((cls_name, _instantiate_settings(settings_class, env_file)))
    return settings_instances


def _discover_config_modules() -> list[str]:
    """Discover config modules under the mink package.

    Returns:
        List of module names ending in ".config".
    """
    modules: list[str] = []
    for _, name, _ in pkgutil.iter_modules(mink.__path__, mink.__name__ + "."):
        mod_name = f"{name}.config"
        try:
            importlib.import_module(mod_name)
        except ModuleNotFoundError:
            continue
        if mod_name != "mink.core.config":
            modules.append(mod_name)
    return modules


def _find_settings_classes(module: Any) -> dict[str, type[BaseSettings]]:
    """Find BaseSettings subclasses in a module.

    Args:
        module: Imported module to inspect.

    Returns:
        Mapping of label to settings class.
    """
    classes: dict[str, type[BaseSettings]] = {}
    for name, obj in module.__dict__.items():
        if (
            isinstance(obj, type)
            and issubclass(obj, BaseSettings)
            and obj is not BaseSettings
            and obj is not CoreSettings
        ):
            label = f"{module.__name__}.{name}"
            classes[label] = obj
    return classes


def _instantiate_settings(settings_class: type[BaseSettings], env_file: str) -> BaseSettings:
    """Instantiate settings while allowing a custom env file.

    Args:
        settings_class: Settings class to instantiate.
        env_file: Path to the env file.

    Returns:
        Settings instance.
    """
    model_config = dict(getattr(settings_class, "model_config", {}))
    model_config["env_file"] = env_file
    model_config.setdefault("env_file_encoding", "utf-8")
    settings_name = f"{settings_class.__name__}WithEnv"
    settings_type = type(settings_name, (settings_class,), {"model_config": model_config})
    return settings_type()


def _source_for_field(name: str, env_file_keys: set[str], env_keys: set[str]) -> str:
    """Return the source label for a field.

    Args:
        name: Field name.
        env_file_keys: Keys present in the env file.
        env_keys: Keys present in the environment.

    Returns:
        Source label string.
    """
    name_key = name.lower()
    sources: list[str] = []
    if name_key in env_file_keys:
        sources.append(".env")
    if name_key in env_keys:
        sources.append("env")
    return "+".join(sources) if sources else "default"


def _collect_extra_entries(
    env_file_values: dict[str, str | None], known_keys: set[str], include_env: bool
) -> tuple[list[ExtraEntry], list[ExtraEntry]]:
    """Collect extra config values not defined in any settings class.

    Args:
        env_file_values: Parsed values from the env file.
        known_keys: Known settings field names.
        include_env: Whether to include extra env variables.

    Returns:
        Tuple of (env file extras, env extras).
    """
    # Reuse the same env-key comparison logic as the runtime warning.
    env_file_extras = [
        ExtraEntry(name=key, value=env_file_values.get(key), source=".env")
        for key in find_unused_env_vars(env_file_values, known_keys)
    ]
    env_extras: list[ExtraEntry] = []

    if include_env:
        env_extras.extend(
            ExtraEntry(name=key, value=os.environ.get(key, ""), source="env")
            for key in os.environ
            if key.lower() not in known_keys and key.lower() not in {e.name.lower() for e in env_file_extras}
        )

    return (
        sorted(env_file_extras, key=lambda entry: entry.name.lower()),
        sorted(env_extras, key=lambda entry: entry.name.lower()),
    )


def _field_default(field: Any) -> Any:
    """Get the default value for a Pydantic field.

    Args:
        field: Pydantic field info.

    Returns:
        The default value or "<required>" if no default exists.
    """
    default = field.get_default(call_default_factory=True)
    if default is None and field.is_required():
        return "<required>"
    return default


def build_report(
    settings: BaseSettings,
    env_file_keys: set[str],
    env_keys: set[str],
    include_defaults: bool,
    only_env_file: bool,
) -> list[ReportEntry]:
    """Build a report for a settings instance.

    Args:
        settings: Settings instance.
        env_file_keys: Keys present in the env file.
        env_keys: Keys present in the environment.
        include_defaults: Whether to include default values.
        only_env_file: Whether to include only settings from the env file.

    Returns:
        List of report entries.
    """
    entries: list[ReportEntry] = []
    values = settings.model_dump()
    model_fields = settings.__class__.model_fields
    for name, field in model_fields.items():
        source = _source_for_field(name, env_file_keys, env_keys)
        if only_env_file and name.lower() not in env_file_keys:
            continue
        if (not include_defaults) and source == "default":
            continue
        value = values.get(name)
        default = _field_default(field)
        entries.append(
            ReportEntry(
                name=name,
                value=value,
                source=source,
                type_name=str(field.annotation),
                default=default,
            )
        )
    return entries


def _stringify_entry(entry: ReportEntry) -> dict[str, str]:
    """Convert a report entry to strings for rendering.

    Args:
        entry: Report entry.

    Returns:
        Mapping of column name to string value.
    """
    return {
        "name": entry.name,
        "value": repr(entry.value),
        "source": entry.source,
        "type": entry.type_name,
        "default": repr(entry.default),
    }


def _stringify_extra(entry: ExtraEntry) -> dict[str, str]:
    """Convert an extra entry to strings for rendering.

    Args:
        entry: Extra entry.

    Returns:
        Mapping of column name to string value.
    """
    return {
        "name": entry.name,
        "value": repr(entry.value),
        "source": entry.source,
        "type": "",
        "default": "",
    }


def _compute_widths(rows: list[dict[str, str]], columns: list[str], limits: dict[str, int]) -> dict[str, int]:
    """Compute consistent column widths across tables.

    Args:
        rows: Row data for width calculation.
        columns: Columns to include.
        limits: Max width per column.

    Returns:
        Mapping of column name to width.
    """
    widths: dict[str, int] = {}
    for col in columns:
        max_len = max((len(row.get(col, "")) for row in rows), default=0)
        widths[col] = min(max(len(col), max_len), limits[col])
    return widths


def _build_table(columns: list[str], rows: list[dict[str, str]], widths: dict[str, int]) -> Table:
    """Build a Rich table.

    Args:
        columns: Column names.
        rows: Row data.
        widths: Column widths.

    Returns:
        Rich Table instance.
    """
    table = Table(show_header=True, box=box.SQUARE, border_style="grey30")
    for col in columns:
        overflow = "fold" if col in {"value", "default"} else "ellipsis"
        table.add_column(col, width=widths[col], overflow=overflow)
    if not rows:
        table.add_row(*(["(no entries)"] + [""] * (len(columns) - 1)))
        return table
    for row in rows:
        table.add_row(*(row.get(col, "") for col in columns))
    return table


def _display_module_name(label: str) -> str:
    """Get a short module name for display.

    Args:
        label: Module label from settings discovery.

    Returns:
        Short module name.
    """
    if label == "core":
        return "core"
    parts = label.split(".")
    if len(parts) >= 2 and parts[0] == "mink":  # ruff: ignore[magic-value-comparison]
        return parts[1]
    return label


def main() -> None:
    """Run the config report."""
    args = parse_args()
    env_file = Path(args.env_file)
    env_file_values = dotenv_values(env_file) if env_file.exists() else {}
    env_file_keys = normalize_env_keys(env_file_values.keys())
    env_keys = normalize_env_keys(os.environ.keys())

    json_out: dict[str, Any] = {}

    try:
        settings_instances = _load_settings(str(env_file))
    except ValidationError as exc:
        print("Config validation failed:")
        print(exc)
        raise SystemExit(1) from exc

    # Build the known key set from the instantiated settings classes so the report
    # and the startup warning use the same case-insensitive comparison rules.
    known_keys = collect_defined_env_var_names(settings.__class__ for _, settings in settings_instances)

    env_file_extras, env_extras = _collect_extra_entries(
        env_file_values,
        known_keys,
        args.include_env_extras,
    )

    include_defaults = args.include_defaults
    only_env_file = not include_defaults
    include_source = include_defaults

    settings_tables: list[tuple[str, list[dict[str, str]]]] = []
    for name, settings in settings_instances:
        entries = build_report(
            settings,
            env_file_keys,
            env_keys,
            include_defaults,
            only_env_file,
        )
        if args.format == "json":
            json_out[name] = [
                {
                    "name": e.name,
                    "value": e.value,
                    "type": e.type_name,
                    "default": e.default,
                }
                for e in entries
            ]
            if include_source:
                for item, entry in zip(json_out[name], entries, strict=False):
                    item["source"] = entry.source
        settings_tables.append((name, [_stringify_entry(e) for e in entries]))

    if args.format == "json":
        json_out["extra_env_file"] = [{"name": e.name, "value": e.value, "source": e.source} for e in env_file_extras]
        json_out["extra_env"] = [{"name": e.name, "value": e.value, "source": e.source} for e in env_extras]
        warnings: list[str] = []
        if env_file_extras:
            warnings.append(
                "Extra config values found in .env (not defined in any settings class). These have no effect."
            )
        if warnings:
            json_out["warnings"] = warnings
        print(json.dumps(json_out, indent=2, default=str))
    else:
        console = Console()
        columns_settings = ["name", "value", "default"]
        if include_source:
            columns_settings.insert(2, "source")
        if args.include_type:
            columns_settings.append("type")
        columns_all = ["name", "value", "source", "type", "default"]

        all_rows: list[dict[str, str]] = []
        for _, rows in settings_tables:
            all_rows.extend(rows)
        all_rows.extend([_stringify_extra(e) for e in env_file_extras])
        all_rows.extend([_stringify_extra(e) for e in env_extras])

        width_limits = {
            "name": 40,
            "value": 80,
            "source": 12,
            "type": 32,
            "default": 80,
        }
        widths = _compute_widths(all_rows, columns_all, width_limits)

        if env_file_extras:
            console.print(
                "WARNING: Extra config values found in .env (not defined in any settings class). These have no effect.",
                style="yellow",
            )
            console.print("\n  extra .env values", style="bold", markup=False)
            console.print(
                _build_table(
                    ["name", "value", "source"],
                    [_stringify_extra(e) for e in env_file_extras],
                    widths,
                )
            )
        if args.include_env_extras:
            console.print("\n  extra env values", style="bold", markup=False)
            console.print(
                _build_table(
                    ["name", "value", "source"],
                    [_stringify_extra(e) for e in env_extras],
                    widths,
                )
            )
        for label, rows in settings_tables:
            title = f"\n  {_display_module_name(label)} settings"
            console.print(title, style="bold", markup=False)
            console.print(_build_table(columns_settings, rows, widths))


if __name__ == "__main__":
    main()
