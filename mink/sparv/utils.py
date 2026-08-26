"""Utility functions for Sparv module."""

import json
from pathlib import Path
from typing import Any

import yaml

from mink.core import exceptions, return_codes
from mink.core.config import settings
from mink.sparv.config import sparv_settings
from mink.sparv.storage import storage


def require_compatible_config(config: str | bytes, source_files: list[dict]) -> None:
    """Raise an error if the importer module in the corpus config is incompatible with source files.

    Args:
        config: The corpus config.
        source_files: The source files.
    """
    if not source_files:
        return

    file_ext = Path(source_files[0]["name"]).suffix
    config_yaml = yaml.load(config, Loader=yaml.FullLoader)
    current_importer = config_yaml.get("import", {}).get("importer", "").split(":")[0] or None
    importer_dict = sparv_settings.SPARV_IMPORTER_MODULES

    # If no importer is specified xml is default
    if current_importer is None and file_ext == ".xml":
        return

    expected_importer = importer_dict.get(file_ext)

    if current_importer == expected_importer:
        return

    raise exceptions.MinkHTTPException(
        return_code=return_codes.INVALID_CONFIG,
        info="The importer in your config file is incompatible with your source files",
        current_importer=current_importer,
        expected_importer=expected_importer,
    )


def config_compatible(config: str | bytes, source_file: dict) -> tuple[bool, Any, Any]:
    """Check if the importer module in the corpus config is compatible with the source files.

    Args:
        config: The corpus config.
        source_file: The source file.

    Returns:
        A tuple containing a boolean indicating compatibility, the current importer, and the expected importer.
    """
    file_ext = Path(source_file["name"]).suffix
    config_yaml = yaml.load(config, Loader=yaml.FullLoader)
    current_importer = config_yaml.get("import", {}).get("importer", "").split(":")[0] or None
    importer_dict = sparv_settings.SPARV_IMPORTER_MODULES

    # If no importer is specified xml is default
    if current_importer is None and file_ext == ".xml":
        return True, None, None

    expected_importer = importer_dict.get(file_ext)
    if current_importer == expected_importer:
        return True, current_importer, expected_importer
    return False, current_importer, expected_importer


def standardize_config(config: str | bytes, resource_id: str) -> tuple[str, str]:
    """Set the correct corpus ID and remove the compression setting in the corpus config.

    Args:
        config: The corpus config.
        resource_id: The corpus ID.

    Returns:
        A tuple containing the standardized config and the corpus name.
    """
    config_yaml = yaml.load(config, Loader=yaml.FullLoader)

    # Set correct corpus ID
    if config_yaml.get("metadata", {}).get("id") != resource_id:
        if not config_yaml.get("metadata"):
            config_yaml["metadata"] = {}
        config_yaml["metadata"]["id"] = resource_id

    # Get corpus name
    name = config_yaml.get("metadata", {}).get("name", {})

    # Remove the compression setting in order to use the standard one given by the default config
    if config_yaml.get("sparv", {}).get("compression") is not None:
        config_yaml["sparv"].pop("compression")
        # Remove entire Sparv section if empty
        if not config_yaml.get("sparv", {}):
            config_yaml.pop("sparv")

    # Remove settings that a Mink user is not allowed to modify
    protected_options = sparv_settings.SPARV_PROTECTED_CONFIG_OPTIONS
    for value in protected_options:
        nested_options = value.split(".")
        current_level = config_yaml
        for option in nested_options[:-1]:
            current_level = current_level.get(option, {})
        current_level.pop(nested_options[-1], None)

    # Remove all install and uninstall targets (this is handled in the installation step instead)
    config_yaml.pop("install", None)
    config_yaml.pop("uninstall", None)

    # Add Korp settings
    korp = config_yaml.setdefault("korp", {})
    korp["protected"] = True
    korp.setdefault("context", ["1 sentence", "5 sentence"])
    korp.setdefault("within", ["sentence", "5 sentence"])

    # Make Strix corpora appear in correct mode
    strix = config_yaml.setdefault("sbx_strix", {})
    strix["modes"] = [{"name": "mink"}]
    # Add '<text>:misc.id as _id' to annotations for Strix' sake
    export = config_yaml.setdefault("export", {})
    export.setdefault("annotations", [])
    if "<text>:misc.id as _id" not in export["annotations"]:
        export["annotations"].append("<text>:misc.id as _id")

    return yaml.dump(config_yaml, sort_keys=False, allow_unicode=True), name


def file_ext_compatible(filename: Path, source_dir: Path) -> tuple[bool, str, str | None]:
    """Check if the file extension of filename is identical to the first file in source_dir.

    Args:
        filename: The filename to check.
        source_dir: The source directory.

    Returns:
        A tuple containing a boolean indicating compatibility, the current extension, and the existing extension.
    """
    existing_files = storage.list_contents(source_dir)
    current_ext = filename.suffix
    if not existing_files:
        return True, current_ext, None
    existing_ext = Path(existing_files[0].get("name")).suffix
    return current_ext == existing_ext, current_ext, existing_ext


def load_available_analyses() -> list[dict[str, Any]]:
    """Load and validate the available Sparv analyses from a JSON file."""
    # Load the instance analyses file, or the packaged default when it is absent.
    path = Path(sparv_settings.SPARV_AVAILABLE_ANALYSES_FILE).expanduser()
    if not path.is_absolute():
        path = Path(settings.INSTANCE_PATH) / path

    try:
        with path.open(encoding="utf-8") as file:
            analyses = json.load(file)
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON in available analyses file {path}: {error}") from error
    except OSError as error:
        raise ValueError(f"Could not read available analyses file {path}: {error}") from error

    if not isinstance(analyses, list):
        raise TypeError(f"Available analyses file {path} must contain a JSON list.")

    for analysis in analyses:
        if not isinstance(analysis, dict) or not isinstance(analysis.get("id"), str):
            raise TypeError(f"Each available analysis in {path} must have a string 'id'.")
        annotations = analysis.get("annotations")
        if not isinstance(annotations, list) or not all(isinstance(annotation, str) for annotation in annotations):
            raise TypeError(f"Each available analysis in {path} must have a list of string 'annotations'.")

    return analyses


def filter_available_analyses(
    analyses: list[dict[str, Any]], language: str | None, variety: str | None
) -> list[dict[str, Any]]:
    """Return analyses applicable to the requested language and variety."""
    if language is None and variety is None:
        return analyses

    # `mul`, `zxx`, and missing language metadata mean that an analysis applies to every language.
    applicable_codes = {language, "mul", "zxx"}
    return [
        analysis
        for analysis in analyses
        # Match the requested language, or include language-independent analyses.
        if (
            language is None
            or not analysis.get("languages")
            or any(language_info.get("code") in applicable_codes for language_info in analysis["languages"])
        )
        # Without a variety query, list only standard-language analyses. A requested variety also includes
        # analyses without a variety restriction.
        and (
            not analysis.get("language_varieties")
            if variety is None
            else variety in analysis.get("language_varieties", []) or not analysis.get("language_varieties")
        )
    ]
