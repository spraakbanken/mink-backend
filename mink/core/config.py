"""Default configuration for mink."""

from datetime import datetime
from pathlib import Path

from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Default app configuration."""
    ENV: str = "production"  # Environment type (production, development or testing)
    DEFAULT_RESOURCE_ID: str = ""  # Default resource ID to be used for testing in development mode

    # Mink settings
    MINK_URL: str = ""  # URL for mink API
    ROOT_PATH: str = ""  # Root path for the API, e.g. "/mink" if served from a subpath
    RESOURCE_PREFIX: str = "mink-"  # Prefix for resource IDs

    # Local files
    INSTANCE_PATH: str = str(Path(__file__).resolve().parent.parent.parent / "instance")  # Path to the instance dir
    TMP_DIR: str = str(Path(INSTANCE_PATH) / "tmp")  # Temporary file storage
    REGISTRY_DIR: str = str(Path(INSTANCE_PATH) / "registry")  # Directory for storing job files
    QUEUE_FILE: str = str(Path(INSTANCE_PATH) / "queue")  # File to store the queue priorities

    # Log settings
    LOG_LEVEL: str = "INFO"
    LOG_TO_FILE: bool = True
    LOG_DIR: str = str(Path(INSTANCE_PATH) / "logs")  # Directory for log files
    LOG_FILENAME: str = f"mink-{datetime.now().strftime('%Y-%m-%d')}.log"  # Name of the log file
    LOG_FORMAT: str = "%(asctime)-15s - %(name)s - %(levelname)s - %(message)s"
    LOG_FORMAT_UVICORN: str = "%(levelprefix)s %(name)s - %(message)s"  # Log format when running mink with Uvicorn
    LOG_DATEFORMAT: str = "%Y-%m-%d %H:%M:%S"

    # Cache settings
    CACHE_CLIENT: str = "127.0.0.1:11211"  # Server address or a path to a socket, e.g. "/var/run/memcached.sock"
    ADMIN_MODE_LIFETIME: int = 60 * 60 * 12  # How long the admin mode is active (in seconds)

    # File upload settings
    MAX_CONTENT_LENGTH: int = 1024 * 1024 * 100  # Max size (bytes) for one request
    MAX_FILE_LENGTH: int = 1024 * 1024 * 10  # Max size (bytes) for one corpus source file
    MAX_CORPUS_LENGTH: int = 1024 * 1024 * 500  # Max size (bytes) for one corpus
    RECOMMENDED_MIN_FILE_LENGTH: int = 1024 * 1024 * 1  # Recommended min size (bytes) for one corpus source file
    RECOMMENDED_MAX_FILE_LENGTH: int = 1024 * 1024 * 5  # Recommended max size (bytes) for one corpus source file

    # sb-auth settings
    SBAUTH_PUBKEY_FILE: str = "pubkey.pem"
    SBAUTH_URL: str = ""  # URL for sb-auth
    SBAUTH_API_KEY: str = ""  # API key for sb-auth
    SBAUTH_MINK_APP_RESOURCE: str = "mink-app"  # Name of the resource used to control admin grants
    SBAUTH_CACHE_LIFETIME: int = 10 * 60  # How long to cache fetched permissions (in seconds)
    SBAUTH_PERSONAL_API_KEY: str = ""  # Personal API key for sb-auth (used for testing purposes)

    # Sparv settings
    SPARV_SOURCE_DIR: str = "source"  # Dir for storing corpus source files
    SPARV_EXPORT_DIR: str = "export"  # Dir for storing corpus exports
    SPARV_WORK_DIR: str = "sparv-workdir"  # Dir for Sparv work files
    SPARV_CORPUS_CONFIG: str = "config.yaml"  # Name of the corpus config file
    SPARV_PLAIN_TEXT_FILE: str = "@text"  # Name of the plain text file in Sparv
    SPARV_IMPORTER_MODULES: dict = {  # File extensions for corpus input and the modules that handle them
        ".xml": "xml_import",
        ".txt": "text_import",
        ".docx": "docx_import",
        ".odt": "odt_import",
        ".pdf": "pdf_import",
    }

    # Sparv server settings
    SSH_KEY: str = "~/.ssh/id_rsa"  # Path to the SSH key for connecting to Sparv
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
    SPARV_DEFAULT_EXPORTS: list = [  # Default export formats to create if nothing is specified
        "xml_export:pretty",
        "csv_export:csv",
        "stats_export:freq_list",
    ]
    SPARV_EXPORT_BLACKLIST: list = [  # Glob patterns for exports that will be excluded from listings and downloads
        "cwb.*",
        "korp.*",
        "sbx_strix.*",
    ]
    SPARV_DEFAULT_KORP_INSTALLS: list = [  # Default Korp install targets to create
        "korp:install_timespan",
        "korp:install_config",
        "korp:install_lemgrams",
    ]
    SPARV_DEFAULT_KORP_UNINSTALLS: list = [  # Default Korp uninstall targets
        "cwb:uninstall_corpus",
        "korp:uninstall_timespan",
        "korp:uninstall_config",
        "korp:uninstall_lemgrams",
    ]
    SPARV_DEFAULT_STRIX_INSTALLS: list = [  # Default Strix install targets to create
        "sbx_strix:install_config",
        "sbx_strix:install_corpus",
        "sbx_strix:install_xml",
    ]
    SPARV_DEFAULT_STRIX_UNINSTALLS: list = [  # Default Strix uninstall targets
        "sbx_strix:uninstall_config",
        "sbx_strix:uninstall_corpus",
        "sbx_strix:uninstall_xml",
    ]
    SPARV_NOHUP_FILE: str = "mink.out"  # File collecting Sparv output for a job
    SPARV_TMP_RUN_SCRIPT: str = "run_sparv.sh"  # Temporary Sparv run script created for every job

    # Settings for metadata upload
    METADATA_HOST: str = ""
    METADATA_USER: str = ""
    METADATA_DIR: str = "mink-data/metadata"  # Dir where metadata resources are stored, relative to the user's home dir
    METADATA_ID_AVAILABLE_URL: str = ""
    METADATA_SOURCE_DIR: str = "source"  # Dir for storing resource files belonging to a metadata resource
    METADATA_ORG_PREFIXES: dict = {}  # Mapping from user IDs to organisation prefixes

    # Settings for queue manager
    CHECK_QUEUE_FREQUENCY: int = 20  # How often the queue will be checked for new jobs (in seconds)
    MINK_SECRET_KEY: str = ""
    HEALTHCHECKS_URL: str = ""
    PING_FREQUENCY: int = 60  # Frequency (in minutes) for how often healthchecks should be pinged

    # Settings for tracking to Matomo
    TRACKING_MATOMO_URL: str = ""
    TRACKING_MATOMO_IDSITE: int = 0
    TRACKING_MATOMO_AUTH_TOKEN: str = ""
    TRACKING_MATOMO_HTTP_TIMEOUT: int = 5

    model_config = ConfigDict(
        env_file=".env",  # Load variables from a .env file if it exists
        env_file_encoding="utf-8"
    )


settings = Settings()
