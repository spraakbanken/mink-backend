"""Routes related to Nextcloud."""

import re
from pathlib import Path

from flask import Blueprint
from flask import current_app as app
from flask import request, send_file

from minsb import jobs, paths, queue, utils

bp = Blueprint("nextcloud", __name__)


@bp.route("/init", methods=["POST"])
@utils.login(require_init=False, require_corpus_id=False, require_corpus_exists=False)
def init(oc, _user, dir_listing):
    """Create corpora directory."""
    try:
        corpora_dir = app.config.get("NC_CORPORA_DIR")
        if corpora_dir in [e.get_name() for e in dir_listing]:
            # Corpora dir already exists
            return utils.response(f"Failed to initialize Min Språkbank! Directory '{corpora_dir}' already exists!",
                                  err=True), 404
        # Create corpora dir
        corpora_dir = str(paths.get_corpora_dir(domain="nc", oc=oc, mkdir=True))
        # TODO: upload some info file?
        app.logger.debug(f"Initialized corpora dir '{corpora_dir}'")
        return utils.response("Min Språkbank successfully initialized!")
    except Exception as e:
        return utils.response("Failed to initialize corpora dir!", err=True, info=str(e)), 404


@bp.route("/list-corpora", methods=["GET"])
@utils.login(require_corpus_id=False, require_corpus_exists=False)
def list_corpora(_oc, _user, corpora):
    """List all available corpora."""
    return utils.response("Listing available corpora", corpora=corpora)


@bp.route("/upload-corpus", methods=["PUT"])
@utils.login(require_corpus_exists=False)
def upload_corpus(oc, _user, corpora, corpus_id):
    """Upload corpus files."""
    # Check if corpus files were provided
    files = list(request.files.listvalues())
    if not files:
        return utils.response("No corpus files provided for upload!", err=True), 404

    try:
        if corpus_id not in corpora:
            # Create corpus dir with subdirs
            create_corpus_dir(oc, corpus_id, corpora)
        # Upload data
        source_dir = paths.get_source_dir(domain="nc", corpus_id=corpus_id, oc=oc)
        for f in files[0]:
            name = utils.check_file(f.filename, app.config.get("SPARV_VALID_INPUT_EXT"))
            if not name:
                return utils.response(f"File '{f.filename}' has an invalid file extension!"), 404
            oc.put_file_contents(str(source_dir / name), f.read())
        return utils.response(f"Corpus '{corpus_id}' successfully uploaded!")
    except Exception as e:
        return utils.response(f"Failed to upload corpus '{corpus_id}'!", err=True, info=str(e)), 404


def create_corpus_dir(oc, corpus_id, corpora):
    """Create corpus dir for corpus_id."""
    # Check if corpus_id is valid
    if not bool(re.match(r"^[a-z0-9-]+$", corpus_id)):
        raise Exception("Corpus ID is invalid!")

    # Make sure corpus dir does not exist already
    if corpus_id in corpora:
        raise Exception(f"Corpus '{corpus_id}' already exists!")

    # Create corpus dir with subdirs
    try:
        corpus_dir = str(paths.get_corpus_dir(domain="nc", corpus_id=corpus_id, oc=oc, mkdir=True))
        source_dir = paths.get_source_dir(domain="nc", corpus_id=corpus_id, oc=oc, mkdir=True)
        paths.get_export_dir(domain="nc", corpus_id=corpus_id, oc=oc, mkdir=True)
        return corpus_dir, source_dir
    except Exception as e:
        try:
            # Try to remove partially uploaded corpus data
            oc.delete(corpus_dir)
        except Exception as err:
            app.logger.error(f"Failed to remove partially uploaded corpus data for '{corpus_id}'! {err}")
        raise Exception(f"Failed to create corpus dir! {e}")


