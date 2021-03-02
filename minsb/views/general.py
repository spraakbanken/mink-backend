"""Collection of general routes."""

import os

import yaml
from flask import Blueprint
from flask import current_app as app
from flask import jsonify, redirect, render_template, request, url_for

from minsb import queue, utils

bp = Blueprint("general", __name__)


@bp.route("/")
def hello():
    """Redirect to /api_doc."""
    return redirect(url_for('general.api_doc', _external=True))


@bp.route("/api-spec")
def api_spec():
    """Return open API specification in json."""
    if app.config.get("DEBUG"):
        host = request.host_url
    else:
        # Proxy fix: When not in debug mode, use MIN_SB_URL instead of host URL
        host = app.config.get("MIN_SB_URL")
    spec_file = os.path.join(app.static_folder, "oas.yaml")
    with open(spec_file, encoding="UTF-8") as f:
        strspec = f.read()
        # Replace {{host}} in examples with real URL
        strspec = strspec.replace("{{host}}", host)
        return jsonify(yaml.safe_load(strspec))


@bp.route("/api-doc")
def api_doc():
    """Render HTML API documentation."""
    if app.config.get("DEBUG"):
        return render_template('apidoc.html',
                               title="Min SB API documentation",
                               favicon=url_for("static", filename="sbx_favicon.svg", _external=True),
                               spec_url=url_for("general.api_spec", _external=True)
                               )
    else:
        # Proxy fix: When not in debug mode, use MIN_SB_URL instead
        return render_template('apidoc.html',
                               title="Min SB API documentation",
                               favicon=app.config.get("MIN_SB_URL") + url_for("static", filename="sbx_favicon.svg"),
                               spec_url=app.config.get("MIN_SB_URL") + url_for("general.api_spec")
                               )


# @bp.route("/routes")
# def routes():
#     """Show available routes."""
#     routes = [str(rule) for rule in app.url_map.iter_rules()]
#     return utils.response("Listing available routes", routes=routes)


@bp.route("/status-codes")
def status_codes():
    """Show existing job status codes."""
    from minsb.jobs import Status
    status_codes = []
    for s in Status:
        status_codes.append({"code": s._value_, "name": s.name, "description": s.desc})
    return utils.response("Listing existing job status codes", status_codes=status_codes)


@bp.route("/init-queue", methods=["GET"])
@utils.gatekeeper(require_corpus_id=False)
def init_queue():
    """Initialize the memcached queue.

    For internal use only!
    """
    try:
        queue.init_queue()
        return utils.response("Successfully initialized the job queue!")
    except Exception as e:
        return utils.response("Failed to init the job queue!", err=True, info=str(e)), 404
