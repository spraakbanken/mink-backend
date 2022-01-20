"""Routes related to Nextcloud."""

import re
from pathlib import Path

import dateutil
from flask import Blueprint
from flask import current_app as app
from flask import request, send_file

from minsb import jobs, paths, queue, utils
from minsb.nextcloud import login, storage

bp = Blueprint("nextcloud", __name__)


@bp.route("/init", methods=["POST"])
@login.login(require_init=False, require_corpus_id=False, require_corpus_exists=False)
def init(oc, _user, dir_listing):
    """Create corpora directory."""
    try:
        corpora_dir = app.config.get("NC_CORPORA_DIR")
        if corpora_dir in [e.get_name() for e in dir_listing]:
            # Corpora dir already exists
            return utils.response(f"Nothing to be done. Min Språkbank has already been initialized"), 200
        # Create corpora dir
        corpora_dir = str(paths.get_corpora_dir(domain="nc", oc=oc, mkdir=True))
        # TODO: upload some info file?
        app.logger.debug(f"Initialized corpora dir '{corpora_dir}'")
        return utils.response("Min Språkbank successfully initialized"), 201
    except Exception as e:
        return utils.response("Failed to initialize corpora dir", err=True, info=str(e)), 404


# ------------------------------------------------------------------------------
# Corpus operations
# ------------------------------------------------------------------------------

@bp.route("/create-corpus", methods=["POST"])
@login.login(require_corpus_exists=False)
def create_corpus(oc, _user, corpora, corpus_id):
    """Create a new corpus."""
    # Check if corpus_id is valid
    if not bool(re.match(r"^[a-z0-9-]+$", corpus_id)):
        return utils.response(f"Corpus ID '{corpus_id}' is invalid", err=True), 404

    # Make sure corpus dir does not exist already
    if corpus_id in corpora:
        return utils.response(f"Corpus '{corpus_id}' already exists", err=True), 404

    # Create corpus dir with subdirs
    try:
        corpus_dir = str(paths.get_corpus_dir(domain="nc", corpus_id=corpus_id, oc=oc, mkdir=True))
        paths.get_source_dir(domain="nc", corpus_id=corpus_id, oc=oc, mkdir=True)
        paths.get_export_dir(domain="nc", corpus_id=corpus_id, oc=oc, mkdir=True)
        paths.get_work_dir(domain="nc", corpus_id=corpus_id, oc=oc, mkdir=True)
        return utils.response(f"Corpus '{corpus_id}' created successfully")
    except Exception as e:
        try:
            # Try to remove partially uploaded corpus data
            oc.delete(corpus_dir)
        except Exception as err:
            app.logger.error(f"Failed to remove partially uploaded corpus data for '{corpus_id}'. {err}")
        return utils.response("Failed to create corpus dir", err=True, info=str(e)), 404


@bp.route("/list-corpora", methods=["GET"])
@login.login(require_corpus_id=False, require_corpus_exists=False)
def list_corpora(_oc, _user, corpora):
    """List all available corpora."""
    return utils.response("Listing available corpora", corpora=corpora)


@bp.route("/remove-corpus", methods=["DELETE"])
@login.login()
def remove_corpus(oc, user, _corpora, corpus_id):
    """Remove corpus."""
    try:
        corpus_dir = str(paths.get_corpus_dir(domain="nc", corpus_id=corpus_id))
        oc.delete(corpus_dir)
    except Exception as e:
        return utils.response(f"Failed to remove corpus '{corpus_id}'", err=True, info=str(e)), 404

    try:
        # Try to safely remove files from Sparv server and remove the job
        job = jobs.get_job(user, corpus_id)
        job.remove_from_sparv()
        queue.remove(job)
        job.remove()
    except Exception as e:
        app.logger.error(f"Failed to remove corpus '{corpus_id}'. {e}")

    return utils.response(f"Corpus '{corpus_id}' successfully removed")


