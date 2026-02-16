"""Utility functions for Sparv module."""

import hashlib
from pathlib import Path
from typing import Any

import yaml

from mink.sparv.config import sparv_settings
from mink.sparv.storage import storage


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


def identical_file_exists(incoming_file_contents: bytes, existing_file: Path) -> bool:
    """Check if the incoming file is identical to the existing file.

    Args:
        incoming_file_contents: The incoming file contents.
        existing_file: Path to the existing file.

    Returns:
        True if the files are identical (in size and md5 hash), False otherwise.
    """
    if len(incoming_file_contents) == storage.get_size(existing_file):
        remote_file_contents = storage.get_file_contents(existing_file, as_bytes=True)
        remote_file_hash = hashlib.md5(remote_file_contents).hexdigest()  # type: ignore
        incoming_file_hash = hashlib.md5(incoming_file_contents).hexdigest()
        if incoming_file_hash == remote_file_hash:
            return True
    return False
