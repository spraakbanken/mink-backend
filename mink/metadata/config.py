"""Default configuration for metadata module."""

from pydantic import Field
from pydantic_settings import BaseSettings


class MetadataSettings(BaseSettings):
    """Settings for metadata upload."""
    METADATA_RES_INFO: str = (
        "This resource type is used to store metadata yaml files to be used for the Språkbanken resource page."
    )

    METADATA_HOST: str = ""
    METADATA_USER: str = ""

    # Dir where metadata resources are stored, relative to the user's home dir
    METADATA_DIR: str = "mink-data/metadata"

    # URL for checking if a metadata ID is available (i.e. not taken by another resource)
    METADATA_ID_AVAILABLE_URL: str = ""

    # Dir for storing resource files belonging to a metadata resource
    METADATA_SOURCE_DIR: str = "source"

    # Mapping from user IDs to organisation prefixes
    METADATA_ORG_PREFIXES: dict[str, str] = Field(default_factory=dict)

    model_config = {
        "env_file": ".env",  # Load variables from a .env file if it exists
        "env_file_encoding": "utf-8",
        "extra": "ignore"  # Ignore extra environment variables from other modules (e.g. SPARV_*)
    }


metadata_settings = MetadataSettings()
