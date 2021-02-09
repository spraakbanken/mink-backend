"""Collection of general routes."""

from flask import Blueprint
from flask import current_app as app

from minsb import utils

bp = Blueprint("general", __name__)


@bp.route("/")
def hello():
    """Show available routes."""
    routes = [str(rule) for rule in app.url_map.iter_rules()]
    return utils.response("Listing available routes", routes=routes)
