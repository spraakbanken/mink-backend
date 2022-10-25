"""Routes related to storage on Sparv server."""

from pathlib import Path

import dateutil
import shortuuid
from flask import Blueprint
from flask import current_app as app
from flask import request, send_file

from mink import corpus_registry, exceptions, jobs, queue, utils
from mink.sb_auth import login
from mink.sparv import storage
from mink.sparv import utils as sparv_utils

bp = Blueprint("sparv_storage", __name__)


# ------------------------------------------------------------------------------
# Corpus operations
# ------------------------------------------------------------------------------

@bp.route("/create-corpus", methods=["POST"])
@login.login(require_corpus_exists=False, require_corpus_id=False)
def create_corpus(corpora: list, auth_token: str):
    """Create a new corpus."""
    # Create corpus ID
    corpus_id = None
    prefix = app.config.get("RESOURCE_PREFIX")
    tries = 1
    while corpus_id is None:
        # Give up after 3 tries
        if tries > 3:
            return utils.response("Failed to create resource", err=True), 500
        tries += 1
        corpus_id = f"{prefix}{shortuuid.uuid()[:10]}".lower()
        corpora = corpus_registry.get_all()
        if corpus_id in corpora:
            corpus_id = None
        try:
            login.create_resource(auth_token, corpus_id)
        except exceptions.CorpusExists:
            # Corpus ID is in use, try to create another one
            corpus_id = None
        except Exception as e:
            return utils.response("Failed to create resource", err=True, info=str(e)), 500

    # Create corpus dir with subdirs
    try:
        corpus_dir = str(storage.get_corpus_dir(corpus_id, mkdir=True))
        storage.get_source_dir(corpus_id, mkdir=True)
        corpus_registry.add(corpus_id)
        return utils.response(f"Corpus '{corpus_id}' created successfully", corpus_id=corpus_id), 201
    except Exception as e:
        try:
            # Try to remove partially uploaded corpus data
            storage.remove_dir(corpus_dir, corpus_id)
        except Exception as err:
            app.logger.error(f"Failed to remove partially uploaded corpus data for '{corpus_id}'. {err}")
        try:
            login.remove_resource(corpus_id)
        except Exception as err:
            app.logger.error(f"Failed to remove corpus '{corpus_id}' from auth system. {err}")
        return utils.response("Failed to create corpus dir", err=True, info=str(e)), 500


@bp.route("/list-corpora", methods=["GET"])
@login.login(require_corpus_id=False, require_corpus_exists=False)
def list_corpora(corpora: list):
    """List all available corpora."""
    return utils.response("Listing available corpora", corpora=corpora)


@bp.route("/list-korp-corpora", methods=["GET"])
@login.login(include_read=True, require_corpus_id=False, require_corpus_exists=False)
def list_korp_corpora(corpora: list):
    """List all corpora installed in Korp."""
    installed_corpora = []
    try:
        # Get jobs beloning to corpora that the user may edit
        all_jobs = queue.get_jobs(corpora)
        for job in all_jobs:
            if job.installed_korp:
                installed_corpora.append(job.corpus_id)
    except Exception as e:
        return utils.response(f"Failed to list corpora installed in Korp", err=True, info=str(e)), 500
    return utils.response("Listing corpora installed in Korp", corpora=installed_corpora)


@bp.route("/remove-corpus", methods=["DELETE"])
@login.login()
def remove_corpus(corpus_id: str):
    """Remove corpus."""
    # TODO: Uninstall corpus (if installed) using Sparv
    try:
        # Remove from storage
        corpus_dir = str(storage.get_corpus_dir(corpus_id))
        storage.remove_dir(corpus_dir, corpus_id)
    except Exception as e:
        return utils.response(f"Failed to remove corpus '{corpus_id}' from storage", err=True, info=str(e)), 500

    try:
        # Remove job
        job = jobs.get_job(corpus_id)
        queue.remove(job)
        job.remove()
    except Exception as e:
        return utils.response(f"Failed to remove job for corpus '{corpus_id}'. {e}", err=True, info=str(e)), 500

    try:
        # Remove from auth system
        login.remove_resource(corpus_id)
    except Exception as e:
        return utils.response(f"Failed to remove corpus '{corpus_id}' from auth system", err=True, info=str(e)), 500

    try:
        # Remove from corpus registry
        corpus_registry.remove(corpus_id)
    except Exception as e:
        app.logger.error(f"Failed to remove corpus '{corpus_id}' from corpus registry: {e}")

    return utils.response(f"Corpus '{corpus_id}' successfully removed")


# ------------------------------------------------------------------------------
# Source file operations
# ------------------------------------------------------------------------------

