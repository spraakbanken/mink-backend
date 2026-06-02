"""Default configuration for Karp module."""

from pydantic import Field
from pydantic_settings import BaseSettings


class KarpSettings(BaseSettings):
    """Settings for the Karp module."""
    KARP_ENABLED: bool = True  # Whether Karp integration is enabled
    KARP_RES_INFO: str = "The lexicon resource type is used to store lexicons that can be processed with Karp."

    KARP_OUTPUT_CONTENTS_CACHE_LIFETIME: int = 60 * 60  # Cache time for per-lexicon output listings

    # Karp server settings
    KARP_HOST: str = ""  # Host where Karp is run
    KARP_USER: str = ""  # User for running Karp
    KARP_DATA_DIR: str = ""  # Dir where user lexicons are stored and run
    KARP_PARENT_CONFIG: str = ""  # Path to parent config file that is used for all Karp runs
    KARP_COMMAND: str = ""  # Command for calling Karp, e.g. "~/.local/bin/karp-pipeline"
    KARP_RUN: str = "run --json-output"  # Karp's 'run' command
    KARP_INSTALL: str = "install karps --json-output"  # Karp's 'install' command
    KARP_UNINSTALL: str = "uninstall karps --json-output"  # Karp's 'uninstall' command

    # Karp data dirs and file naming
    KARP_SOURCE_DIR: str = "source"  # Dir for storing source files
    KARP_OUTPUT_DIR: str = "output"  # Dir for storing karp output
    KARP_CONFIG: str = "config.yaml"  # Name of the config file

    # Glob patterns for output files that will be excluded from listings and downloads
    KARP_OUTPUT_BLACKLIST: list[str] = Field(
        default_factory=lambda: [
            "schema",
            "schema/*",
            "**/*.yaml",
            "generate_categorical_values",
            "generate_categorical_values/*",
        ]
    )

    KARP_NOHUP_FILE: str = "mink.out"  # File collecting Karp output for a job
    KARP_TMP_RUN_SCRIPT: str = "run_karp.sh"  # Temporary Karp run script created for every job

    model_config = {
        "env_file": ".env",  # Load variables from a .env file if it exists
        "env_file_encoding": "utf-8",
        "extra": "ignore"  # Ignore extra environment variables from other modules
    }


karp_settings = KarpSettings()
