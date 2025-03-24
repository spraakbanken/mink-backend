"""Default configuration for mink.

Can be overridden with config.py in instance folder.
"""

LOG_LEVEL = "INFO"  # Log level for the application
MINK_URL = ""  # URL for mink API

# Prefix used when creating new resources
RESOURCE_PREFIX = "mink-"

# File upload settings
MAX_CONTENT_LENGTH = 1024 * 1024 * 100  # Max size (bytes) for one request (which may contain multiple files)
MAX_FILE_LENGTH = 1024 * 1024 * 10  # Max size (bytes) for one corpus source file
MAX_CORPUS_LENGTH = 1024 * 1024 * 500  # Max size (bytes) for one corpus
RECOMMENDED_MIN_FILE_LENGTH = (
    1024 * 1024 * 1
)  # Recommended min size (bytes) for one corpus source file (when uploading many files)
RECOMMENDED_MAX_FILE_LENGTH = 1024 * 1024 * 5  # Recommended max size (bytes) for one corpus source file

# sb-auth settings
SBAUTH_PUBKEY_FILE = "pubkey.pem"
SBAUTH_URL = ""
SBAUTH_API_KEY = ""
SBAUTH_MINK_APP_RESOURCE = "mink-app"  # Name of the resource used to control admin grants
SBAUTH_CACHE_LIFETIME = 10 * 60  # How long to cache fetched permissions (in seconds)

# Sparv specific strings and settings
SPARV_SOURCE_DIR = "source"
SPARV_EXPORT_DIR = "export"
SPARV_WORK_DIR = "sparv-workdir"
SPARV_CORPUS_CONFIG = "config.yaml"
SPARV_PLAIN_TEXT_FILE = "@text"
SPARV_IMPORTER_MODULES = {
    ".xml": "xml_import",
    ".txt": "text_import",
    ".docx": "docx_import",
    ".odt": "odt_import",
    ".pdf": "pdf_import",
}  # File extensions for corpus input and the modules that handle them

# Settings for the server where Sparv is run
SSH_KEY = "~/.ssh/id_rsa"
SPARV_HOST = ""  # Define this in instance/config.py!
SPARV_USER = ""  # Define this in instance/config.py!
SPARV_WORKERS = 1  # Number of available Sparv workers
SPARV_DEFAULT_CORPORA_DIR = "~/mink-data/corpus/default"  # Dir for running listings like 'sparv run -l'
SPARV_CORPORA_DIR = "mink-data/corpus"  # Dir where the user corpora are stored and run, relative to the user's home dir
SPARV_ENVIRON = "SPARV_DATADIR=~/sparv-pipeline/data/"  # Environment variables to set when running Sparv
SPARV_COMMAND = "~/sparv-pipeline/venv/bin/python -u -m sparv"  # Command for calling Sparv
SPARV_RUN = "run --socket ~/sparv-pipeline/sparv.socket --json-log --log-to-file info"  # Sparv's 'run' command
SPARV_INSTALL = "install --json-log --log-to-file info"  # Sparv's 'install' command
SPARV_UNINSTALL = "uninstall --log-to-file info"  # Sparv's 'uninstall' command
SPARV_DEFAULT_EXPORTS = [
    "xml_export:pretty",
    "csv_export:csv",
    "stats_export:freq_list",
]  # Default export formats to create if nothing is specified
SPARV_EXPORT_BLACKLIST = [
    "cwb.*",
    "korp.*",
    "sbx_strix.*",
]  # Glob patterns for exports that will be excluded from listings and downloads
SPARV_DEFAULT_KORP_INSTALLS = [
    "korp:install_timespan",
    "korp:install_config",
    "korp:install_lemgrams",
]  # Default Korp install targets to create
SPARV_DEFAULT_KORP_UNINSTALLS = [
    "cwb:uninstall_corpus",
    "korp:uninstall_timespan",
    "korp:uninstall_config",
    "korp:uninstall_lemgrams",
]  # Default Korp uninstall targets
SPARV_DEFAULT_STRIX_INSTALLS = [
    "sbx_strix:install_config",
    "sbx_strix:install_corpus",
    "sbx_strix:install_xml",
]  # Default Strix install targets to create
SPARV_DEFAULT_STRIX_UNINSTALLS = [
    "sbx_strix:uninstall_config",
    "sbx_strix:uninstall_corpus",
    "sbx_strix:uninstall_xml",
]  # Default Strix uninstall targets
SPARV_NOHUP_FILE = "mink.out"  # File collecting Sparv output for a job
SPARV_TMP_RUN_SCRIPT = "run_sparv.sh"  # Temporary Sparv run script created for every job