@bp.route("/remove-corpus", methods=["DELETE"])
@utils.login()
def remove_corpus(oc, user, _corpora, corpus_id):
    """Remove corpus."""
    try:
        corpus_dir = str(paths.get_corpus_dir(domain="nc", corpus_id=corpus_id))
        oc.delete(corpus_dir)
    except Exception as e:
        return utils.response(f"Failed to remove corpus '{corpus_id}'!", err=True, info=str(e)), 404

    try:
        # Try to safely remove files from Sparv server and remove the job
        job = jobs.get_job(user, corpus_id)
        job.remove_from_sparv()
        queue.remove(job)
        job.remove()
    except Exception as e:
        app.logger.error(f"Failed to remove corpus '{corpus_id}'! {e}")

    return utils.response(f"Corpus '{corpus_id}' successfully removed!")


@bp.route("/update-corpus", methods=["PUT"])
@utils.login()
def update_corpus(oc, _user, _corpora, corpus_id):
    """Update corpus with new/modified files or delete files.

    Attached files will be added to the corpus or replace existing ones.
    File paths listed in 'remove' (comma separated) will be removed.
    """
    add_files = list(request.files.listvalues())[0]
    remove_files = request.args.get("remove") or request.form.get("remove") or ""
    remove_files = [i for i in remove_files.split(",") if i]

    source_dir = paths.get_source_dir(domain="nc", corpus_id=corpus_id)

    # Add/update files
    for af in add_files:
        try:
            name = utils.check_file(af.filename, app.config.get("SPARV_VALID_INPUT_EXT"))
            if not name:
                return utils.response(f"File '{af.filename}' has an invalid file extension!"), 404
            oc.put_file_contents(str(source_dir / name), af.read())
        except Exception as e:
            return utils.response(f"Failed to add file '{af}'!", err=True, info=str(e)), 404

    # Remove files
    for rf in remove_files:
        nc_path = str(source_dir / Path(rf))
        try:
            oc.delete(nc_path)
        except Exception as e:
            return utils.response(f"Failed to remove file '{nc_path}'!", err=True, info=str(e)), 404

    return utils.response(f"Corpus '{corpus_id}' successfully updated!")


@bp.route("/upload-config", methods=["PUT"])
@utils.login(require_corpus_exists=False)
def upload_config(oc, _user, corpora, corpus_id):
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
        if corpus_id not in corpora:
            # Create corpus dir with subdirs
            create_corpus_dir(oc, corpus_id, corpora)
        oc.put_file_contents(str(paths.get_config_file(domain="nc", corpus_id=corpus_id)), config_file.read())
        return utils.response(f"Config file successfully uploaded for '{corpus_id}'!")
    except Exception as e:
        return utils.response(f"Failed to upload config file for '{corpus_id}'!", err=True, info=str(e))


@bp.route("/list-exports", methods=["GET"])
@utils.login()
def list_exports(oc, _user, _corpora, corpus_id):
    """List exports available for download for a given corpus."""
    path = str(paths.get_export_dir(domain="nc", corpus_id=corpus_id))
    try:
        objlist = utils.list_contents(oc, path)
        return utils.response(f"Current export files for '{corpus_id}'", contents=objlist)
    except Exception as e:
        return utils.response(f"Failed to list files in '{corpus_id}'!", err=True, info=str(e)), 404


@bp.route("/download-exports", methods=["GET"])
@utils.login()
def download_export(oc, user, _corpora, corpus_id):
    """Download one or more export files for a corpus as a zip file."""
    download_files = request.args.get("file") or request.form.get("files") or ""
    download_files = [i for i in download_files.split(",") if i]
    download_folders = request.args.get("directories") or request.form.get("directories") or ""
    download_folders = [i for i in download_folders.split(",") if i]

    nc_export_dir = str(paths.get_export_dir(domain="nc", corpus_id=corpus_id))
    local_corpus_dir = paths.get_corpus_dir(user=user, corpus_id=corpus_id, mkdir=True)
    local_export_dir = str(paths.get_export_dir(user=user, corpus_id=corpus_id, mkdir=True))

    zip_out = str(local_corpus_dir / Path(f"{corpus_id}_export.zip"))

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
    # utils.download_dir(oc, nc_export_dir, str(local_corpus_dir), corpus_id, file_index)
    # utils.create_zip(local_export_dir, zip_out)
    return utils.response("Not yet implemented!", err=True), 501
