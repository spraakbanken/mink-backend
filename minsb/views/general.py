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
        return utils.success_response("Min Språkbank successfully initialized!")
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


@bp.route("/upload-corpus", methods=["PUT"])
def upload_corpus():
    """Upload corpus files."""
    try:
        oc = utils.login(request)
    except Exception as e:
        return utils.error_response(f"Could not authenticate! {e}"), 401

    # Check if corpus ID and files were provided
    corpus_id = request.args.get("corpus_id") or request.form.get("corpus_id")
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
    source_dir = corpus_dir + "/" + current_app.config.get("SPARV_SOURCE_DIR")
    try:
        oc.mkdir(corpus_dir)
        oc.mkdir(source_dir)
        for f in files.values():
            oc.put_file_contents(source_dir + "/" + f.filename, f.read())
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

    corpus_id = request.args.get("corpus_id") or request.form.get("corpus_id")
    if not corpus_id:
        return utils.error_response("No corpus ID provided!"), 404

    if corpus_id not in utils.list_corpora(oc):
        return utils.error_response(f"Corpus '{corpus_id}' does not exist!"), 404

    corpus_dir = current_app.config.get("CORPORA_DIR") + "/" + corpus_id
    try:
        oc.delete(corpus_dir)
        return utils.success_response(f"Corpus '{corpus_id}' successfully removed!")
    except Exception as e:
        return utils.error_response(f"Could not remove corpus '{corpus_id}'! {e}"), 404


@bp.route("/update-corpus", methods=["PUT"])
def update_corpus():
    """Update corpus with new/modified files."""
    # TODO: Need specification! How should this work? Do we just add files and replace existing ones?
    # Or do we replace all source files? In case of the former: How can one delete files?
    return utils.error_response("Not yet implemented!"), 501


@bp.route("/upload-config", methods=["PUT"])
def upload_config():
    """Upload a corpus config file."""
    try:
        oc = utils.login(request)
    except Exception as e:
        return utils.error_response(f"Could not authenticate! {e}"), 401

    # Check if corpus ID and config file were provided
    corpus_id = request.args.get("corpus_id") or request.form.get("corpus_id")
    if not corpus_id:
        return utils.error_response("No corpus ID provided!"), 404
    attached_files = list(request.files.values())
    if not attached_files:
        return utils.error_response(f"No config file provided for upload!"), 404
    # Check if MIME type = YAML
    config_file = attached_files[0]
    if config_file.mimetype not in ("application/x-yaml", "text/yaml"):
        return utils.error_response("Config file needs to be YAML!"), 404

    corpus_dir = current_app.config.get("CORPORA_DIR") + "/" + corpus_id
    try:
        oc.put_file_contents(corpus_dir + "/" + "config.yaml", config_file.read())
        return utils.success_response("Config file successfully uploaded for '{corpus_id}'!")
    except Exception as e:
        return utils.error_response(f"Could not upload config file! {e}"), 404


@bp.route("/run-sparv", methods=["PUT"])
def run_sparv():
    """Run Sparv on given corpus."""
    # TODO: What input args do we need besides corpus_id? Maybe the export format (optionally)?
    return utils.error_response("Not yet implemented!"), 501


@bp.route("/sparv-status", methods=["GET"])
def sparv_status():
    """Check the annotation status for a given corpus."""
    # TODO: Check if this is even possible in Sparv.
    return utils.error_response("Not yet implemented!"), 501


@bp.route("/clear-annotations", methods=["DELETE"])
def clear_annotations():
    """Remove annotation files."""
    try:
        oc = utils.login(request)
    except Exception as e:
        return utils.error_response(f"Could not authenticate! {e}"), 401

    corpus_id = request.args.get("corpus_id") or request.form.get("corpus_id")
    if not corpus_id:
        return utils.error_response("No corpus ID provided!"), 404

    annotation_dir = current_app.config.get("CORPORA_DIR") + "/" + corpus_id + current_app.config.get("SPARV_WORK_DIR")
    try:
        oc.delete(annotation_dir)
        return utils.success_response(f"Annotations for '{corpus_id}' successfully removed!")
    except Exception as e:
        return utils.error_response(f"Could not remove annotations for '{corpus_id}'! {e}"), 404


@bp.route("/list-exports", methods=["GET"])
def list_exports():
    """List exports available for download for a given corpus."""
    return utils.error_response("Not yet implemented!"), 501


@bp.route("/download-export", methods=["GET"])
def download_export():
    """Download and export for a corpus."""
    # TODO: Need specification! Should result come as zip file? Should user specify which export to download?
    # Should there be a default download (or default = download all available exports)?
    return utils.error_response("Not yet implemented!"), 501
