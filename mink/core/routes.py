"""Collection of general routes."""

from pathlib import Path

import yaml
from flask import Blueprint, Response, jsonify, redirect, render_template, send_from_directory, url_for
from flask import current_app as app
from apiflask import APIBlueprint

from mink import __version__
from mink.core import utils

bp = APIBlueprint("general", __name__)


@bp.route("/")
def hello() -> Response:
    """Redirect to /api_doc."""
    return redirect(app.config.get("MINK_URL") + url_for("general.api_doc"))


@bp.route("/api-spec")
def api_spec() -> Response:
    """Return open API specification in json."""
    host = app.config.get("MINK_URL")
    spec_file = Path(app.static_folder) / "oas.yaml"
    strspec = spec_file.read_text(encoding="UTF-8")
    # Replace {{host}} in examples with real URL
    strspec = strspec.replace("{{host}}", host)
    # Replace {{version}} with current app version
    strspec = strspec.replace("{{version}}", __version__)
    return jsonify(yaml.safe_load(strspec))


@bp.route("/api-doc")
def api_doc() -> str:
    """Render HTML API documentation."""
    return render_template(
        "apidoc.html",
        title="Mink API documentation",
        favicon=app.config.get("MINK_URL") + url_for("static", filename="favicon.ico"),
        logo=app.config.get("MINK_URL") + url_for("static", filename="mink.svg"),
        spec_url=app.config.get("MINK_URL") + url_for("general.api_spec"),
    )


@bp.route("/developers-guide")
def developers_guide() -> str:
    """Render docsify HTML with the developer's guide."""
    return render_template(
        "docsify.html", favicon=app.config.get("MINK_URL") + url_for("static", filename="favicon.ico")
    )


@bp.route("/developers-guide/<path:path>")
def developers_guide_files(path: str) -> Response:
    """Serve sub pages to the developer's guide needed by docsify.

    Args:
        path: The path to the sub page.

    Returns:
        The requested sub page.
    """
    return send_from_directory("templates", path)


# @bp.route("/routes")
# def routes():
#     """Show available routes."""
#     routes = [str(rule) for rule in app.url_map.iter_rules()]
#     return utils.response("Listing available routes", routes=routes)


@bp.route("/info")
def info() -> Response:
    """Show info about data processing.

    Returns:
        A JSON response with information about data processing.
    """
    from mink.core.status import Status  # noqa: PLC0415

    status_codes = {"info": "job status codes", "data": []}
    for s in Status:
        status_codes["data"].append({"name": s.name, "description": s.value})

    importer_modules = {"info": "Sparv importers that need to be used for different file extensions", "data": []}
    for ext, importer in app.config.get("SPARV_IMPORTER_MODULES").items():
        importer_modules["data"].append({"file_extension": ext, "importer": importer})

    file_size_limits = {
        "info": "size limits (in bytes) for uploaded files",
        "data": [
            {
                "name": "max_content_length",
                "description": "max size for one request (which may contain multiple files)",
                "value": app.config.get("MAX_CONTENT_LENGTH"),
            },
            {
                "name": "max_file_length",
                "description": "max size for one corpus source file",
                "value": app.config.get("MAX_FILE_LENGTH"),
            },
            {
                "name": "max_corpus_length",
                "description": "max size for one corpus",
                "value": app.config.get("MAX_CORPUS_LENGTH"),
            },
        ],
    }

    recommended_file_size = {
        "info": "approximate recommended file sizes (in bytes) when processing many files with Sparv",
        "data": [
            {
                "name": "max_file_length",
                "description": "recommended min size for one corpus source file",
                "value": app.config.get("RECOMMENDED_MIN_FILE_LENGTH"),
            },
            {
                "name": "min_file_length",
                "description": "recommended max size for one corpus source file",
                "value": app.config.get("RECOMMENDED_MAX_FILE_LENGTH"),
            },
        ],
    }

    return utils.response(
        "Listing information about data processing",
        status_codes=status_codes,
        importer_modules=importer_modules,
        file_size_limits=file_size_limits,
        recommended_file_size=recommended_file_size,
        return_code="listing_info",
    )
