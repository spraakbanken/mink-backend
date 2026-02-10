"""Utility functions for metadata module."""

import yaml


def standardize_yaml(metadata_yaml: str | bytes) -> tuple[str, str]:
    """Get resource name from metadata yaml and remove comments etc.

    Args:
        metadata_yaml: The metadata yaml.

    Returns:
        A tuple containing the standardized yaml and the resource name.
    """
    yaml_contents = yaml.load(metadata_yaml, Loader=yaml.FullLoader)

    # Get resource name
    name = yaml_contents.get("name", {})

    return yaml.dump(yaml_contents, sort_keys=False, allow_unicode=True), name