@bp.route("/rename-corpus", methods=["POST"])
@login.login()
def rename_corpus(oc, user, corpora, corpus_id):
    """Rename corpus."""
    new_id = request.args.get("new_id") or request.form.get("new_id") or ""

    if not new_id:
        return utils.response("No new corpus ID was provided", err=True), 400
    if new_id == corpus_id:
        return utils.response("The new ID must not be the same as the current ID", err=True), 400
    if new_id in corpora:
        return utils.response("The chosen ID already exists", err=True), 400

    nextcloud_success = sparv_server_success = config_success = False
    try:
        job = jobs.get_job(user, corpus_id)
        if jobs.Status.none < job.status < jobs.Status.done_annotating or job.status == jobs.Status.syncing_results:
            return utils.response("Cannot rename corpus while a job is running", err=True), 404
        # Rename on Nextcloud (NB: order of changes is relevant!)
        corpus_dir = paths.get_corpus_dir(domain="nc", corpus_id=corpus_id)
        new_corpus_dir = corpus_dir.parent.joinpath(new_id)
        oc.move(str(corpus_dir), str(new_corpus_dir))
        nextcloud_success = True

        # Change ID in config file
        config_file = str(paths.get_config_file(domain="nc", corpus_id=new_id))
        config_contents = oc.get_file_contents(config_file)
        new_config = utils.set_corpus_id(config_contents, new_id)
        oc.put_file_contents(str(paths.get_config_file(domain="nc", corpus_id=new_id)), new_config)
        config_success = True

        # Rename corpus dir on Sparv server and job in cache
        if queue.get_priority(job) != -1:
            queue.remove(job)
            job.change_id(new_id)
            queue.add(job)
            sparv_server_success = True

        return utils.response(f"Successfully renamed corpus to '{new_id}'")
    except Exception as e:
        # Undo renaming if it succeeded partially (NB: order of changes is relevant!)
        if nextcloud_success:
            corpus_dir = paths.get_corpus_dir(domain="nc", corpus_id=new_id)
            reset_corpus_dir = corpus_dir.parent.joinpath(corpus_id)
            oc.move(str(corpus_dir), str(reset_corpus_dir))
        if config_success:
            config_file = str(paths.get_config_file(domain="nc", corpus_id=corpus_id))
            config_contents = oc.get_file_contents(config_file)
            reset_config = utils.set_corpus_id(config_contents, corpus_id)
            oc.put_file_contents(str(paths.get_config_file(domain="nc", corpus_id=corpus_id)), reset_config)
        if sparv_server_success:
            queue.remove(job)
            job.change_id(corpus_id)
            queue.add(job)

        return utils.response("Failed to rename corpus", err=True, info=str(e)), 404


# ------------------------------------------------------------------------------
# Source file operations
# ------------------------------------------------------------------------------

@bp.route("/upload-sources", methods=["PUT"])
@login.login()
def upload_sources(oc, _user, corpora, corpus_id):
    """Upload corpus source files.

    Attached files will be added to the corpus or replace existing ones.
    """
    # Check if corpus files were provided
    files = list(request.files.listvalues())
    if not files:
        return utils.response("No corpus files provided for upload", err=True), 404

    try:
        # Upload data
        source_dir = paths.get_source_dir(domain="nc", corpus_id=corpus_id, oc=oc)
        for f in files[0]:
            name = utils.check_file_ext(f.filename, app.config.get("SPARV_IMPORTER_MODULES", {}).keys())
            if not name:
                return utils.response(f"Failed to upload some source files to '{corpus_id}' due to invalid "
                                       "file extension", err=True, file=f.filename, info="invalid file extension"), 404
            compatible, current_ext, existing_ext = utils.check_file_compatible(name, source_dir, oc)
            if not compatible:
                return utils.response(f"Failed to upload some source files to '{corpus_id}' due to incompatible "
                                       "file extensions", err=True, file=f.filename, info="incompatible file extensions",
                                       current_file_extension=current_ext, existing_file_extension=existing_ext), 404
            file_contents = f.read()
            # Validate XML files
            if current_ext == ".xml":
                if not utils.validate_xml(file_contents):
                    return utils.response(f"Failed to upload some source files to '{corpus_id}' due to invalid XML",
                                          err=True, file=f.filename, info="invalid XML"), 404
            oc.put_file_contents(str(source_dir / name), file_contents)
        return utils.response(f"Source files successfully added to '{corpus_id}'")
    except Exception as e:
        return utils.response(f"Failed to upload source files to '{corpus_id}'", err=True, info=str(e)), 404


