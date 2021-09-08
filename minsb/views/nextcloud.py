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
            return utils.response(f"Nothing to be done. Min Språkbank has already been initialized."), 200
        # Create corpora dir
        corpora_dir = str(paths.get_corpora_dir(domain="nc", oc=oc, mkdir=True))
        # TODO: upload some info file?
        app.logger.debug(f"Initialized corpora dir '{corpora_dir}'")
        return utils.response("Min Språkbank successfully initialized!"), 201
    except Exception as e:
        return utils.response("Failed to initialize corpora dir!", err=True, info=str(e)), 404


# ------------------------------------------------------------------------------
# Corpus operations
# ------------------------------------------------------------------------------

@bp.route("/create-corpus", methods=["POST"])
@utils.login(require_corpus_exists=False)
def create_corpus(oc, _user, corpora, corpus_id):
    """Create a new corpus."""
    # Check if corpus_id is valid
    if not bool(re.match(r"^[a-z0-9-]+$", corpus_id)):
        return utils.response(f"Corpus ID '{corpus_id}' is invalid!", err=True), 404

    # Make sure corpus dir does not exist already
    if corpus_id in corpora:
        return utils.response(f"Corpus '{corpus_id}' already exists!", err=True), 404

    # Create corpus dir with subdirs
    try:
        corpus_dir = str(paths.get_corpus_dir(domain="nc", corpus_id=corpus_id, oc=oc, mkdir=True))
        paths.get_source_dir(domain="nc", corpus_id=corpus_id, oc=oc, mkdir=True)
        paths.get_export_dir(domain="nc", corpus_id=corpus_id, oc=oc, mkdir=True)
        return utils.response(f"Corpus '{corpus_id}' created successfully!")
    except Exception as e:
        try:
            # Try to remove partially uploaded corpus data
            oc.delete(corpus_dir)
        except Exception as err:
            app.logger.error(f"Failed to remove partially uploaded corpus data for '{corpus_id}'! {err}")
        return utils.response("Failed to create corpus dir!", err=True, info=str(e)), 404


@bp.route("/list-corpora", methods=["GET"])
@utils.login(require_corpus_id=False, require_corpus_exists=False)
def list_corpora(_oc, _user, corpora):
    """List all available corpora."""
    return utils.response("Listing available corpora", corpora=corpora)


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


# @bp.route("/rename-corpus", methods=["POST"])
# @utils.login()
# def rename_corpus(oc, user, _corpora, corpus_id):
#     """Rename corpus."""
#     new_id = request.args.get("new_id") or request.form.get("new_id") or ""
#     if not new_id:
#         return utils.response("No new corpus ID was provided!", err=True), 404
#     try:
#         job = jobs.get_job(user, corpus_id)
#         if jobs.Status.none < job.status < jobs.Status.done_annotating or job.status == jobs.Status.syncing_results:
#             return utils.response("Cannot rename corpus while a job is running!", err=True), 404
#         # Rename on Nextcloud
#         corpus_dir = paths.get_corpus_dir(domain="nc", corpus_id=corpus_id)
#         new_corpus_dir = corpus_dir.parent.joinpath(new_id)
#         oc.move(corpus_dir, new_corpus_dir)
#         # Rename corpus dir on Sparv server and job in cache
#         queue.remove(job)
#         job.change_id(new_id)
#         queue.add(job)
#         # TODO: Change ID in config file
#         return utils.response(f"Successfully renamed corpus to '{new_id}'!")
#     except Exception as e:
#         # TODO: Undo renaming if it succeeded partially
#         return utils.response("Failed to rename corpus!", err=True, info=str(e)), 404


# ------------------------------------------------------------------------------
# Source file operations
# ------------------------------------------------------------------------------

@bp.route("/upload-sources", methods=["PUT"])
@utils.login()
def upload_sources(oc, _user, corpora, corpus_id):
    """Upload corpus source files.

    Attached files will be added to the corpus or replace existing ones.
    """
    # Check if corpus files were provided
    files = list(request.files.listvalues())
    if not files:
        return utils.response("No corpus files provided for upload!", err=True), 404

    try:
        # Upload data
        source_dir = paths.get_source_dir(domain="nc", corpus_id=corpus_id, oc=oc)
        for f in files[0]:
            name = utils.check_file(f.filename, app.config.get("SPARV_VALID_INPUT_EXT"))
            if not name:
                return utils.response(f"File '{f.filename}' has an invalid file extension!"), 404
            oc.put_file_contents(str(source_dir / name), f.read())
        return utils.response(f"Source files successfully added to '{corpus_id}'!")
    except Exception as e:
        return utils.response(f"Failed to upload source files to '{corpus_id}'!", err=True, info=str(e)), 404