@bp.route("/upload-sources", methods=["PUT"])
@login.login()
def upload_sources(corpus_id: str):
    """Upload corpus source files.

    Attached files will be added to the corpus or replace existing ones.
    """
    # Check if corpus files were provided
    files = list(request.files.listvalues())
    if not files:
        return utils.response("No corpus files provided for upload", err=True), 400

    try:
        # Upload data
        source_dir = storage.get_source_dir(corpus_id)
        for f in files[0]:
            name = sparv_utils.secure_filename(f.filename)
            if not utils.check_file_ext(name, app.config.get("SPARV_IMPORTER_MODULES", {}).keys()):
                return utils.response(f"Failed to upload some source files to '{corpus_id}' due to invalid "
                                      "file extension", err=True, file=f.filename, info="invalid file extension"), 400
            compatible, current_ext, existing_ext = utils.check_file_compatible(name, source_dir)
            if not compatible:
                return utils.response(f"Failed to upload some source files to '{corpus_id}' due to incompatible "
                                      "file extensions", err=True, file=f.filename, info="incompatible file extensions",
                                      current_file_extension=current_ext, existing_file_extension=existing_ext), 400
            file_contents = f.read()
            # Validate XML files
            if current_ext == ".xml":
                if not utils.validate_xml(file_contents):
                    return utils.response(f"Failed to upload some source files to '{corpus_id}' due to invalid XML",
                                          err=True, file=f.filename, info="invalid XML"), 400
            storage.write_file_contents(str(source_dir / name), file_contents, corpus_id)
        return utils.response(f"Source files successfully added to '{corpus_id}'")
    except Exception as e:
        return utils.response(f"Failed to upload source files to '{corpus_id}'", err=True, info=str(e)), 500


@bp.route("/list-sources", methods=["GET"])
@login.login()
def list_sources(corpus_id: str):
    """List the available corpus source files."""
    source_dir = str(storage.get_source_dir(corpus_id))
    try:
        objlist = storage.list_contents(source_dir)
        return utils.response(f"Current source files for '{corpus_id}'", contents=objlist)
    except Exception as e:
        return utils.response(f"Failed to list source files in '{corpus_id}'", err=True, info=str(e)), 500


@bp.route("/remove-sources", methods=["DELETE"])
@login.login()
def remove_sources(corpus_id: str):
    """Remove file paths listed in 'remove' (comma separated) from the corpus."""
    remove_files = request.args.get("remove") or request.form.get("remove") or ""
    remove_files = [i.strip() for i in remove_files.split(",") if i]
    if not remove_files:
        return utils.response("No files provided for removal", err=True), 400

    source_dir = storage.get_source_dir(corpus_id)

    # Remove files
    successes = []
    fails = []
    for rf in remove_files:
        storage_path = str(source_dir / Path(rf))
        try:
            storage.remove_file(storage_path, corpus_id)
            successes.append(rf)
        except Exception:
            fails.append(rf)

    if fails and successes:
        return utils.response(f"Failed to remove some source files form '{corpus_id}'.",
                              failed=fails, succeeded=successes, err=True), 500
    if fails:
        return utils.response("Failed to remove files", err=True), 500

    return utils.response(f"Source files for '{corpus_id}' successfully removed")


@bp.route("/download-sources", methods=["GET"])
@login.login()
def download_sources(corpus_id: str):
    """Download the corpus source files as a zip file.

    The parameter 'file' may be used to download a specific source file. This
    parameter must either be a file name or a path on the storage server. The `zip`
    parameter may be set to `false` in combination with the `file` param to avoid
    zipping the file to be downloaded.
    """
    download_file = request.args.get("file") or request.form.get("file") or ""

    # Check if there are any source files
    storage_source_dir = str(storage.get_source_dir(corpus_id))
    try:
        source_contents = storage.list_contents(storage_source_dir, exclude_dirs=False)
        if source_contents == []:
            return utils.response(f"You have not uploaded any source files for corpus '{corpus_id}'", err=True), 404
    except Exception as e:
        return utils.response(f"Failed to download source files for corpus '{corpus_id}'", err=True, info=str(e)), 500

    local_source_dir = utils.get_source_dir(corpus_id, mkdir=True)
    local_corpus_dir = utils.get_corpus_dir(corpus_id, mkdir=True)

    # Download and zip file specified in args
    if download_file:
        download_file_name = Path(download_file).name
        full_download_file = str(Path(storage_source_dir) / download_file)
        if download_file not in [i.get("path") for i in source_contents]:
            return utils.response(f"The file '{download_file}' you are trying to download does not exist",
                                  err=True), 404
        try:
            local_path = local_source_dir / download_file_name
            zipped = request.args.get("zip", "") or request.form.get("zip", "")
            zipped = not zipped.lower() == "false"
            storage.download_file(full_download_file, local_path, corpus_id)
            if zipped:
                outf = str(local_corpus_dir / Path(f"{corpus_id}_{download_file_name}.zip"))
                utils.create_zip(local_path, outf)
                return send_file(outf, mimetype="application/zip")
            else:
                # Determine content type
                content_type = "application/xml"
                for file_obj in source_contents:
                    if file_obj.get("name") == download_file_name:
                        content_type = file_obj.get("type")
                        break
                return send_file(local_path, mimetype=content_type)
        except Exception as e:
            return utils.response(f"Failed to download file '{download_file}'", err=True, info=str(e)), 500

    # Download all files as zip archive
    try:
        zip_out = str(local_corpus_dir / f"{corpus_id}_source.zip")
        # Get files from storage server
        storage.download_dir(storage_source_dir, local_source_dir, corpus_id, zipped=True, zippath=zip_out)
        return send_file(zip_out, mimetype="application/zip")
    except Exception as e:
        return utils.response(f"Failed to download source files for corpus '{corpus_id}'", err=True,
                              info=str(e)), 500


