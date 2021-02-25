"""Collection of general routes."""

from flask import Blueprint
from flask import current_app as app
from flask import redirect, render_template, send_from_directory, url_for

bp = Blueprint("general", __name__)


@bp.route("/")
def hello():
    """Redirect to /api_doc."""
    return redirect(url_for('general.api_doc', _external=True))


# @bp.route("/routes")
# def routes():
#     """Show available routes."""
#     routes = [str(rule) for rule in app.url_map.iter_rules()]
#     return utils.response("Listing available routes", routes=routes)


@bp.route("/api-spec")
def api_spec():
    """Return open API specification in yaml."""
    return send_from_directory(app.static_folder, "oas.yaml")
    # spec_file = os.path.join(app.static_folder, "oas.yaml")
    # with open(spec_file, encoding="UTF-8") as f:
    #     return jsonify(yaml.load(f, Loader=yaml.FullLoader))


@bp.route("/api-doc")
def api_doc():
    """Render HTML API documentation."""
    app.logger.info("URL: %s", url_for("general.api_spec", _external=True))
    return render_template('apidoc.html',
                           title="Min SB API documentation",
                           favicon=url_for("static", filename="sbx_favicon.svg", _external=True),
                           spec_url=url_for("general.api_spec", _external=True)
                           )
