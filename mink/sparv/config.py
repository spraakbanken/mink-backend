"""Default configuration for Sparv module."""

from pydantic import Field
from pydantic_settings import BaseSettings


class SparvSettings(BaseSettings):
    """Settings for the Sparv module."""
    SPARV_ENABLED: bool = True  # Whether Sparv integration is enabled
    SPARV_RES_INFO: str = "The corpus resource type is used to store corpora that can be processed with Sparv."

    SPARV_SCHEMA_CACHE_LIFETIME: int = 60 * 60 * 24 * 10  # How long to cache Sparv schema info (in seconds)

    SPARV_RECOMMENDED_MIN_FILE_LENGTH: int = 1024 * 1024 * 1  # Recommended min size (bytes) for one corpus source file
    SPARV_RECOMMENDED_MAX_FILE_LENGTH: int = 1024 * 1024 * 5  # Recommended max size (bytes) for one corpus source file

    # Sparv server settings
    SPARV_HOST: str = ""  # Host where Sparv is run
    SPARV_USER: str = ""  # User for running Sparv
    SPARV_WORKERS: int = 1  # Number of available Sparv workers
    SPARV_DEFAULT_CORPORA_DIR: str = "~/mink-data/corpus/default"  # Dir for running listings like 'sparv run -l'
    SPARV_CORPORA_DIR: str = "mink-data/corpus"  # Dir where user corpora are stored and run, relative to home dir
    SPARV_ENVIRON: str = "SPARV_DATADIR=~/sparv-pipeline/data/"  # Environment variables to set when running Sparv
    SPARV_COMMAND: str = "~/sparv-pipeline/venv/bin/python -u -m sparv"  # Command for calling Sparv
    SPARV_RUN: str = "run --socket ~/sparv-pipeline/sparv.socket --json-log --log-to-file info"  # Sparv's 'run' command
    SPARV_INSTALL: str = "install --json-log --log-to-file info"  # Sparv's 'install' command
    SPARV_UNINSTALL: str = "uninstall --log-to-file info"  # Sparv's 'uninstall' command

    # Sparv data dirs and file naming
    SPARV_SOURCE_DIR: str = "source"  # Dir for storing corpus source files
    SPARV_EXPORT_DIR: str = "export"  # Dir for storing corpus exports
    SPARV_WORK_DIR: str = "sparv-workdir"  # Dir for Sparv work files
    SPARV_LOG_DIR: str = "logs"  # Dir for Sparv log files
    SPARV_CORPUS_CONFIG: str = "config.yaml"  # Name of the corpus config file
    SPARV_PLAIN_TEXT_FILE: str = "@text"  # Name of the plain text file in Sparv

    # File extensions for corpus input and the modules that handle them
    SPARV_IMPORTER_MODULES: dict[str, str] = Field(
        default_factory=lambda: {
            ".xml": "xml_import",
            ".txt": "text_import",
            ".docx": "docx_import",
            ".odt": "odt_import",
            ".pdf": "pdf_import",
        }
    )

    SPARV_NOHUP_FILE: str = "mink.out"  # File collecting Sparv output for a job
    SPARV_TMP_RUN_SCRIPT: str = "run_sparv.sh"  # Temporary Sparv run script created for every job

    # Default export formats to create if nothing is specified
    SPARV_DEFAULT_EXPORTS: list[str] = Field(
        default_factory=lambda: [
            "xml_export:pretty",
            "csv_export:csv",
            "stats_export:freq_list",
        ]
    )
    # Glob patterns for exports that will be excluded from listings and downloads
    SPARV_EXPORT_BLACKLIST: list[str] = Field(
        default_factory=lambda: [
            "cwb.*",
            "korp.*",
            "sbx_strix.*",
        ]
    )
    # Default Korp install targets to create
    SPARV_DEFAULT_KORP_INSTALLS: list[str] = Field(
        default_factory=lambda: [
            "korp:install_timespan",
            "korp:install_config",
            "korp:install_lemgrams",
        ]
    )
    # Default Korp uninstall targets
    SPARV_DEFAULT_KORP_UNINSTALLS: list[str] = Field(
        default_factory=lambda: [
            "cwb:uninstall_corpus",
            "korp:uninstall_timespan",
            "korp:uninstall_config",
            "korp:uninstall_lemgrams",
        ]
    )
    # Default Strix install targets to create
    SPARV_DEFAULT_STRIX_INSTALLS: list[str] = Field(
        default_factory=lambda: [
            "sbx_strix:install_config",
            "sbx_strix:install_corpus",
            "sbx_strix:install_xml",
        ]
    )
    # Default Strix uninstall targets
    SPARV_DEFAULT_STRIX_UNINSTALLS: list[str] = Field(
        default_factory=lambda: [
            "sbx_strix:uninstall_config",
            "sbx_strix:uninstall_corpus",
            "sbx_strix:uninstall_xml",
        ]
    )
    # Config options that users are not allowed to set
    SPARV_PROTECTED_CONFIG_OPTIONS: list[str] = Field(
        default_factory=lambda: [
            "cwb",
            "korp.config_dir",
            "korp.modes",
            "korp.mysql_dbname",
            "korp.protected",
            "korp.remote_host",
            "korp.wordpicture_table",
            "sbx_strix",
        ]
    )

    model_config = {
        "env_file": ".env",  # Load variables from a .env file if it exists
        "env_file_encoding": "utf-8",
        "extra": "ignore"  # Ignore extra environment variables from other modules (e.g. SPARV_*)
    }


sparv_settings = SparvSettings()