@bp.route("/list-sources", methods=["GET"])
@utils.login()
def list_sources(oc, _user, corpora, corpus_id):
    """List the available corpus source files."""
    source_dir = str(paths.get_source_dir(domain="nc", corpus_id=corpus_id, oc=oc))
    try:
        objlist = utils.list_contents(oc, source_dir)
        return utils.response(f"Current source files for '{corpus_id}'", contents=objlist)
    except Exception as e:
        return utils.response(f"Failed to list source files in '{corpus_id}'!", err=True, info=str(e)), 404


@bp.route("/remove-sources", methods=["DELETE"])
@utils.login()
def remove_sources(oc, _user, _corpora, corpus_id):
    """Remove file paths listed in 'remove' (comma separated) from the corpus."""
    remove_files = request.args.get("remove") or request.form.get("remove") or ""
    remove_files = [i.strip() for i in remove_files.split(",") if i]
    if not remove_files:
        return utils.response("No files provided for removal!", err=True), 404

    source_dir = paths.get_source_dir(domain="nc", corpus_id=corpus_id)

    # Remove files
    successes = []
    fails = []
    for rf in remove_files:
        nc_path = str(source_dir / Path(rf))
        try:
            oc.delete(nc_path)
            successes.append(rf)
        except Exception:
            fails.append(rf)

    if fails and successes:
        return utils.response("Failed to remove: '{}'! Successfully removed: '{}'!".format(
                              "', '".join(fails), "', '".join(successes)), err=True), 404
    if fails:
        return utils.response("Failed to remove files!", err=True), 404

    return utils.response(f"Source files for '{corpus_id}' successfully updated!")


@bp.route("/download-sources", methods=["GET"])
@utils.login()
def download_sources(oc, user, _corpora, corpus_id):
    """Download the corpus source files as a zip file."""
    nc_source_dir = str(paths.get_source_dir(domain="nc", corpus_id=corpus_id, oc=oc))
    local_source_dir = paths.get_source_dir(user=user, corpus_id=corpus_id, mkdir=True)
    zip_out = str(local_source_dir / f"{corpus_id}_source.zip")

    try:
        # Get files from Nextcloud
        oc.get_directory_as_zip(nc_source_dir, zip_out)
        return send_file(zip_out, mimetype="application/zip")
    except Exception as e:
        return utils.response(f"Failed to download corpus source files for corpus '{corpus_id}'!", err=True,
                              info=str(e)), 404


# ------------------------------------------------------------------------------
# Config file operations
# ------------------------------------------------------------------------------

@bp.route("/upload-config", methods=["PUT"])
@utils.login()
def upload_config(oc, _user, corpora, corpus_id):
    """Upload a corpus config as file or plain text."""
    attached_files = list(request.files.values())
    config_txt = request.args.get("config") or request.form.get("config") or ""

    if attached_files and config_txt:
        return utils.response("Found both a config file and a plain text config but can only process one of these!",
                              err=True), 404

    # Process uploaded config file
    if attached_files:
        # Check if config file is YAML
        config_file = attached_files[0]
        if config_file.mimetype not in ("application/x-yaml", "text/yaml"):
            return utils.response("Config file needs to be YAML!", err=True), 404

        try:
            new_config = utils.set_corpus_id(config_file.read(), corpus_id)
            oc.put_file_contents(str(paths.get_config_file(domain="nc", corpus_id=corpus_id)), new_config)
            return utils.response(f"Config file successfully uploaded for '{corpus_id}'!")
        except Exception as e:
            return utils.response(f"Failed to upload config file for '{corpus_id}'!", err=True, info=str(e))

    elif config_txt:
        try:
            new_config = utils.set_corpus_id(config_txt, corpus_id)
            oc.put_file_contents(str(paths.get_config_file(domain="nc", corpus_id=corpus_id)), new_config)
            return utils.response(f"Config file successfully uploaded for '{corpus_id}'!")
        except Exception as e:
            return utils.response(f"Failed to upload config file for '{corpus_id}'!", err=True, info=str(e))

    else:
        return utils.response("No config file provided for upload!", err=True), 404


@bp.route("/download-config", methods=["GET"])
@utils.login()
def download_config(oc, user, _corpora, corpus_id):
    """Download the corpus config file."""
    nc_config_file = str(paths.get_config_file(domain="nc", corpus_id=corpus_id))
    paths.get_source_dir(user=user, corpus_id=corpus_id, mkdir=True)
    local_config_file = str(paths.get_config_file(user=user, corpus_id=corpus_id))

    try:
        # Get file from Nextcloud
        oc.get_file(nc_config_file, local_file=local_config_file)
        return send_file(local_config_file, mimetype="text/yaml")
    except Exception as e:
        return utils.response(f"Failed to download config file for corpus '{corpus_id}'!", err=True, info=str(e)), 404


