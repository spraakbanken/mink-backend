"""Default configuration for sparv_backed.

Can be overwritten with config.py in instance folder.
"""

# Nextcloud domain
NC_DOMAIN = "https://spraakbanken.gu.se/nextcloud"

# Directory on Nextcloud where the corpora are stored
CORPORA_DIR = "Min Språkbank"

# Sparv specific strings
SPARV_SOURCE_DIR = "source"
SPARV_EXPORT_DIR = "export"
SPARV_CORPUS_CONFIG = "config.yaml"

# Info about the server where Sparv is run
SPARV_SERVER = ""
SPARV_USER = ""
REMOTE_CORPORA_DIR = "min-sb-data"
SPARV_COMMAND = "/home/fksparv/.local/pipx/venvs/sparv-pipeline/bin/python -u -m sparv"
SPARV_DEFAULT_EXPORTS = ["xml_export:pretty"]
SPARV_VALID_INPUT_EXT = [".xml", ".txt"]
SPARV_NOHUP_FILE = "min-sb.out"

# Local temporary file storage (relative to flask instance dir)
TMP_DIR = "tmp"

# Memcached socket file relative to instance dir
MEMCACHED_SOCKET = "memcached.sock"