@bp.route("/list-sources", methods=["GET"])
@login.login()
def list_sources(oc, _user, corpora, corpus_id):
    """List the available corpus source files."""
    source_dir = str(paths.get_source_dir(domain="nc", corpus_id=corpus_id, oc=oc))
    try:
        objlist = storage.list_contents(oc, source_dir)
        return utils.response(f"Current source files for '{corpus_id}'", contents=objlist)
    except Exception as e:
        return utils.response(f"Failed to list source files in '{corpus_id}'", err=True, info=str(e)), 404


@bp.route("/remove-sources", methods=["DELETE"])
@login.login()
def remove_sources(oc, _user, _corpora, corpus_id):
    """Remove file paths listed in 'remove' (comma separated) from the corpus."""
    remove_files = request.args.get("remove") or request.form.get("remove") or ""
    remove_files = [i.strip() for i in remove_files.split(",") if i]
    if not remove_files:
        return utils.response("No files provided for removal", err=True), 404

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
        return utils.response(f"Failed to remove some source files form '{corpus_id}'.",
                              failed=fails, succeeded=successes, err=True), 404
    if fails:
        return utils.response("Failed to remove files", err=True), 404

    return utils.response(f"Source files for '{corpus_id}' successfully removed")


@bp.route("/download-sources", methods=["GET"])
@login.login()
def download_sources(oc, user, _corpora, corpus_id):
    """Download the corpus source files as a zip file.

    The parameter 'file' may be used to download a specific source file. This
    parameter must either be a file name or an absolute Nextcloud path. The `zip`
    parameter may be set to `false` in combination the the `file` param to avoid
    zipping the file to be downloaded.
    """
    download_file = request.args.get("file") or request.form.get("file") or ""

    # Check if there are any source files
    nc_source_dir = str(paths.get_source_dir(domain="nc", corpus_id=corpus_id, oc=oc))
    source_contents = storage.list_contents(oc, nc_source_dir, exclude_dirs=False)
    try:
        source_contents = storage.list_contents(oc, nc_source_dir, exclude_dirs=False)
        if source_contents == []:
            return utils.response(f"You have not uploaded any source files for corpus '{corpus_id}'", err=True), 404
    except Exception as e:
        return utils.response(f"Failed to download source files for corpus '{corpus_id}'", err=True, info=str(e)), 404

    local_source_dir = paths.get_source_dir(user=user, corpus_id=corpus_id, mkdir=True)

    # Download and zip file specified in args
    if download_file:
        full_download_file = download_file
        download_file_name = Path(download_file).name
        if not download_file.lstrip("/").startswith(nc_source_dir):
            full_download_file = "/" + str(Path(nc_source_dir) / download_file)
        if full_download_file not in [i.get("path") for i in source_contents]:
            return utils.response(f"The file '{download_file}' you are trying to download does not exist",
                                  err=True), 404
        try:
            local_path = local_source_dir / download_file_name
            zipped = request.args.get("zip", "") or request.form.get("zip", "")
            zipped = False if zipped.lower() == "false" else True
            if zipped:
                outf = str(local_source_dir / Path(f"{corpus_id}_{download_file_name}.zip"))
                oc.get_file(full_download_file, local_path)
                utils.create_zip(local_path, outf)
                return send_file(outf, mimetype="application/zip")
            else:
                outf = str(local_source_dir / Path(download_file_name))
                oc.get_file(full_download_file, local_path)
                # Determine content type
                content_type = "application/xml"
                for file_obj in source_contents:
                    if file_obj.get("name") == download_file_name:
                        content_type = file_obj.get("type")
                        break
                return send_file(outf, mimetype=content_type)
        except Exception as e:
            return utils.response(f"Failed to download file '{download_file}'", err=True, info=str(e)), 404

    # Download all files as zip archive
    try:
        zip_out = str(local_source_dir / f"{corpus_id}_source.zip")
        # Get files from Nextcloud
        oc.get_directory_as_zip(nc_source_dir, zip_out)
        return send_file(zip_out, mimetype="application/zip")
    except Exception as e:
        return utils.response(f"Failed to download source files for corpus '{corpus_id}'", err=True,
                              info=str(e)), 404