# ------------------------------------------------------------------------------
# Config file operations
# ------------------------------------------------------------------------------

@bp.route("/upload-config", methods=["PUT"])
@login.login()
def upload_config(corpus_id: str):
    """Upload a corpus config as file or plain text."""
    attached_files = list(request.files.values())
    config_txt = request.args.get("config") or request.form.get("config") or ""

    if attached_files and config_txt:
        return utils.response("Found both a config file and a plain text config but can only process one of these",
                              err=True), 400

    source_dir = str(storage.get_source_dir(corpus_id))
    source_files = storage.list_contents(str(source_dir))

    # Process uploaded config file
    if attached_files:
        # Check if config file is YAML
        config_file = attached_files[0]
        if config_file.mimetype not in ("application/x-yaml", "text/yaml"):
            return utils.response("Config file needs to be YAML", err=True), 400

        config_contents = config_file.read()

        # Check if config file is compatible with the uploaded source files
        if source_files:
            compatible, resp = utils.config_compatible(config_contents, source_files[0])
            if not compatible:
                return resp, 400

        try:
            new_config = utils.standardize_config(config_contents, corpus_id)
            storage.write_file_contents(str(storage.get_config_file(corpus_id)), new_config.encode("UTF-8"), corpus_id)
            return utils.response(f"Config file successfully uploaded for '{corpus_id}'"), 201
        except Exception as e:
            return utils.response(f"Failed to upload config file for '{corpus_id}'", err=True, info=str(e))

    elif config_txt:
        try:
            # Check if config file is compatible with the uploaded source files
            if source_files:
                compatible, resp = utils.config_compatible(config_txt, source_files[0])
                if not compatible:
                    return resp, 400
            new_config = utils.standardize_config(config_txt, corpus_id)
            storage.write_file_contents(str(storage.get_config_file(corpus_id)), new_config.encode("UTF-8"), corpus_id)
            return utils.response(f"Config file successfully uploaded for '{corpus_id}'"), 201
        except Exception as e:
            return utils.response(f"Failed to upload config file for '{corpus_id}'", err=True, info=str(e))

    else:
        return utils.response("No config file provided for upload", err=True), 400


@bp.route("/download-config", methods=["GET"])
@login.login()
def download_config(corpus_id: str):
    """Download the corpus config file."""
    storage_config_file = str(storage.get_config_file(corpus_id))
    utils.get_source_dir(corpus_id, mkdir=True)
    local_config_file = utils.get_config_file(corpus_id)

    try:
        # Get file from storage
        if storage.download_file(storage_config_file, local_config_file, corpus_id, ignore_missing=True):
            return send_file(local_config_file, mimetype="text/yaml")
        else:
            return utils.response(f"No config file found for corpus '{corpus_id}'", err=True), 404
    except Exception as e:
        return utils.response(f"Failed to download config file for corpus '{corpus_id}'", err=True, info=str(e)), 500


# ------------------------------------------------------------------------------
# Export file operations
# ------------------------------------------------------------------------------

@bp.route("/list-exports", methods=["GET"])
@login.login()
def list_exports(corpus_id: str):
    """List exports available for download for a given corpus."""
    path = str(storage.get_export_dir(corpus_id))
    try:
        objlist = storage.list_contents(path)
        return utils.response(f"Current export files for '{corpus_id}'", contents=objlist)
    except Exception as e:
        return utils.response(f"Failed to list files in '{corpus_id}'", err=True, info=str(e)), 500


