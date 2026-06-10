"""Instantiation of FastAPI app."""

import logging
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

from mink.cache.memcached import cache
from mink.core import config_utils, exceptions, job_routes, registry, routes, user_routes, utils
from mink.core.config import settings
from mink.core.logging import logger
from mink.core.resource_specs import get_resource_routers, run_startup_checks
from mink.sb_auth import routes as login_routes

MINK_VERSION = utils.get_version_from_pyproject()


def preflight() -> None:
    """Perform preflight checks before starting the app."""
    logger.info("Starting Mink version: %s", MINK_VERSION)
    logger.debug("Environment: %s. Log level: %s", settings.ENV, settings.LOG_LEVEL)

    # Check for unused environment variables
    config_utils.check_unused_env_vars()

    # Make sure required config variables are set
    if not settings.CACHE_CLIENT:
        logger.error("CACHE_CLIENT not set, cannot start Mink!")
        raise exceptions.ConfigVariableNotSetError("CACHE_CLIENT")
    if not settings.INSTANCE_PATH:
        logger.error("INSTANCE_PATH not set, cannot start Mink!")
        raise exceptions.ConfigVariableNotSetError("INSTANCE_PATH")
    if not settings.SBAUTH_PUBKEY_FILE:
        logger.error("SBAUTH_PUBKEY_FILE not set, cannot start Mink!")
        raise exceptions.ConfigVariableNotSetError("SBAUTH_PUBKEY_FILE")

    # Run any registered startup checks from resource specs
    try:
        run_startup_checks()
    except Exception as e:
        logger.exception("Error occurred while running startup checks: %s", e)
        raise

    # Create instance directory if it does not exist
    Path(settings.INSTANCE_PATH).mkdir(exist_ok=True)

    # Initialize the cache client and the resource registry
    cache.initialize(settings.CACHE_CLIENT)
    registry.initialize_if_needed()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator:
    """Lifespan context manager for the FastAPI app.

    Args:
        app (FastAPI): The FastAPI application instance.

    Yields:
        None: Indicates the lifespan context.
    """
    # -------------------------------
    # Startup logic
    # -------------------------------
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


preflight()

# Deactivate default Redoc, Swagger UI and openapi_url because we use custom routes
app = FastAPI(
    lifespan=lifespan,
    version=MINK_VERSION,
    root_path=settings.ROOT_PATH,
    redoc_url=None,
    docs_url=None,
    openapi_url=None,
)

# Create docs/site directory if it does not exist
docs_site_path = Path("docs/site")
docs_site_path.mkdir(parents=True, exist_ok=True)

# Mount directories for static files
app.mount("/static", StaticFiles(directory="mink/static"), name="static")
app.mount("/docs", StaticFiles(directory=docs_site_path, html=True), name="mkdocs")

# ------------------------------------------------------------------------------
# Register custom exception handlers
# ------------------------------------------------------------------------------
app.add_exception_handler(exceptions.MinkHTTPException, exceptions.custom_http_exception_handler)  # type: ignore
app.add_exception_handler(RequestValidationError, exceptions.validation_exception_handler)  # type: ignore
app.add_exception_handler(StarletteHTTPException, exceptions.starlette_exceptions_handler)  # type: ignore
app.add_exception_handler(Exception, exceptions.internal_server_error_handler)


# ------------------------------------------------------------------------------
# Include routes
# ------------------------------------------------------------------------------
app.include_router(routes.router)
app.include_router(job_routes.router)
app.include_router(login_routes.router)
app.include_router(user_routes.router)
for router in get_resource_routers():
    app.include_router(router)


# ------------------------------------------------------------------------------
# Middleware
# ------------------------------------------------------------------------------
@app.middleware("http")
async def log_request(request: Request, call_next: Callable) -> Response:
    """Middleware to log info about each request (except when serving static files)."""
    root_path = request.scope.get("root_path") or ""
    path = request.scope.get("path") or request.url.path
    if root_path and path.startswith(root_path):
        path = path[len(root_path) :] or "/"

    # Log request info, but don't log options and queue advance requests (too much spam)
    if request.method != "OPTIONS" and not path.startswith(("/queue/advance", "/queue/health")):
        request_str = f"{request.method} {path}" + (f"?{request.url.query}" if request.url.query else "")
        logger.info("Request: %s", request_str)

    # Call the actual route
    return await call_next(request)


