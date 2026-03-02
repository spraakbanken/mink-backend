"""Collection of general routes."""

import json
import re
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import Template

from mink.core import return_codes, utils
from mink.core.config import settings
from mink.core.models import InfoResponse, ReturnCodesResponse
from mink.core.resource_specs import get_all_specs

router = APIRouter(tags=["Documentation"])
templates = Jinja2Templates(directory="templates")


@router.get("/", include_in_schema=False)
async def hello(request: Request) -> RedirectResponse:
    """Redirect to /redoc."""
    return RedirectResponse(url=request.url_for("api_documentation"))


@router.get("/openapi.json", response_model=dict)
async def api_specification(request: Request) -> JSONResponse:
    """Get the open API specification (in json format) for this API."""
    oas = request.app.openapi()
    # Convert markdown anchor links to ReDoc operation links, e.g. (#install-strix-put)->(#operation/install-strix-put)
    oas_string = re.sub(r"\(#([a-zA-Z0-9\-]+)\)", r"(#operation/\1)", json.dumps(oas))
    return JSONResponse(content=json.loads(oas_string))


@router.get("/redoc", response_class=HTMLResponse)
async def api_documentation(request: Request) -> HTMLResponse:
    """Render ReDoc HTML (documentation for this API)."""
    return get_redoc_html(
        openapi_url=str(request.url_for("api_specification")),
        redoc_favicon_url=str(request.url_for("static", path="favicon.ico")),
        title="Mink API documentation"
    )


@router.get("/swagger-openapi.json", include_in_schema=False)
async def swagger_api_spec(request: Request) -> JSONResponse:
    """Serve a modified OpenAPI schema (OAS) for Swagger."""
    oas = request.app.openapi()
    # Create a dictionary with paths as keys and their tag names as values (needed for Swagger links)
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


@router.get("/swagger", response_class=HTMLResponse)
async def swagger_api_documentation(request: Request) -> HTMLResponse:
    """Render Swagger UI HTML (documentation for this API)."""
    html_body = get_swagger_ui_html(
        openapi_url=str(request.url_for("swagger_api_spec")),
        swagger_favicon_url=str(request.url_for("static", path="favicon.ico")),
        title=request.app.title + " - Swagger UI",
    ).body
    # Decode the HTML body
    html_body = html_body.tobytes().decode() if isinstance(html_body, memoryview) else html_body.decode()
    # Modify JavaScript to apply API key authentication in each request if SBAUTH_PERSONAL_API_KEY is set
    api_key = settings.SBAUTH_PERSONAL_API_KEY
    if api_key:
        # Insert a requestInterceptor into the swagger UI html
        intercept = f"""requestInterceptor: (req) => {{ req.headers["X-API-Key"] = "{api_key}"; return req; }},\n"""
        html_body = re.sub(r"(url: '/swagger-openapi.json',\n)", r"\1" + " " * 8 + intercept, html_body)
    return HTMLResponse(html_body)


@router.get("/docs")
async def developers_guide(request: Request) -> RedirectResponse:
    """Render mkdocs HTML with the developer's guide."""
    docs_url = request.scope.get("root_path", "") + "/docs/"
    return RedirectResponse(url=docs_url)


@router.get("/openapi-to-markdown", include_in_schema=False, response_class=PlainTextResponse)
async def openapi_to_markdown(request: Request) -> PlainTextResponse:
    """Render OpenAPI schema in Markdown format."""
    openapi_schema = request.app.openapi()

    # Get the production server URL from the OpenAPI schema
    servers = openapi_schema.get("servers", [])
    production_server_url = None
    for server in servers:
        if server.get("description") == "Production server":
            production_server_url = server.get("url", "")
            break

    # Fix all anchor links in the OpenAPI schema, e.g. (#install-strix-put) --> (#install-strix)
    oas_string = re.sub(r"\(#([a-zA-Z0-9\-]+)-[a-zA-Z0-9]+\)", r"(#\1)", json.dumps(openapi_schema))

    # Replace the current host with the production server URL
    if production_server_url is not None and production_server_url != settings.MINK_URL:
        oas_string = re.sub(rf"{settings.MINK_URL}", production_server_url, oas_string)

    openapi_schema = json.loads(oas_string)

    # Organize paths by tags, preserving tag order from the OpenAPI spec
    tag_order = [tag["name"] for tag in openapi_schema.get("tags", [])]
    tag_descriptions = {tag["name"]: tag["description"] for tag in openapi_schema.get("tags", [])}
    tags_dict = {tag: [] for tag in tag_order}
    for path, operations in openapi_schema["paths"].items():
        for method, operation in operations.items():
            for tag in operation.get("tags", []):
                tags_dict[tag].append({
                    "path": path,
                    "method": method,
                    "operation": operation,
                    "summary": operation.get("summary", ""),
                })
            # Add another markdown header level to "Example" in description
            if "description" in operation:
                operation["description"] = re.sub(
                    r"\n\n### Example\n\n", r"\n\n#### Example\n\n", operation["description"], flags=re.DOTALL
                )

    # Load the Jinja2 markdown template
    template_path = Path("templates") / "openapi_to_markdown.j2"
    with template_path.open("r", encoding="utf-8") as f:
        markdown_template = f.read()
    template = Template(markdown_template)

    markdown = template.render(
        info=openapi_schema["info"],
        tags=tags_dict,
        tag_descriptions=tag_descriptions,
    )

    return PlainTextResponse(content=markdown)


@router.get("/info", response_model=InfoResponse)
async def api_info() -> JSONResponse:
    """Show info about data processing, e.g. job status codes, file size limits and Sparv importer modules."""
    from mink.core.status import Status  # noqa: PLC0415

    status_codes = {"info": "job status codes", "data": []}
    for s in Status:
        status_codes["data"].append({"name": s.value, "description": s.description})

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
                "description": "max size for one resource source file",
                "value": settings.MAX_FILE_LENGTH,
            },
            {
                "name": "max_resource_length",
                "description": "max size for one resource (total of all source files)",
                "value": settings.MAX_RESOURCE_LENGTH,
            },
        ],
    }

    resource_info = {}
    for rtype, spec in get_all_specs().items():
        payload = spec.info_builder() if spec.info_builder else {}
        if payload:
            resource_info[rtype.value] = payload

    return utils.response(
        return_code=return_codes.LISTING_CONTENT,
        info="Listing Mink API information",
        status_codes=status_codes,
        file_size_limits=file_size_limits,
        resource_info=resource_info,
)


@router.get("/return-codes", response_model=ReturnCodesResponse)
async def list_return_codes() -> JSONResponse:
    """List all return codes."""
    # Sort return codes into a dict keyed by tag
    codes = return_codes.get_all_return_codes()
    tags_dict = defaultdict(list)
    for code in codes:
        tags_dict[code.tag].append({"code": code.code, "message": code.message, "status_code": code.status_code})

    return utils.response(
        return_code=return_codes.LISTING_CONTENT,
        info="Listing all return codes",
        data=tags_dict,
    )