@bp.route("/download-exports", methods=["GET"])
@login.login()
def download_export(corpus_id: str):
    """Download export files for a corpus as a zip file.

    The parameters 'file' and 'dir' may be used to download a specific export file or a directory of export files. These
    parameters must be supplied as  paths relative to the export directory. The `zip` parameter may be set to `false` in
    combination with the `file` param to avoid zipping the file to be downloaded.
    """
    download_file = request.args.get("file") or request.form.get("file") or ""
    download_folder = request.args.get("dir") or request.form.get("dir") or ""

    if download_file and download_folder:
        return utils.response("The parameters 'dir' and 'file' must not be supplied simultaneously", err=True), 400

    storage_export_dir = str(storage.get_export_dir(corpus_id))
    local_corpus_dir = utils.get_corpus_dir(corpus_id, mkdir=True)
    local_export_dir = utils.get_export_dir(corpus_id, mkdir=True)

    try:
        export_contents = storage.list_contents(storage_export_dir, exclude_dirs=False)
        if export_contents == []:
            return utils.response(f"There are currently no exports available for corpus '{corpus_id}'", err=True), 404
    except Exception as e:
        return utils.response(f"Failed to download exports for corpus '{corpus_id}'", err=True, info=str(e)), 500

    # Download all export files
    if not (download_file or download_folder):
        try:
            zip_out = str(local_corpus_dir / f"{corpus_id}_export.zip")
            # Get files from storage server
            storage.download_dir(storage_export_dir, local_export_dir, corpus_id, zipped=True, zippath=zip_out)
            return send_file(zip_out, mimetype="application/zip")
        except Exception as e:
            return utils.response(f"Failed to download exports for corpus '{corpus_id}'", err=True, info=str(e)), 500

    # Download and zip folder specified in args
    if download_folder:
        download_folder_name = "_".join(Path(download_folder).parts)
        full_download_folder = str(Path(storage_export_dir) / download_folder)
        if download_folder not in [i.get("path") for i in export_contents]:
            return utils.response(f"The folder '{download_folder}' you are trying to download does not exist",
                                  err=True), 404
        try:
            zip_out = str(local_corpus_dir / f"{corpus_id}_{download_folder_name}.zip")
            (local_export_dir / download_folder).mkdir(exist_ok=True)
            storage.download_dir(full_download_folder, local_export_dir / download_folder, corpus_id,
                                 zipped=True, zippath=zip_out)
            return send_file(zip_out, mimetype="application/zip")
        except Exception as e:
            return utils.response(f"Failed to download folder '{download_folder}'", err=True, info=str(e)), 500

    # Download and zip file specified in args
    if download_file:
        download_file_name = Path(download_file).name
        full_download_file = str(Path(storage_export_dir) / download_file)
        if download_file not in [i.get("path") for i in export_contents]:
            return utils.response(f"The file '{download_file}' you are trying to download does not exist",
                                  err=True), 404
        try:
            local_path = local_export_dir / download_file
            (local_export_dir / download_file).parent.mkdir(exist_ok=True)
            zipped = request.args.get("zip", "") or request.form.get("zip", "")
            zipped = not zipped.lower() == "false"
            if zipped:
                outf = str(local_corpus_dir / Path(f"{corpus_id}_{download_file_name}.zip"))
                storage.download_file(full_download_file, local_path, corpus_id)
                utils.create_zip(local_path, outf)
                return send_file(outf, mimetype="application/zip")
            else:
                storage.download_file(full_download_file, local_path, corpus_id)
                # Determine content type
                content_type = "application/xml"
                for file_obj in export_contents:
                    if file_obj.get("name") == download_file_name:
                        content_type = file_obj.get("type")
                        break
                return send_file(local_path, mimetype=content_type)
        except Exception as e:
            return utils.response(f"Failed to download file '{download_file}'", err=True, info=str(e)), 500


@bp.route("/remove-exports", methods=["DELETE"])
@login.login()
def remove_exports(corpus_id: str):
    """Remove export files."""
    try:
        # Remove export dir from storage server and create a new empty one
        export_dir = str(storage.get_export_dir(corpus_id))
        storage.remove_dir(export_dir, corpus_id)
        storage.get_export_dir(corpus_id, mkdir=True)
    except Exception as e:
        return utils.response(f"Failed to remove export files for corpus '{corpus_id}'", err=True, info=str(e)), 500

    try:
        # Remove from Sparv server
        job = jobs.get_job(corpus_id)
        sparv_output = job.clean_export()
        app.logger.debug(f"Output from sparv clean --export: {sparv_output}")
    except Exception as e:
        app.logger.error(f"Failed to remove export files from Sparv server. {str(e)}")

    return utils.response(f"Export files for corpus '{corpus_id}' successfully removed")


