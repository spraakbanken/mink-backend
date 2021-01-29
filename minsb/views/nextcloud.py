"""Routes related to Nextcloud."""

import os
import re

from flask import Blueprint
from flask import current_app as app
from flask import request, send_file

from minsb import paths, utils

bp = Blueprint("nextcloud", __name__)


@bp.route("/init", methods=["POST"])
@utils.login(require_init=False, require_corpus_id=False, require_corpus_exists=False)
def init(oc, user):
    """Create corpora directory."""
    try:
        corpora_dir = paths.get_corpora_dir(domain="nc", oc=oc, mkdir=True)
        # TODO: upload some info file?
        app.logger.debug(f"Initialized corpora dir '{corpora_dir}'")
        return utils.response("Min Språkbank successfully initialized!")
    except Exception as e:
        return utils.response(f"Failed to initialize corpora dir '{corpora_dir}'!", err=True, info=str(e)), 404


@bp.route("/list-corpora", methods=["GET"])
@utils.login(require_corpus_id=False, require_corpus_exists=False)
def list_corpora(oc, user, corpora):
    """List all available corpora."""
    return utils.response("Listing available corpora", corpora=corpora)


@bp.route("/upload-corpus", methods=["PUT"])
@utils.login(require_corpus_exists=False)
def upload_corpus(oc, user, corpora, corpus_id):
    """Upload corpus files."""
    # Check if corpus_id is valid
    if not bool(re.match(r"^[a-z0-9-]+$", corpus_id)):
        return utils.response("Corpus ID is invalid!", err=True), 404

    # Check if corpus files were provided
    files = list(request.files.listvalues())[0]
    if not files:
        return utils.response("No corpus files provided for upload!", err=True), 404

    # Make sure corpus dir does not exist already
    if corpus_id in corpora:
        return utils.response(f"Corpus '{corpus_id}' already exists!", err=True), 404

    try:
        # Create corpus dir with subdirs and upload data
        corpus_dir = paths.get_corpus_dir(domain="nc", corpus_id=corpus_id, oc=oc, mkdir=True)
        source_dir = paths.get_source_dir(domain="nc", corpus_id=corpus_id, oc=oc, mkdir=True)
        paths.get_export_dir(domain="nc", corpus_id=corpus_id, oc=oc, mkdir=True)
        for f in files:
            # TODO: make sure corpus files have correct format (xml or txt)?
            oc.put_file_contents(os.path.join(source_dir, f.filename), f.read())
        return utils.response(f"Corpus '{corpus_id}' successfully uploaded!")
    except Exception as e:
        try:
            # Try to remove partially uploaded corpus data
            corpus_dir = paths.get_corpus_dir(domain="nc", corpus_id=corpus_id)
            oc.delete(corpus_dir)
        except Exception as err:
            app.logger.error(f"Failed to remove partially uploaded corpus data for '{corpus_id}'! {err}")
        return utils.response(f"Failed to upload corpus '{corpus_id}'!", err=True, info=str(e)), 404


@bp.route("/remove-corpus", methods=["DELETE"])
@utils.login()
def remove_corpus(oc, user, corpora, corpus_id):
    """Remove corpus."""
    try:
        corpus_dir = paths.get_corpus_dir(domain="nc", corpus_id=corpus_id)
        oc.delete(corpus_dir)
        return utils.response(f"Corpus '{corpus_id}' successfully removed!")
    except Exception as e:
        return utils.response(f"Failed to remove corpus '{corpus_id}'!", err=True, info=str(e)), 404


@bp.route("/update-corpus", methods=["PUT"])
@utils.login()
def update_corpus(oc, user, corpora, corpus_id):
    """Update corpus with new/modified files."""
    # TODO: Need specification! How should this work? Do we just add files and replace existing ones?
    # Or do we replace all source files? In case of the former: How can one delete files?
    return utils.response("Not yet implemented!", err=True), 501


@bp.route("/upload-config", methods=["PUT"])
@utils.login()
def upload_config(oc, user, corpora, corpus_id):
    """Upload a corpus config file."""
    # Check if config file was provided
    attached_files = list(request.files.values())
    if not attached_files:
        return utils.response("No config file provided for upload!", err=True), 404

    # Check if config file is YAML
    config_file = attached_files[0]
    if config_file.mimetype not in ("application/x-yaml", "text/yaml"):
        return utils.response("Config file needs to be YAML!", err=True), 404

    try:
        oc.put_file_contents(paths.get_config_file(domain="nc", corpus_id=corpus_id), config_file.read())
        return utils.response(f"Config file successfully uploaded for '{corpus_id}'!")
    except Exception as e:
        return utils.response(f"Failed to upload config file for '{corpus_id}'!", err=True, info=str(e))


@bp.route("/list-exports", methods=["GET"])
@utils.login()
def list_exports(oc, user, corpora, corpus_id):
    """List exports available for download for a given corpus."""
    path = paths.get_export_dir(domain="nc", corpus_id=corpus_id)
    try:
        objlist = utils.list_contents(oc, path)
        return utils.response(f"Current export files for '{corpus_id}'", contents=objlist)
    except Exception as e:
        return utils.response(f"Failed to list files in '{corpus_id}'!", err=True, info=str(e)), 404


@bp.route("/download-exports", methods=["GET"])
@utils.login()
def download_export(oc, user, corpora, corpus_id):
    """Download one or more export files for a corpus as a zip file."""
    download_files = request.args.get("file") or request.form.get("files") or ""
    download_files = [i for i in download_files.split(",") if i]
    download_folders = request.args.get("directories") or request.form.get("directories") or ""
    download_folders = [i for i in download_folders.split(",") if i]

    nc_export_dir = paths.get_export_dir(domain="nc", corpus_id=corpus_id)
    local_corpus_dir = paths.get_corpus_dir(user=user, corpus_id=corpus_id, mkdir=True)
    local_export_dir = paths.get_export_dir(user=user, corpus_id=corpus_id, mkdir=True)

    zip_out = os.path.join(local_corpus_dir, f"{corpus_id}_export.zip")

    if not (download_files or download_folders):
        try:
            # Get files from Nextcloud
            oc.get_directory_as_zip(nc_export_dir, zip_out)
            return send_file(zip_out, mimetype="application/zip")
        except Exception as e:
            return utils.response(f"Failed to download exports for corpus '{corpus_id}'!", err=True, info=str(e)), 404

    # TODO: Download and zip files/folders specified in args
    # print(download_files, download_folders)
    # export_contents = utils.list_contents(oc, nc_export_dir, exclude_dirs=False)
    # file_index = utils.create_file_index(export_contents, user)
    # utils.download_dir(oc, nc_export_dir, local_corpus_dir, corpus_id, file_index)
    # utils.create_zip(local_export_dir, zip_out)
    return utils.response("Not yet implemented!", err=True), 501