# ------------------------------------------------------------------------------
# Export file operations
# ------------------------------------------------------------------------------

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
    """Download export files for a corpus as a zip file.

    The parameters 'file' and 'dir' may be used to download a specific export file
    or a directory of export files. These parameters must be supplied as absolute
    Nextcloud paths or paths relative to the export directory.
    """
    download_file = request.args.get("file") or request.form.get("file") or ""
    download_folder = request.args.get("dir") or request.form.get("dir") or ""

    if download_file and download_folder:
        return utils.response("The parameters 'dir' and 'file' must not be supplied simultaneously!", err=True), 404

    nc_export_dir = str(paths.get_export_dir(domain="nc", corpus_id=corpus_id))
    local_corpus_dir = str(paths.get_corpus_dir(user=user, corpus_id=corpus_id, mkdir=True))

    try:
        export_contents = utils.list_contents(oc, nc_export_dir, exclude_dirs=False)
        if export_contents == []:
            return utils.response(f"There are currently no exports available for corpus '{corpus_id}'!", err=True), 404
    except Exception as e:
        return utils.response(f"Failed to download exports for corpus '{corpus_id}'!", err=True, info=str(e)), 404

    if not (download_file or download_folder):
        try:
            zip_out = str(local_corpus_dir / Path(f"{corpus_id}_export.zip"))
            # Get files from Nextcloud
            oc.get_directory_as_zip(nc_export_dir, zip_out)
            return send_file(zip_out, mimetype="application/zip")
        except Exception as e:
            return utils.response(f"Failed to download exports for corpus '{corpus_id}'!", err=True, info=str(e)), 404

    # Download and zip folder specified in args
    if download_folder:
        full_download_folder = download_folder
        if not download_folder("/").startswith(nc_export_dir):
            full_download_folder = "/" + str(Path(nc_export_dir) / download_folder)
        if full_download_folder not in [i.get("path") for i in export_contents]:
            return utils.response(f"The folder '{download_folder}' you are trying to download does not exist!",
                                  err=True), 404
        try:
            zip_out = str(local_corpus_dir / Path(f"{corpus_id}_{download_folder}.zip"))
            oc.get_directory_as_zip(full_download_folder, zip_out)
            return send_file(zip_out, mimetype="application/zip")
        except Exception as e:
            utils.response(f"Failed to download folder '{download_folder}'!", err=True, info=str(e)), 404

    # Download and zip file specified in args
    if download_file:
        full_download_file = download_file
        download_file_name = Path(download_file).name
        if not download_file.lstrip("/").startswith(nc_export_dir):
            full_download_file = "/" + str(Path(nc_export_dir) / download_file)
        if full_download_file not in [i.get("path") for i in export_contents]:
            return utils.response(f"The file '{download_file}' you are trying to download does not exist!",
                                  err=True), 404
        try:
            zip_out = str(local_corpus_dir / Path(f"{corpus_id}_{download_file_name}.zip"))
            local_path = Path(local_corpus_dir) / download_file_name
            oc.get_file(full_download_file, local_path)
            utils.create_zip(local_path, zip_out)
            return send_file(zip_out, mimetype="application/zip")
        except Exception as e:
            return utils.response(f"Failed to download file '{download_file}'!", err=True, info=str(e)), 404


@bp.route("/remove-exports", methods=["DELETE"])
@utils.login()
def remove_exports(oc, user, _corpora, corpus_id):
    """Remove export files."""
    try:
        # Remove export dir from Nextcloud and create a new empty one
        export_dir = str(paths.get_export_dir(domain="nc", corpus_id=corpus_id))
        oc.delete(export_dir)
        paths.get_export_dir(domain="nc", corpus_id=corpus_id, oc=oc, mkdir=True)
    except Exception as e:
        return utils.response(f"Failed to remove export files for corpus '{corpus_id}'!", err=True, info=str(e)), 404

    try:
        # Remove from Sparv server
        job = jobs.get_job(user, corpus_id)
        sparv_output = job.clean_export()
        app.logger.debug(f"Output from sparv clean --export: {sparv_output}")
    except Exception as e:
        app.logger.error(f"Failed to remove export files from Sparv server! {str(e)}")

    return utils.response(f"Export files for corpus '{corpus_id}' successfully removed!")
