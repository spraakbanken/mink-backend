"""Routes related to Nextcloud."""

import os
import re

from flask import Blueprint
from flask import current_app as app
from flask import request

from minsb import utils

bp = Blueprint("nextcloud", __name__)


@bp.route("/init", methods=["POST"])
@utils.login(require_init=False, require_corpus_id=False, require_corpus_exists=False)
def init(oc):
    """Create corpora directory."""
    corpora_dir = app.config.get("CORPORA_DIR")
    try:
        oc.mkdir(corpora_dir)
        # TODO: upload some info file?
        app.logger.debug(f"Initialized corpora dir '{corpora_dir}'")
        return utils.response("Min Språkbank successfully initialized!")
    except Exception as e:
        return utils.response(f"Failed to initialize corpora dir '{corpora_dir}'!", err=True, info=str(e)), 404


@bp.route("/list-corpora", methods=["GET"])
@utils.login(require_corpus_id=False, require_corpus_exists=False)
def list_corpora(oc, corpora):
    """List all available corpora."""
    return utils.response("Listing available corpora", corpora=corpora)


@bp.route("/upload-corpus", methods=["PUT"])
@utils.login(require_corpus_exists=False)
def upload_corpus(oc, corpora, corpus_id):
    """Upload corpus files."""
    # Check if corpus_id is valid
    if not bool(re.match(r"^[a-z0-9-]+$", corpus_id)):
        return utils.response("Corpus ID is invalid!", err=True), 404

    # Check if corpus files were provided
    files = request.files
    if not files:
        return utils.response("No corpus files provided for upload!", err=True), 404
    # TODO: make sure corpus files have correct format (xml or txt)?

    # Make sure corpus dir does not exist already
    if corpus_id in corpora:
        return utils.response(f"Corpus '{corpus_id}' already exists!", err=True), 404

    # Create corpus dir and upload data
    corpus_dir = os.path.join(app.config.get("CORPORA_DIR"), corpus_id)
    source_dir = os.path.join(corpus_dir, app.config.get("SPARV_SOURCE_DIR"))
    export_dir = os.path.join(corpus_dir, app.config.get("SPARV_EXPORT_DIR"))
    try:
        oc.mkdir(corpus_dir)
        oc.mkdir(source_dir)
        oc.mkdir(export_dir)
        for f in files.values():
            oc.put_file_contents(os.path.join(source_dir, f.filename), f.read())
        return utils.response(f"Corpus '{corpus_id}' successfully uploaded!")
    except Exception as e:
        try:
            # Try to remove partially uploaded corpus data
            oc.delete(corpus_dir)
        except Exception as e:
            app.logger.error(f"Failed to remove partially uploaded corpus data for '{corpus_id}'! {e}")
        return utils.response(f"Failed to upload corpus '{corpus_id}'!", err=True, info=str(e)), 404


@bp.route("/remove-corpus", methods=["DELETE"])
@utils.login()
def remove_corpus(oc, corpora, corpus_id):
    """Remove corpus."""
    corpus_dir = os.path.join(app.config.get("CORPORA_DIR"), corpus_id)
    try:
        oc.delete(corpus_dir)
        return utils.response(f"Corpus '{corpus_id}' successfully removed!")
    except Exception as e:
        return utils.response(f"Failed to remove corpus '{corpus_id}'!", err=True, info=str(e)), 404


@bp.route("/update-corpus", methods=["PUT"])
@utils.login()
def update_corpus(oc, corpora, corpus_id):
    """Update corpus with new/modified files."""
    # TODO: Need specification! How should this work? Do we just add files and replace existing ones?
    # Or do we replace all source files? In case of the former: How can one delete files?
    return utils.response("Not yet implemented!", err=True), 501


@bp.route("/upload-config", methods=["PUT"])
@utils.login()
def upload_config(oc, corpora, corpus_id):
    """Upload a corpus config file."""
    # Check if config file was provided
    attached_files = list(request.files.values())
    if not attached_files:
        return utils.response("No config file provided for upload!", err=True), 404

    # Check if config file is YAML
    config_file = attached_files[0]
    if config_file.mimetype not in ("application/x-yaml", "text/yaml"):
        return utils.response("Config file needs to be YAML!", err=True), 404

    corpus_dir = os.path.join(app.config.get("CORPORA_DIR"), corpus_id)
    try:
        oc.put_file_contents(os.path.join(corpus_dir, app.config.get("SPARV_CORPUS_CONFIG")),
                             config_file.read())
        return utils.response(f"Config file successfully uploaded for '{corpus_id}'!")
    except Exception as e:
        return utils.response(f"Failed to upload config file for '{corpus_id}'!", err=True, info=str(e))


@bp.route("/list-exports", methods=["GET"])
@utils.login()
def list_exports(oc, corpora, corpus_id):
    """List exports available for download for a given corpus."""
    path = os.path.join(app.config.get("CORPORA_DIR"), corpus_id, app.config.get("SPARV_EXPORT_DIR"))
    try:
        objlist = utils.list_contents(oc, path)
        return utils.response(f"Current export files for '{corpus_id}'", contents=objlist)
    except Exception as e:
        return utils.response(f"Failed to list files in '{corpus_id}'!", err=True, info=str(e)), 404
    return utils.response("Not yet implemented!", err=True), 501


@bp.route("/download-export", methods=["GET"])
@utils.login()
def download_export(oc, corpora, corpus_id):
    """Download and export for a corpus."""
    # TODO: Need specification! Should result come as zip file? Should user specify which export to download?
    # Should there be a default download (or default = download all available exports)?
    return utils.response("Not yet implemented!", err=True), 501