# ------------------------------------------------------------------------------
# Config file operations
# ------------------------------------------------------------------------------

@bp.route("/upload-config", methods=["PUT"])
@login.login()
def upload_config(oc, _user, corpora, corpus_id):
    """Upload a corpus config as file or plain text."""
    attached_files = list(request.files.values())
    config_txt = request.args.get("config") or request.form.get("config") or ""

    if attached_files and config_txt:
        return utils.response("Found both a config file and a plain text config but can only process one of these",
                              err=True), 404

    source_dir = str(paths.get_source_dir(domain="nc", corpus_id=corpus_id, oc=oc))
    source_files = storage.list_contents(oc, str(source_dir))

    # Process uploaded config file
    if attached_files:
        # Check if config file is YAML
        config_file = attached_files[0]
        if config_file.mimetype not in ("application/x-yaml", "text/yaml"):
            return utils.response("Config file needs to be YAML", err=True), 404

        config_contents = config_file.read()

        # Check if config file is compatible with the uploaded source files
        if source_files:
            compatible, resp = utils.config_compatible(config_contents, source_files[0])
            if not compatible:
                return resp, 404

        try:
            new_config = utils.set_corpus_id(config_contents, corpus_id)
            oc.put_file_contents(str(paths.get_config_file(domain="nc", corpus_id=corpus_id)), new_config)
            return utils.response(f"Config file successfully uploaded for '{corpus_id}'")
        except Exception as e:
            return utils.response(f"Failed to upload config file for '{corpus_id}'", err=True, info=str(e))

    elif config_txt:
        try:
            # Check if config file is compatible with the uploaded source files
            if source_files:
                compatible, resp = utils.config_compatible(config_txt, source_files[0])
                if not compatible:
                    return resp, 404
            new_config = utils.set_corpus_id(config_txt, corpus_id)
            oc.put_file_contents(str(paths.get_config_file(domain="nc", corpus_id=corpus_id)), new_config)
            return utils.response(f"Config file successfully uploaded for '{corpus_id}'")
        except Exception as e:
            return utils.response(f"Failed to upload config file for '{corpus_id}'", err=True, info=str(e))

    else:
        return utils.response("No config file provided for upload", err=True), 404


@bp.route("/download-config", methods=["GET"])
@login.login()
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
        return utils.response(f"Failed to download config file for corpus '{corpus_id}'", err=True, info=str(e)), 404


# ------------------------------------------------------------------------------
# Export file operations
# ------------------------------------------------------------------------------

@bp.route("/list-exports", methods=["GET"])
@login.login()
def list_exports(oc, _user, _corpora, corpus_id):
    """List exports available for download for a given corpus."""
    path = str(paths.get_export_dir(domain="nc", corpus_id=corpus_id))
    try:
        objlist = storage.list_contents(oc, path)
        return utils.response(f"Current export files for '{corpus_id}'", contents=objlist)
    except Exception as e:
        return utils.response(f"Failed to list files in '{corpus_id}'", err=True, info=str(e)), 404