@bp.route("/download-source-text", methods=["GET"])
@login.login()
def download_source_text(corpus_id: str):
    """Get one of the source files in plain text.

    The source file name (including its file extension) must be specified in the 'file' parameter.
    """
    download_file = request.args.get("file") or request.form.get("file") or ""

    storage_work_dir = str(storage.get_work_dir(corpus_id))
    local_corpus_dir = str(utils.get_corpus_dir(corpus_id, mkdir=True))

    if not download_file:
        return utils.response("Please specify the source file to download", err=True), 400

    try:
        source_texts = storage.list_contents(storage_work_dir, exclude_dirs=False)
        if source_texts == []:
            return utils.response((f"There are currently no source texts for corpus '{corpus_id}'. "
                                   "You must run Sparv before you can view source texts."), err=True), 404
    except Exception as e:
        return utils.response(f"Failed to download source text for corpus '{corpus_id}'", err=True, info=str(e)), 500

    # Download file specified in args
    download_file_stem = Path(download_file).stem
    short_path = str(Path(download_file_stem) / app.config.get("SPARV_PLAIN_TEXT_FILE"))
    if short_path not in [i.get("path") for i in source_texts]:
        return utils.response(f"The source text for the file '{download_file}' does not exist",
                              err=True), 404
    try:
        full_download_path = str(Path(storage_work_dir) / Path(download_file).parent / download_file_stem /
                                app.config.get("SPARV_PLAIN_TEXT_FILE"))
        out_file_name = download_file_stem + "_plain.txt"
        local_path = Path(local_corpus_dir) / out_file_name
        storage.download_file(full_download_path, local_path, corpus_id)
        utils.uncompress_gzip(local_path)
        return send_file(local_path, mimetype="text/plain")
    except Exception as e:
        return utils.response(f"Failed to download source text for file '{download_file}'", err=True, info=str(e)), 500


@bp.route("/check-changes", methods=["GET"])
@login.login()
def check_changes(corpus_id: str):
    """Check if config or source files have changed since the last job was started."""
    try:
        job = jobs.get_job(corpus_id)
        if not job.started:
            return utils.response(f"Corpus '{corpus_id}' has not been run")
        started = dateutil.parser.isoparse(job.started)

        # Get current source files on storage server
        source_dir = str(storage.get_source_dir(corpus_id))
        try:
            source_files = storage.list_contents(source_dir)
        except Exception as e:
            return utils.response(f"Failed to list source files in '{corpus_id}'", err=True, info=str(e)), 500
        source_file_paths = [f["path"] for f in source_files]
        available_file_paths = [f["path"] for f in job.available_files]

        # Check for new source files
        added_sources = []
        for sf in source_files:
            if sf["path"] not in available_file_paths:
                added_sources.append(sf)

        # Compare all source files modification time to the time stamp of the last job started
        changed_sources = []
        for sf in source_files:
            if sf in added_sources:
                continue
            mod = dateutil.parser.isoparse(sf.get("last_modified"))
            if mod > started:
                changed_sources.append(sf)

        # Check for deleted source files
        deleted_sources = []
        for fileobj in job.available_files:
            if fileobj["path"] not in source_file_paths:
                deleted_sources.append(fileobj)

        # Compare the config file modification time to the time stamp of the last job started
        changed_config = {}
        corpus_dir = str(storage.get_corpus_dir(corpus_id))
        corpus_files = storage.list_contents(corpus_dir)
        config_file = storage.get_config_file(corpus_id)
        for f in corpus_files:
            if f.get("name") == config_file.name:
                config_mod = dateutil.parser.isoparse(f.get("last_modified"))
                if config_mod > started:
                    changed_config = f
                break

        if added_sources or changed_sources or changed_config or deleted_sources:
            return utils.response(f"Your input for the corpus '{corpus_id}' has changed since the last run",
                                  config_changed=bool(changed_config), sources_added=bool(added_sources),
                                  sources_changed=bool(changed_sources), sources_deleted=bool(deleted_sources),
                                  changed_config=changed_config, added_sources=added_sources,
                                  changed_sources=changed_sources, deleted_sources=deleted_sources,
                                  last_run_started=job.started)
        return utils.response(f"Your input for the corpus '{corpus_id}' has not changed since the last run",
                              last_run_started=job.started)

    except Exception as e:
        return utils.response(f"Failed to check changes for corpus '{corpus_id}'", err=True, info=str(e)), 500
