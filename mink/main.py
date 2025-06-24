"""Instantiation of FastAPI app."""

__version__ = "1.2.0-dev"

import shutil
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from asgi_matomo import MatomoMiddleware
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from mink.cache.cache import initialize_cache
from mink.core import exceptions, registry, routes, utils
from mink.core.config import settings
from mink.core.logging import logger
from mink.metadata import routes as metadata_routes
from mink.sb_auth import routes as login_routes
from mink.sparv import process_routes, storage_routes


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator:  # noqa: RUF029 unused async
    """Lifespan context manager for the FastAPI app.

    Args:
        app (FastAPI): The FastAPI application instance.

    Yields:
        None: Indicates the lifespan context.
    """
    # -------------------------------
    # Startup logic
    # -------------------------------
    logger.info("Startig Mink version: %s", __version__)

    # Make sure required config variables are set
    if not settings.CACHE_CLIENT:
        raise ValueError("Config variable 'CACHE_CLIENT' is not set.")
    if not settings.SPARV_HOST:
        raise ValueError("Config variable 'SPARV_HOST' is not set.")
    if not settings.SPARV_USER:
        raise ValueError("Config variable 'SPARV_USER' is not set.")
    if not settings.SBAUTH_PUBKEY_FILE:
        raise ValueError("Config variable 'SBAUTH_PUBKEY_FILE' is not set.")
    if not settings.INSTANCE_PATH:
        raise ValueError("Config variable 'INSTANCE_PATH' is not set.")

    # Create instance directory if it does not exist
    Path(settings.INSTANCE_PATH).mkdir(exist_ok=True)

    # Initialize the cache client and the resource registry
    initialize_cache(settings.CACHE_CLIENT)
    logger.info("Connected to memcached on %s", settings.CACHE_CLIENT)
    registry.initialize()

    # Build the MkDocs documentation
    if settings.ENV != "testing":
        utils.build_docs()

    yield

    # -------------------------------
    # Shutdown logic
    # -------------------------------
    logger.info("Shutting down Mink, removing temporary files")
    tmp_dir = Path(settings.INSTANCE_PATH) / settings.TMP_DIR
    shutil.rmtree(str(tmp_dir), ignore_errors=True)
    logger.info("Done")


# Deactivate default Redoc and Swagger UI and openapi_url because we use custom ones
app = FastAPI(lifespan=lifespan, version=__version__, redoc_url=None, docs_url=None, openapi_url=None)

# Create docs/site directory if it does not exist
docs_site_path = Path("docs/site")
docs_site_path.mkdir(parents=True, exist_ok=True)

# Mount directories for static files
app.mount("/static", StaticFiles(directory="mink/static"), name="static")
app.mount("/docs", StaticFiles(directory=docs_site_path, html=True), name="mkdocs")

# ------------------------------------------------------------------------------
# Register custom exception handlers
# ------------------------------------------------------------------------------
app.add_exception_handler(exceptions.MinkHTTPException, exceptions.custom_http_exception_handler)
app.add_exception_handler(RequestValidationError, exceptions.validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, exceptions.starlette_exceptions_handler)
app.add_exception_handler(Exception, exceptions.internal_server_error_handler)


# ------------------------------------------------------------------------------
# Include routes
# ------------------------------------------------------------------------------
app.include_router(routes.router)
app.include_router(login_routes.router)
app.include_router(storage_routes.router)
app.include_router(process_routes.router)
app.include_router(metadata_routes.router)


# ------------------------------------------------------------------------------
# Middleware
# ------------------------------------------------------------------------------
@app.middleware("http")
async def log_request(request: Request, call_next: Callable) -> Response:
    """Middleware to log info about each request (except when serving static files)."""
    # Log request info, but don't log options and advance-queue requests (too much spam)
    if request.method != "OPTIONS" and request.url.path != "/advance-queue":
        logger.info("Request: %s %s?%s", request.method, request.url.path, request.url.query)

    # Call the actual route
    return await call_next(request)


# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust origins as needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Add Matomo middleware for tracking
if settings.TRACKING_MATOMO_URL and settings.TRACKING_MATOMO_IDSITE:
    logger.info("Enabling tracking to Matomo")
    # # Suppress some chatty logs
    # logger.getLogger("httpx").setLevel("WARNING")
    # Add the Matomo middleware
    app.add_middleware(
        MatomoMiddleware,
        matomo_url=settings.TRACKING_MATOMO_URL,
        idsite=settings.TRACKING_MATOMO_IDSITE,
        access_token=settings.TRACKING_MATOMO_AUTH_TOKEN,
        http_timeout=settings.TRACKING_MATOMO_HTTP_TIMEOUT,
        exclude_paths=["/advance-queue"],
        ignored_methods=["OPTIONS"],
    )
elif settings.ENV not in {"testing", "development"}:
    logger.warning("Tracking to Matomo disabled, please set TRACKING_MATOMO_URL and TRACKING_MATOMO_IDSITE.")


# Add middleware to enforce the request size limit
app.add_middleware(utils.LimitRequestSizeMiddleware, max_body_size=settings.MAX_CONTENT_LENGTH)


# ------------------------------------------------------------------------------
# Custom OpenAPI schema
# ------------------------------------------------------------------------------
def custom_openapi() -> dict:
    """Customize the OpenAPI schema.

    Returns:
        dict: The OpenAPI schema
    """
    if app.openapi_schema:
        return app.openapi_schema
    # Load OpenAPI info from the YAML file
    openapi_info_path = Path(__file__).parent / "openapi_info.yaml"
    with openapi_info_path.open("r", encoding="utf-8") as file:
        openapi_info = yaml.safe_load(file)
    openapi_schema = get_openapi(
        title=openapi_info["info"]["title"],
        version=__version__,
        routes=app.routes,
    )
    openapi_schema["info"] = openapi_info["info"]
    openapi_schema["info"]["version"] = __version__
    openapi_schema["tags"] = openapi_info["tags"]
    openapi_schema["servers"] = []
    if settings.ENV in {"development", "testing"}:
        # Add local test server if in development/testing mode
        openapi_schema["servers"].append({"url": settings.MINK_URL, "description": "Local test server"})
    openapi_schema["servers"].extend(openapi_info["servers"])

    openapi_schema["components"]["securitySchemes"] = {
        "OAuth2PasswordBearer": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"},
        "APIKeyHeader": {"type": "apiKey", "in": "header", "name": "X-Api-Key"}
    }

    # Adapt some settings for the OpenAPI schema
    host = settings.MINK_URL

    # Remove auto-generated "title" from schemas
    for schema in openapi_schema.get("components", {}).get("schemas", {}).values():
        schema.pop("title", None)

    for path, path_item in openapi_schema.get("paths", {}).items():
        for method, operation in path_item.items():

            # Generate simpler operationIds (used for anchor links in the documentation)
            # Example: /admin-mode-off [POST] -> admin-mode-off-post
            clean_path = path.strip("/").replace("/", "-")
            if not clean_path:
                clean_path = "root"
            operation_id = f"{clean_path}-{method}"
            operation["operationId"] = operation_id

            # Remove auto-generated "title" from response schemas in paths
            for response in operation.get("responses", {}).values():
                for schema in (media.get("schema", {}) for media in response.get("content", {}).values()):
                    schema.pop("title", None)

            # Populate resource_id param with default value in development mode
            if settings.ENV in {"development", "testing"} and settings.DEFAULT_RESOURCE_ID:
                for param in operation.get("parameters", []):
                    if param["name"] == "resource_id":
                        param["schema"]["default"] = settings.DEFAULT_RESOURCE_ID

            # Replace {{host}} in descriptions with actual backend URL
            operation["description"] = operation.get("description", "").replace("{{host}}", host)

    # Cache the modified OpenAPI schema
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi
