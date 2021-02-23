"""Default configuration for sparv_backed.

Can be overridden with config.py in instance folder.
"""

# Nextcloud settings
NC_DOMAIN = "https://spraakbanken.gu.se/nextcloud"  # Nextcloud domain
CORPORA_DIR = "Min Språkbank"  # Directory on Nextcloud where the corpora are stored
NC_STATUS_FILE = "status.json"    # File where a job status is stored

# Sparv specific strings
SPARV_SOURCE_DIR = "source"
SPARV_EXPORT_DIR = "export"
SPARV_CORPUS_CONFIG = "config.yaml"

# Info about the server where Sparv is run
SPARV_SERVER = ""  # Define this in instance/config.py!
SPARV_USER = ""    # Define this in instance/config.py!
SPARV_WORKERS = 1  # Number of available Sparv workers
REMOTE_CORPORA_DIR = "min-sb-data"
SPARV_COMMAND = "/home/fksparv/.local/pipx/venvs/sparv-pipeline/bin/python -u -m sparv"
SPARV_DEFAULT_EXPORTS = ["xml_export:pretty"]
SPARV_VALID_INPUT_EXT = [".xml", ".txt"]   # File extensions for corpus input
SPARV_NOHUP_FILE = "min-sb.out"            # File collecting Sparv output for a job
SPARV_TMP_RUN_SCRIPT = "run_sparv.sh"      # Temporary Sparv run script created for every job

# Local files relative to flask instance dir
TMP_DIR = "tmp"                      # Temporary file storage
MEMCACHED_SOCKET = "memcached.sock"  # Memcached socket file
QUEUE_DIR = "queue"

# Settings for queue manager
MIN_SB_URL = "https://ws.spraakbanken.gu.se/ws/min-sb"  # URL for min-sb API
CHECK_QUEUE_FREQUENCY = 20  # How often the queue will be checked for new jobs (in seconds)
