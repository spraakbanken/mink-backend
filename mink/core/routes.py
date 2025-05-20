"""Collection of general routes."""

import json
import re
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from mink.core import utils
from mink.core.config import settings
from mink.core.models import InfoResponse

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/", include_in_schema=False)
async def hello() -> RedirectResponse:
    """Redirect to /redoc."""
    return RedirectResponse(url="/redoc")


@router.get("/openapi.json", tags=["Documentation"], response_model=dict)
async def api_specification(request: Request) -> JSONResponse:
    """Get the open API specification (in json format) for this API."""
    oas = request.app.openapi()
    # Convert markdown anchor links to ReDoc operation links, e.g. (#install-strix-put)->(#operation/install-strix-put)
    oas_string = re.sub(r"\(#([a-zA-Z0-9\-]+)\)", r"(#operation/\1)", json.dumps(oas))
    return JSONResponse(content=json.loads(oas_string))


# Kept for backwards compatibility
@router.get("/api-spec", include_in_schema=False)
async def api_specification2() -> JSONResponse:
    """Get the open API specification (in json format) for this API."""
    return RedirectResponse(url="/openapi.json")


@router.get("/redoc", tags=["Documentation"], response_class=HTMLResponse)
async def api_documentation() -> HTMLResponse:
    """Render ReDoc HTML (documentation for this API)."""
    return get_redoc_html(
        openapi_url="/openapi.json",
        redoc_favicon_url="/static/favicon.ico",
        title="Mink API documentation"
    )


# Kept for backwards compatibility
@router.get("/api-doc", include_in_schema=False)
async def api_documentation2() -> HTMLResponse:
    """Render ReDoc HTML (documentation for this API)."""
    return RedirectResponse(url="/redoc")


@router.get("/swagger-openapi.json", include_in_schema=False)
async def swagger_api_spec(request: Request) -> JSONResponse:
    """Serve a modified OpenAPI schema (OAS) for Swagger."""
    oas = request.app.openapi()
    # Create a dictionarey with paths as keys and their tag names as values (needed for Swagger links)
    paths_dict = {
        operation.get("operationId", ""): tag.replace(" ", "%20")
        for operations in oas.get("paths", {}).values()
        for operation in operations.values()
        for tag in operation.get("tags", [])
    }
    # Convert markdown anchor links to Swagger links, e.g. (#install-strix-put)->(#/Process%20Corpus/install-strix-put)
    oas_string = re.sub(
        r"\(#([a-zA-Z0-9\-]+)\)",
        lambda match: f"(#/{paths_dict.get(match.group(1), '')}/{match.group(1)})",
        json.dumps(oas)
    )
    return JSONResponse(content=json.loads(oas_string))


@router.get("/docs", tags=["Documentation"], response_class=HTMLResponse)
async def swagger_api_documentation(request: Request) -> HTMLResponse:
    """Render Swagger UI HTML (documentation for this API)."""
    html = get_swagger_ui_html(
        openapi_url="/swagger-openapi.json",
        swagger_favicon_url="/static/favicon.ico",
        title=request.app.title + " - Swagger UI",
    ).body.decode()
    # Modify JavaScript to apply API key authentication in each request if SBAUTH_PERSONAL_API_KEY is set
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
