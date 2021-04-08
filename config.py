"""Default configuration for sparv_backed.

Can be overridden with config.py in instance folder.
"""

LOG_LEVEL = "INFO"   # Log level for the application

# Nextcloud settings
NC_DOMAIN = "https://spraakbanken.gu.se/nextcloud"  # Nextcloud domain
NC_CORPORA_DIR = "Min Språkbank"  # Directory on Nextcloud where the corpora are stored
NC_STATUS_FILE = "status.json"    # File where a job status is stored

# Sparv specific strings and settings
SPARV_SOURCE_DIR = "source"
SPARV_EXPORT_DIR = "export"
SPARV_CORPUS_CONFIG = "config.yaml"
SPARV_VALID_INPUT_EXT = [".xml", ".txt"]       # File extensions for corpus input

# Settings for the server where Sparv is run
SPARV_SERVER = ""  # Define this in instance/config.py!
SPARV_USER = ""    # Define this in instance/config.py!
SPARV_WORKERS = 1  # Number of available Sparv workers
SPARV_DEFAULT_CORPORA_DIR = "min-sb-data/default"  # Dir for running listings like 'sparv run -l'
SPARV_CORPORA_DIR = "min-sb-data"                  # Dir where the user corpora are stored and run
SPARV_ENVIRON = "SPARV_DATADIR=~/min-sb-pipeline/data/"                       # Environment variables to set when running Sparv
SPARV_COMMAND = "~/min-sb-pipeline/venv/bin/python -u -m sparv"               # Command for calling Sparv
SPARV_RUN = "run --socket ~/min-sb-pipeline/sparv.socket --log-to-file info"  # Sparv's 'run' command
SPARV_DEFAULT_EXPORTS = ["xml_export:pretty"]  # Default export format to create if nothing is specified
SPARV_NOHUP_FILE = "min-sb.out"                # File collecting Sparv output for a job
SPARV_TMP_RUN_SCRIPT = "run_sparv.sh"          # Temporary Sparv run script created for every job

# Local files relative to flask instance dir
TMP_DIR = "tmp"                      # Temporary file storage
MEMCACHED_SOCKET = "memcached.sock"  # Memcached socket file
QUEUE_DIR = "queue"                  # Directory for storing job files

# Settings for queue manager
MIN_SB_URL = "https://ws.spraakbanken.gu.se/ws/min-sb"  # URL for min-sb API
CHECK_QUEUE_FREQUENCY = 20  # How often the queue will be checked for new jobs (in seconds)
MIN_SB_SECRET_KEY = ""  # Define this in instance/config.py!
HEALTHCHECKS_URL = ""   # Healthchecks URL, define this in instance/config.py!
PING_FREQUENCY = 60     # Frequency (in minutes) for how often healthchecks should be pinged