# Settings for metadata upload
METADATA_HOST = ""  # Define this in instance/config.py!
METADATA_USER = ""  # Define this in instance/config.py!
METADATA_DIR = "mink-data/metadata"  # Dir where metadata resources are stored, relative to the user's home dir
METADATA_ID_AVAILABLE_URL = ""
METADATA_SOURCE_DIR = "source"  # Dir for storing resource files belonging to a metadata resource
METADATA_ORG_PREFIXES = {}  # Mapping from user IDs to organisation prefixes

# Local files relative to flask instance dir
TMP_DIR = "tmp"  # Temporary file storage
MEMCACHED_SOCKET = "memcached.sock"  # Memcached socket file
REGISTRY_DIR = "registry"  # Directory for storing job files
QUEUE_FILE = "queue"  # File to store the queue priorities

# Settings for queue manager
CHECK_QUEUE_FREQUENCY = 20  # How often the queue will be checked for new jobs (in seconds)
MINK_SECRET_KEY = ""  # Define this in instance/config.py!
HEALTHCHECKS_URL = ""  # Healthchecks URL, define this in instance/config.py!
PING_FREQUENCY = 60  # Frequency (in minutes) for how often healthchecks should be pinged

# Settings for tracking to Matomo (uncomment)
# TRACKING_MATOMO_URL =
# TRACKING_MATOMO_IDSITE =
# TRACKING_MATOMO_AUTH_TOKEN =
# TRACKING_MATOMO_HTTP_TIMEOUT =



DOCS_FAVICON = "static/favicon.ico"
REDOC_CONFIG = {"typography": {"fontsize": "15px"}}

INFO = {
    "description": """# Introduction
Web API serving as a backend to Mink.

For now the API is used for uploading corpus data to a storage server and processing that data with Sparv.

# Workflow
A workflow for processing data with Sparv via Mink could look like this:

1. <a href="#operation/createcorpus">Create a new corpus</a>
2. <a href="#operation/uploadsources">Upload some corpus source files</a>
3. <a href="#operation/uploadconfig">Upload a corpus config file</a>
4. <a href="#operation/runSparv">Run Sparv</a>
5. <a href="#operation/resourceinfo">Check the status</a>
6. <a href="#operation/downloadexports">Download export files</a>
7. <a href="#operation/installinKorp">Install the corpus in Korp</a> / <a href="#operation/installinStrix">Strix</a>

# Authentication
Note that most HTTP requests need to be authenticated with A) a JSON Web Token (JWT, read more at https://jwt.io/)
or B) an SB-Auth user API key:

## JWT
1. In the browser, log in at https://spraakbanken.gu.se/mink
2. Open https://sp.spraakbanken.gu.se/auth/jwt to download the token in plain text
3. Use the token in the request header as: `Authorization: Bearer <token>`
4. The token is valid for a few hours. When it expires, repeat these steps.

## API key
1. Ask Språkbanken for an API key
2. Use the API key token in the request header as: `X-Api-Key: <token>`
3. The token is valid for an extended time, currently 90 days. When it expires, repeat these steps

# Parameters
Parameters such as `corpus_id` can usually be provided as a query parameter or as form data.
The following two examples will thus result in the same response:

`curl -X GET '{{host}}/list-sources?corpus_id=some_corpus_name' -H 'Authorization: Bearer YOUR_JWT`

`curl -X GET -F "corpus_id=some_corpus_name" '{{host}}/list-sources' -H 'Authorization: Bearer YOUR_JWT`

# Responses
- Most responses will be in json format.
- Json responses contain a `status` field which will have the value `success` if the response code is 200 and
  `error` otherwise. Thus this `status` merely reports whether the call was processed correctly.
- All json responses also contain a `return_code` field with a unique code that can be used for mapping to
  human-friendly error messages.
- Most responses contain a `message` field with information about what was done during the call or where things went
  wrong.
- Each call may have an arbitrary amount of additional fields containing more information or data.
""",
    "x-logo": {
        "url": "https://raw.githubusercontent.com/spraakbanken/mink-backend/main/mink/static/mink.svg"
    },
    "contact": {
        "name": "Språkbanken",
        "url": "https://spraakbanken.gu.se/",
        "email": "sb-info@svenska.gu.se",
    },
    "license": {
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    "servers": [
        {
            "url": "https://ws.spraakbanken.gu.se/ws/mink",
            "description": "Production server",
        }
    ],
}
