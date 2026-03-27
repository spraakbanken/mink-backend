"""Utility functions for the Karp module."""

import yaml

from mink.karp.config import karp_settings


def standardize_config(config: str | bytes, resource_id: str) -> tuple[str, str]:
    """Set the correct resource ID, path to parent config and link.

    Args:
        config: The lexicon config.
        resource_id: The resource ID.

    Returns:
        A tuple containing the standardized config and the resource name.
    """
    config_yaml = yaml.load(config, Loader=yaml.FullLoader)

    # Set correct resource ID
    if config_yaml.get("resource_id", {}) != resource_id:
        config_yaml["resource_id"] = resource_id

    # Set path to parent config
    config_yaml["parent_config"] = karp_settings.KARP_PARENT_CONFIG

    # Set link
    config_yaml.setdefault("karps", {}).setdefault("link", f"/library/lexicon/{resource_id}")

    # Get resource name
    name = config_yaml.get("name", {})

    return yaml.dump(config_yaml, sort_keys=False, allow_unicode=True), name