@bp.route("/download-exports", methods=["GET"])
@login.login()
def download_export(oc, user, _corpora, corpus_id):
    """Download export files for a corpus as a zip file.

    The parameters 'file' and 'dir' may be used to download a specific export file
    or a directory of export files. These parameters must be supplied as absolute
    Nextcloud paths or paths relative to the export directory.
    The `zip` parameter may be set to `false` in combination the the `file` param
    to avoid zipping the file to be downloaded.
    """
    download_file = request.args.get("file") or request.form.get("file") or ""
    download_folder = request.args.get("dir") or request.form.get("dir") or ""

    if download_file and download_folder:
        return utils.response("The parameters 'dir' and 'file' must not be supplied simultaneously", err=True), 404

    nc_export_dir = str(paths.get_export_dir(domain="nc", corpus_id=corpus_id))
    local_corpus_dir = str(paths.get_corpus_dir(user=user, corpus_id=corpus_id, mkdir=True))

    try:
        export_contents = storage.list_contents(oc, nc_export_dir, exclude_dirs=False)
        if export_contents == []:
            return utils.response(f"There are currently no exports available for corpus '{corpus_id}'", err=True), 404
    except Exception as e:
        return utils.response(f"Failed to download exports for corpus '{corpus_id}'", err=True, info=str(e)), 404

    if not (download_file or download_folder):
        try:
            zip_out = str(local_corpus_dir / Path(f"{corpus_id}_export.zip"))
            # Get files from Nextcloud
            oc.get_directory_as_zip(nc_export_dir, zip_out)
            return send_file(zip_out, mimetype="application/zip")
        except Exception as e:
            return utils.response(f"Failed to download exports for corpus '{corpus_id}'", err=True, info=str(e)), 404

    # Download and zip folder specified in args
    if download_folder:
        full_download_folder = download_folder
        if not download_folder("/").startswith(nc_export_dir):
            full_download_folder = "/" + str(Path(nc_export_dir) / download_folder)
        if full_download_folder not in [i.get("path") for i in export_contents]:
            return utils.response(f"The folder '{download_folder}' you are trying to download does not exist",
                                  err=True), 404
        try:
            zip_out = str(local_corpus_dir / Path(f"{corpus_id}_{download_folder}.zip"))
            oc.get_directory_as_zip(full_download_folder, zip_out)
            return send_file(zip_out, mimetype="application/zip")
        except Exception as e:
            utils.response(f"Failed to download folder '{download_folder}'", err=True, info=str(e)), 404

    # Download and zip file specified in args
    if download_file:
        full_download_file = download_file
        download_file_name = Path(download_file).name
        if not download_file.lstrip("/").startswith(nc_export_dir):
            full_download_file = "/" + str(Path(nc_export_dir) / download_file)
        if full_download_file not in [i.get("path") for i in export_contents]:
            return utils.response(f"The file '{download_file}' you are trying to download does not exist",
                                  err=True), 404
        try:
            local_path = Path(local_corpus_dir) / download_file_name
            zipped = request.args.get("zip", "") or request.form.get("zip", "")
            zipped = False if zipped.lower() == "false" else True
            if zipped:
                outf = str(local_corpus_dir / Path(f"{corpus_id}_{download_file_name}.zip"))
                oc.get_file(full_download_file, local_path)
                utils.create_zip(local_path, outf)
                return send_file(outf, mimetype="application/zip")
            else:
                outf = str(local_corpus_dir / Path(download_file_name))
                oc.get_file(full_download_file, local_path)
                # Determine content type
                content_type = "application/xml"
                for file_obj in export_contents:
                    if file_obj.get("name") == download_file_name:
                        content_type = file_obj.get("type")
                        break
                return send_file(outf, mimetype=content_type)
        except Exception as e:
            return utils.response(f"Failed to download file '{download_file}'", err=True, info=str(e)), 404


