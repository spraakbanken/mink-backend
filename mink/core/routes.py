"""Collection of general routes."""

import re
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from mink.config import settings
from mink.core import utils
from mink.core.models import InfoResponse

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/", include_in_schema=False)
async def hello() -> RedirectResponse:
    """Redirect to /api_doc."""
    return RedirectResponse(url="/api-doc")


@router.get("/api-spec", tags=["Documentation"], response_model=dict)
async def api_specification(request: Request) -> JSONResponse:
    """Get the open API specification (in json format) for this API."""
    return request.app.openapi_url


@router.get("/api-doc", tags=["Documentation"])
async def api_documentation(request: Request) -> HTMLResponse:
    """Render ReDoc HTML (documentation for this API)."""
    return get_redoc_html(
        openapi_url=request.app.openapi_url,
        redoc_favicon_url="/static/favicon.ico",
        title="Mink API documentation"
    )


@router.get("/swagger-test", include_in_schema=False)
async def custom_swagger_ui_html(request: Request) -> HTMLResponse:
    """Render Swagger UI with custom JavaScript to apply API key authentication in each request."""
    html = get_swagger_ui_html(
        openapi_url=request.app.openapi_url,
        swagger_favicon_url="/static/favicon.ico",
        title=request.app.title + " - Swagger UI",
    ).body.decode()

    api_key = settings.SBAUTH_PERSONAL_API_KEY
    if api_key:
        # Insert a requestInterceptor into the swagger UI html
        intercept = f"""requestInterceptor: (req) => {{ req.headers["X-API-Key"] = "{api_key}"; return req; }},\n"""
        html = re.sub(r"(url: '/api-spec',\n)", r"\1" + " " * 8 + intercept, html)

    return HTMLResponse(html)


@router.get("/developers-guide", tags=["Documentation"])
async def developers_guide(request: Request) -> HTMLResponse:
    """Render docsify HTML with the developer's guide."""
    mink_url = settings.MINK_URL
    return templates.TemplateResponse(
        request=request, name="docsify.html", context={"favicon": f"{mink_url}/static/favicon.ico"}
    )


@router.get("/developers-guide/{path:path}", include_in_schema=False)
async def developers_guide_files(path: str) -> HTMLResponse:
    """Serve sub pages to the developer's guide needed by docsify."""
    file_path = Path("templates") / path
    if file_path.exists():
        return HTMLResponse(content=file_path.read_text(encoding="UTF-8"))
    return HTMLResponse(content="File not found", status_code=404)


@router.get("/info", tags=["Documentation"], response_model=InfoResponse)
async def api_info() -> JSONResponse:
    """Show info about data processing, e.g. job status codes, file size limits and Sparv importer modules."""
    from mink.core.status import Status  # noqa: PLC0415

    status_codes = {"info": "job status codes", "data": []}
    for s in Status:
        status_codes["data"].append({"name": s.value, "description": s.description})

    importer_modules = {"info": "Sparv importers that need to be used for different file extensions", "data": []}
    for ext, importer in settings.SPARV_IMPORTER_MODULES.items():
        importer_modules["data"].append({"file_extension": ext, "importer": importer})

    file_size_limits = {
        "info": "size limits (in bytes) for uploaded files",
        "data": [
            {
                "name": "max_content_length",
                "description": "max size for one request (which may contain multiple files)",
                "value": settings.MAX_CONTENT_LENGTH,
            },
            {
                "name": "max_file_length",
                "description": "max size for one corpus source file",
                "value": settings.MAX_FILE_LENGTH,
            },
            {
                "name": "max_corpus_length",
                "description": "max size for one corpus",
                "value": settings.MAX_CORPUS_LENGTH,
            },
        ],
    }

    recommended_file_size = {
        "info": "approximate recommended file sizes (in bytes) when processing many files with Sparv",
        "data": [
            {
                "name": "max_file_length",
                "description": "recommended min size for one corpus source file",
                "value": settings.RECOMMENDED_MIN_FILE_LENGTH,
            },
            {
                "name": "min_file_length",
                "description": "recommended max size for one corpus source file",
                "value": settings.RECOMMENDED_MAX_FILE_LENGTH,
            },
        ],
    }

    return utils.response(
        message="Listing information about data processing",
        return_code="listing_info",
        status_codes=status_codes,
        importer_modules=importer_modules,
        file_size_limits=file_size_limits,
        recommended_file_size=recommended_file_size,
    )
