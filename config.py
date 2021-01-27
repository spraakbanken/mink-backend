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
SPARV_COMMAND = "/home/fksparv/.local/pipx/venvs/sparv-pipeline/bin/python -m sparv"

# Local temporary file storage (relative to flask instance dir)
TMP_DIR = "tmp"
