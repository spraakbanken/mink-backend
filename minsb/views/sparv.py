"""Routes related to Sparv."""

import os
import subprocess

from flask import Blueprint
from flask import current_app as app
from flask import request

from minsb import utils, paths

bp = Blueprint("sparv", __name__)


@bp.route("/run-sparv", methods=["PUT"])
@utils.login()
def run_sparv(oc, user, corpora, corpus_id):
    """Run Sparv on given corpus."""
    # Parse requested exports
    sparv_exports = request.args.get("exports") or request.form.get("exports") or ""
    sparv_exports = [i for i in sparv_exports.split(",") if i] or app.config.get("SPARV_DEFAULT_EXPORTS")

    # Get relevant directories
    nc_corpus_dir = paths.get_corpus_dir(domain="nc", corpus_id=corpus_id)
    local_user_dir = paths.get_corpus_dir(user=user, mkdir=True)
    local_corpus_dir = paths.get_corpus_dir(user=user, corpus_id=corpus_id, mkdir=True)
    remote_corpus_dir = paths.get_corpus_dir(domain="sparv", user=user, corpus_id=corpus_id)

    sparv_user = app.config.get("SPARV_USER")
    sparv_server = app.config.get("SPARV_SERVER")

    # Check if required corpus contents are present
    corpus_contents = utils.list_contents(oc, nc_corpus_dir, exclude_dirs=False)
    if not app.config.get("SPARV_CORPUS_CONFIG") in [i.get("name") for i in corpus_contents]:
        return utils.response(f"No config file provided for '{corpus_id}'!", err=True)
    if not len([i for i in corpus_contents if i.get("path").endswith(app.config.get("SPARV_SOURCE_DIR"))]):
        return utils.response(f"No config file provided for '{corpus_id}'!", err=True)

    # Create file index with timestamps
    file_index = utils.create_file_index(corpus_contents, user)

    try:
        utils.download_dir(oc, nc_corpus_dir, local_user_dir, corpus_id, file_index)
    except Exception as e:
        return utils.response(f"Failed to download corpus '{corpus_id}' from Nextcloud!", err=True, info=str(e))

    # Create user and corpus dir on Sparv server
    p = subprocess.run(["ssh", "-i", "~/.ssh/id_rsa", f"{sparv_user}@{sparv_server}",
                        f"cd /home/{sparv_user} && mkdir -p {remote_corpus_dir}"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.stderr:
        return utils.response("Failed to create corpus dir on Sparv server!", err=True, info=p.stderr.decode()), 404

    # Sync corpus files to Sparv server
    local_source_dir = paths.get_source_dir(user=user, corpus_id=corpus_id)
    p = subprocess.run(["rsync", "-av", "--delete", local_source_dir,
                        f"{sparv_user}@{sparv_server}:~/{remote_corpus_dir}/"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.stderr:
        return utils.response("Failed to copy corpus files to Sparv server!", err=True, info=p.stderr.decode()), 404

    # Sync corpus config to Sparv server
    p = subprocess.run(["rsync", "-av", paths.get_config_file(user=user, corpus_id=corpus_id),
                        f"{sparv_user}@{sparv_server}:~/{remote_corpus_dir}/"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.stderr:
        return utils.response("Failed to copy corpus config file to Sparv server!", err=True,
                              info=p.stderr.decode()), 404

    # Run Sparv
    sparv_command = app.config.get("SPARV_COMMAND") + " run " + " ".join(sparv_exports)
    p = subprocess.run(["ssh", "-i", "~/.ssh/id_rsa", f"{sparv_user}@{sparv_server}",
                        f"cd /home/{sparv_user}/{remote_corpus_dir} && {sparv_command}"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.stderr:
        return utils.response("Failed to run Sparv!", err=True, info=p.stderr.decode()), 404
    sparv_output = p.stdout.decode() if p.stdout else ""
    sparv_output = "\n".join([line for line in sparv_output.split("\n") if not line.startswith("Progress:")]).strip()

    # Retrieve exports from Sparv
    remote_export_dir = paths.get_export_dir(domain="sparv", user=user, corpus_id=corpus_id)
    p = subprocess.run(["rsync", "-av", f"{sparv_user}@{sparv_server}:~/{remote_export_dir}",
                        local_corpus_dir], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.stderr:
        return utils.response("Failed to retrieve Sparv exports!", err=True, info=p.stderr.decode()), 404

    # Transfer exports to Nextcloud
    local_export_dir = paths.get_export_dir(user=user, corpus_id=corpus_id)
    try:
        utils.upload_dir(oc, nc_corpus_dir, local_export_dir, corpus_id, user, file_index)
    except Exception as e:
        return utils.response("Failed to upload exports to Nextcloud!", err=True, info=str(e))

    return utils.response("Sparv run successfully!", sparv_output=sparv_output)


@bp.route("/sparv-status", methods=["GET"])
@utils.login()
def sparv_status(oc, user, corpora, corpus_id):
    """Check the annotation status for a given corpus."""
    # TODO: Check if this is even possible in Sparv.
    return utils.response("Not yet implemented!", err=True), 501


@bp.route("/clear-annotations", methods=["DELETE"])
@utils.login()
def clear_annotations(oc, user, corpora, corpus_id):
    """Remove annotation files from Sparv server."""
    return utils.response("Not yet implemented!", err=True), 501
    # try:
    #     oc.delete(annotation_dir)
    #     return utils.response(f"Annotations for '{corpus_id}' successfully removed!")
    # except Exception as e:
    #     return utils.response(f"Could not remove annotations for '{corpus_id}'!", err=True, info=str(e)), 404