# Add middleware to enforce the request size limit
app.add_middleware(utils.LimitRequestSizeMiddleware)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=settings.ALLOW_METHODS,
    allow_headers=settings.ALLOW_HEADERS,
)

# Add Matomo middleware for tracking
if settings.TRACKING_MATOMO_URL and settings.TRACKING_MATOMO_IDSITE:
    logger.info("Enabling tracking to Matomo")
    if settings.LOG_LEVEL == "DEBUG":
        logging.getLogger("asgi_matomo").setLevel("DEBUG")
    # Suppress some chatty logs
    logging.getLogger("httpx").setLevel("WARNING")
    # Add the Matomo middleware
    app.add_middleware(
        MatomoMiddleware,
        matomo_url=settings.TRACKING_MATOMO_URL,
        idsite=settings.TRACKING_MATOMO_IDSITE,
        access_token=settings.TRACKING_MATOMO_AUTH_TOKEN,
        http_timeout=settings.TRACKING_MATOMO_HTTP_TIMEOUT,
        exclude_paths=["/queue/advance", "/queue/health"],
        ignored_methods=["OPTIONS"],
    )
elif settings.ENV not in {"testing", "development"}:
    logger.warning("Tracking to Matomo disabled, please set TRACKING_MATOMO_URL and TRACKING_MATOMO_IDSITE.")


# ------------------------------------------------------------------------------
# Custom OpenAPI schema
# ------------------------------------------------------------------------------
def custom_openapi() -> dict:
    """Customize the OpenAPI schema.

    Returns:
        dict: The OpenAPI schema
    """

    def rewrite_file_upload_schema(schema: object) -> None:
        """Rewrite OpenAPI 3.1 octet-stream file fields to Swagger-friendly binary fields."""
        if isinstance(schema, dict):
            if schema.get("type") == "string" and schema.get("contentMediaType") == "application/octet-stream":
                schema["format"] = "binary"
            for value in schema.values():
                rewrite_file_upload_schema(value)
        elif isinstance(schema, list):
            for item in schema:
                rewrite_file_upload_schema(item)

    if app.openapi_schema:
        return app.openapi_schema
    # Load OpenAPI info from the YAML file
    openapi_info_path = Path(__file__).parent / "openapi_info.yaml"
    with openapi_info_path.open("r", encoding="utf-8") as file:
        openapi_info = yaml.safe_load(file)
    openapi_schema = get_openapi(
        title=openapi_info["info"]["title"],
        version=MINK_VERSION,
        routes=app.routes,
    )
    openapi_schema["info"] = openapi_info["info"]
    openapi_schema["info"]["version"] = MINK_VERSION  # Need to set version again since it is overridden above
    openapi_schema["tags"] = openapi_info["tags"]
    openapi_schema["servers"] = []
    if settings.ENV in {"development", "testing"}:
        # Add local test server if in development/testing mode
        openapi_schema["servers"].append({"url": settings.MINK_URL, "description": "Local test server"})
    openapi_schema["servers"].extend(openapi_info["servers"])

    openapi_schema["components"]["securitySchemes"] = {
        "OAuth2PasswordBearer": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"},
        "APIKeyHeader": {"type": "apiKey", "in": "header", "name": "X-Api-Key"},
    }

    # Make Swagger UI render OpenAPI 3.1 file upload schemas
    for schema in openapi_schema.get("components", {}).get("schemas", {}).values():
        rewrite_file_upload_schema(schema)

    # Adapt some settings for the OpenAPI schema
    host = settings.MINK_URL

    # Remove auto-generated "title" from schemas
    for schema in openapi_schema.get("components", {}).get("schemas", {}).values():
        schema.pop("title", None)

    for path_item in openapi_schema.get("paths", {}).values():
        for operation in path_item.values():
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

    # Inject resource-specific OpenAPI examples
    from mink.core.resource_specs import get_all_specs  # noqa: PLC0415

    for spec in get_all_specs().values():
        if not spec.openapi_examples:
            continue
        for schema_name, examples in spec.openapi_examples.items():
            schema = openapi_schema.get("components", {}).get("schemas", {}).get(schema_name)
            if schema is not None:
                schema["examples"] = examples

    # Cache the modified OpenAPI schema
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi
