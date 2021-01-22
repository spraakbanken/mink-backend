"""Collection of general routes."""

from flask import Blueprint, current_app

from minsb import utils

bp = Blueprint("general", __name__)


@bp.route("/")
def hello():
    """Show available routes."""
    routes = [str(rule) for rule in current_app.url_map.iter_rules()]
    return utils.success_response("Listing available routes", routes=routes)
