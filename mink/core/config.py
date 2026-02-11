"""Default configuration for mink."""

from datetime import datetime
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Default app configuration."""
    ENV: str = "production"  # Environment type (production, development or testing)
    DEFAULT_RESOURCE_ID: str = ""  # Default resource ID to be used for testing in development mode

    # Mink settings
    MINK_URL: str = ""  # URL for mink API
    ROOT_PATH: str = ""  # Root path for the API, e.g. "/mink" if served from a subpath
    RESOURCE_PREFIX: str = "mink-"  # Prefix for resource IDs

    # Modules that register resource specs
    SPEC_MODULES: list[str] = Field(
        default_factory=lambda: ["mink.sparv.spec", "mink.metadata.spec"]
    )

    # CORS settings
    ALLOW_ORIGINS: list[str] = Field(default_factory=lambda: ["*"])
    ALLOW_METHODS: list[str] = Field(default_factory=lambda: ["GET", "POST", "PUT", "DELETE", "OPTIONS"])
    ALLOW_HEADERS: list[str] = Field(default_factory=lambda: ["*"])

    # Path to the SSH key for connecting to external servers
    SSH_KEY: str = "~/.ssh/id_rsa"

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
    MAX_FILE_LENGTH: int = 1024 * 1024 * 10  # Max size (bytes) for one resource source file
    MAX_RESOURCE_LENGTH: int = 1024 * 1024 * 500  # Max size (bytes) for one resource

    # SB Auth settings
    SBAUTH_PUBKEY_FILE: str = "pubkey.pem"
    SBAUTH_URL: str = ""  # URL for SB Auth
    SBAUTH_API_KEY: str = ""  # API key for SB Auth
    SBAUTH_MINK_APP_RESOURCE: str = "mink-app"  # Name of the resource used to control admin grants
    SBAUTH_CACHE_LIFETIME: int = 10 * 60  # How long to cache fetched permissions (in seconds)
    SBAUTH_PERSONAL_API_KEY: str = ""  # Personal API key for SB Auth (used for testing purposes)

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

    model_config = {
        "env_file": ".env",  # Load variables from a .env file if it exists
        "env_file_encoding": "utf-8",
        "extra": "ignore"  # Ignore extra environment variables from other modules (e.g. SPARV_*)
    }


settings = Settings()