@bp.route("/remove-exports", methods=["DELETE"])
@login.login()
def remove_exports(oc, user, _corpora, corpus_id):
    """Remove export files."""
    try:
        # Remove export dir from Nextcloud and create a new empty one
        export_dir = str(paths.get_export_dir(domain="nc", corpus_id=corpus_id))
        oc.delete(export_dir)
        paths.get_export_dir(domain="nc", corpus_id=corpus_id, oc=oc, mkdir=True)
    except Exception as e:
        return utils.response(f"Failed to remove export files for corpus '{corpus_id}'", err=True, info=str(e)), 404

    try:
        # Remove from Sparv server
        job = jobs.get_job(user, corpus_id)
        sparv_output = job.clean_export()
        app.logger.debug(f"Output from sparv clean --export: {sparv_output}")
    except Exception as e:
        app.logger.error(f"Failed to remove export files from Sparv server. {str(e)}")

    return utils.response(f"Export files for corpus '{corpus_id}' successfully removed")


@bp.route("/download-source-text", methods=["GET"])
@login.login()
def download_source_text(oc, user, _corpora, corpus_id):
    """Get one of the source files in plain text.

    The source file name (including its file extension) must be specified in the 'file' parameter.
    """
    download_file = request.args.get("file") or request.form.get("file") or ""

    nc_work_dir = str(paths.get_work_dir(domain="nc", corpus_id=corpus_id))
    local_corpus_dir = str(paths.get_corpus_dir(user=user, corpus_id=corpus_id, mkdir=True))

    if not download_file:
        return utils.response("Please specify the source file to download", err=True), 404

    try:
        source_texts = storage.list_contents(oc, nc_work_dir, exclude_dirs=False)
        if source_texts == []:
            return utils.response((f"There are currently no source texts for corpus '{corpus_id}'. "
                                    "You must run Sparv before you can view source texts."), err=True), 404
    except Exception as e:
        return utils.response(f"Failed to download source text for corpus '{corpus_id}'", err=True, info=str(e)), 404

    # Download file specified in args
    download_file_stem = Path(download_file).stem
    full_download_path = "/" + str(Path(nc_work_dir) / download_file_stem / app.config.get("SPARV_PLAIN_TEXT_FILE"))
    out_file_name = download_file_stem + "_plain.txt"
    if full_download_path not in [i.get("path") for i in source_texts]:
        return utils.response(f"The source text for the file '{download_file}' does not exist",
                                err=True), 404
    try:
        local_path = Path(local_corpus_dir) / out_file_name
        oc.get_file(full_download_path, local_path)
        return send_file(local_path, mimetype="text/plain")
    except Exception as e:
        return utils.response(f"Failed to download source text for file '{download_file}'", err=True, info=str(e)), 404


@bp.route("/check-changes", methods=["GET"])
@login.login()
def check_changes(oc, user, _corpora, corpus_id):
    """Check if config or source files have changed since the last job was started."""
    try:
        job = jobs.get_job(user, corpus_id)
        if not job.started:
            return utils.response(f"Failed to remove export files for corpus '{corpus_id}'", err=True), 404
        started = dateutil.parser.isoparse(job.started)

        # Get currenct source files on Nextclouds
        source_dir = str(paths.get_source_dir(domain="nc", corpus_id=corpus_id, oc=oc))
        try:
            source_files = storage.list_contents(oc, source_dir)
        except Exception as e:
            return utils.response(f"Failed to list source files in '{corpus_id}'", err=True, info=str(e)), 404
        # Check for new source files
        added_sources = []
        for sf in source_files:
            if sf not in job.available_files:
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
            if fileobj not in source_files:
                deleted_sources.append(fileobj)

        # Compare the config file modification time to the time stamp of the last job started
        changed_config = {}
        corpus_dir = str(paths.get_corpus_dir(domain="nc", corpus_id=corpus_id))
        corpus_files = storage.list_contents(oc, corpus_dir)
        config_file = paths.get_config_file(domain="nc", corpus_id=corpus_id)
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
        return utils.response(f"Failed to check changes for corpus '{corpus_id}'", err=True, info=str(e)), 404
