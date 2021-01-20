"""Collection of general routes."""

from flask import Blueprint, current_app, request
import owncloud

from minsb import utils

bp = Blueprint("general", __name__)


@bp.route("/")
def hello():
    """Show available routes."""
    current_app.logger.debug(current_app.config)
    routes = [str(rule) for rule in current_app.url_map.iter_rules()]
    return utils.success_response("Listing available routes", routes=routes)


@bp.route("/init-min-sb", methods=["POST"])
def init_min_sb():
    """Create corpora directory."""
    try:
        oc = utils.login(request)
    except Exception as e:
        return utils.error_response(f"Could not authenticate! {e}"), 401

    corpora_dir = current_app.config.get("CORPORA_DIR")
    try:
        oc.mkdir(corpora_dir)
        # TODO: upload some info file?
        current_app.logger.debug(f"Initialized corpora dir '{corpora_dir}'")
    except Exception as e:
        return utils.error_response(f"Could not initialize corpora dir '{corpora_dir}'! {e}"), 404


@bp.route("/list-corpora", methods=["GET"])
def list_corpora():
    """List all available corpora."""
    try:
        oc = utils.login(request)
    except Exception as e:
        return utils.error_response(f"Could not authenticate! {e}"), 401

    try:
        corpora = utils.list_corpora(oc)
        return utils.success_response("Listing available corpora", corpora=corpora)
    except Exception as e:
        return utils.error_response(f"Could not access corpora dir! {e}"), 404


@bp.route("/upload-corpus", methods=["POST"])
def upload_corpus():
    """Upload corpus files."""
    try:
        oc = utils.login(request)
    except Exception as e:
        return utils.error_response(f"Could not authenticate! {e}"), 401

    # Check if corpus ID and files were provided
    corpus_id = request.form.get("corpus_id")
    if not corpus_id:
        return utils.error_response("No corpus ID provided!"), 404
    files = request.files
    if not files:
        return utils.error_response("No corpus files provided for upload!"), 404

    # Make sure corpus dir does not exist already
    corpora = utils.list_corpora(oc)
    if corpus_id in corpora:
        return utils.error_response(f"Corpus '{corpus_id}' already exists!"), 404

    # Create corpus dir and upload data
    corpus_dir = current_app.config.get("CORPORA_DIR") + "/" + corpus_id
    try:
        oc.mkdir(corpus_dir)
        for f in files.values():
            oc.put_file_contents(corpus_dir + "/" + f.filename, f.read())
        return utils.success_response(f"Corpus '{corpus_id}' successfully uploaded!")
    except Exception as e:
        try:
            # Try to remove partially uploaded corpus data
            oc.delete(corpus_dir)
        except Exception as e:
            current_app.logger.error(f"Could not remove partially uploaded corpus data for '{corpus_id}'! {e}")
        return utils.error_response(f"Could not upload corpus '{corpus_id}'! {e}"), 404


@bp.route("/remove-corpus", methods=["DELETE"])
def remove_corpus():
    """Remove corpus."""
    try:
        oc = utils.login(request)
    except Exception as e:
        return utils.error_response(f"Could not authenticate! {e}"), 401

    corpus_id = request.args.get("corpus_id")
    if not corpus_id:
        return utils.error_response("No corpus ID provided!"), 404

    corpus_dir = current_app.config.get("CORPORA_DIR") + "/" + corpus_id
    try:
        oc.delete(corpus_dir)
        return utils.success_response(f"Corpus '{corpus_id}' successfully removed!")
    except Exception as e:
        return utils.error_response(f"Could not remove corpus '{corpus_id}'! {e}"), 404


@bp.route("/update-corpus", methods=["PUT"])
def update_corpus():
    """Update corpus with new/modified files."""
    return utils.error_response("Not yet implemented!"), 501


# Other routes:
# - upload config file
# - run corpus
# - check status
# - clear annotations
# - list and download export(s)
