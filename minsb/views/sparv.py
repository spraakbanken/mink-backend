"""Routes related to Sparv."""

import os
import subprocess

from flask import Blueprint
from flask import current_app as app
from flask import request

from minsb import utils

bp = Blueprint("sparv", __name__)


@bp.route("/run-sparv", methods=["PUT"])
@utils.login()
def run_sparv(oc, corpora, corpus_id):
    """Run Sparv on given corpus."""
    # TODO: What input args do we need? Maybe the export format (optionally)?
    user = request.authorization.username
    nextcloud_corpus_dir = os.path.join(app.config.get("CORPORA_DIR"), corpus_id)
    local_user_dir = os.path.join(app.instance_path, app.config.get("TMP_DIR"), user)
    local_corpus_dir = os.path.join(local_user_dir, corpus_id)
    remote_corpus_dir = os.path.join(app.config.get("REMOTE_CORPORA_DIR"), user, corpus_id)
    sparv_user = app.config.get("SPARV_USER")
    sparv_server = app.config.get("SPARV_SERVER")

    # Check if required corpus contents are present
    corpus_contents = utils.list_contents(oc, nextcloud_corpus_dir)
    if not app.config.get("SPARV_CORPUS_CONFIG") in [i.get("name") for i in corpus_contents]:
        return utils.response(f"No config file provided for '{corpus_id}'!", err=True)
    if not len([i for i in corpus_contents if i.get("path").endswith(app.config.get("SPARV_SOURCE_DIR"))]):
        return utils.response(f"No config file provided for '{corpus_id}'!", err=True)

    # Create temporary local corpus dir and get files from Nextcloud
    os.makedirs(local_user_dir, exist_ok=True)
    try:
        utils.download_dir(oc, nextcloud_corpus_dir, local_user_dir, user, corpus_id, corpus_contents)
    except Exception as e:
        return utils.response(f"Failed to download corpus '{corpus_id}' from Nextcloud!", err=True, info=str(e))

    # Create user and corpus dir on Sparv server
    p = subprocess.run(["ssh", "-i", "~/.ssh/id_rsa", f"{sparv_user}@{sparv_server}",
                        f"cd /home/{sparv_user} && mkdir -p {remote_corpus_dir}"], stderr=subprocess.PIPE)
    if p.stderr:
        return utils.response("Failed to create corpus dir on Sparv server!", err=True, info=p.stderr.decode()), 404

    # Sync corpus files to Sparv server
    local_source_dir = os.path.join(local_corpus_dir, app.config.get("SPARV_SOURCE_DIR"))
    p = subprocess.run(["rsync", "-av", "--delete", local_source_dir,
                        f"{sparv_user}@{sparv_server}:~/{remote_corpus_dir}/"], stderr=subprocess.PIPE)
    if p.stderr:
        return utils.response("Failed to copy corpus files to Sparv server!", err=True, info=p.stderr.decode()), 404
    local_config_file = os.path.join(local_corpus_dir, app.config.get("SPARV_CORPUS_CONFIG"))

    # Sync corpus config to Sparv server
    p = subprocess.run(["rsync", "-av", local_config_file,
                        f"{sparv_user}@{sparv_server}:~/{remote_corpus_dir}/"], stderr=subprocess.PIPE)
    if p.stderr:
        return utils.response("Failed to copy corpus config file to Sparv server!", err=True,
                              info=p.stderr.decode()), 404

    # Run Sparv
    sparv_command = app.config.get("SPARV_COMMAND") + " run xml_export:pretty"
    p = subprocess.run(["ssh", "-i", "~/.ssh/id_rsa", f"{sparv_user}@{sparv_server}",
                        f"cd /home/{sparv_user}/{remote_corpus_dir} && {sparv_command}"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.stderr:
        return utils.response("Failed to run Sparv!", err=True, info=p.stderr.decode()), 404
    sparv_output = p.stdout.decode() if p.stdout else ""
    sparv_output = "\n".join([line for line in sparv_output.split("\n") if not line.startswith("Progress:")]).strip()

    # Retrieve exports from Sparv
    export_dir = app.config.get("SPARV_EXPORT_DIR")
    p = subprocess.run(["rsync", "-av", f"{sparv_user}@{sparv_server}:~/{remote_corpus_dir}/{export_dir}",
                        local_corpus_dir], stderr=subprocess.PIPE)
    if p.stderr:
        return utils.response("Failed to retrieve Sparv exports!", err=True, info=p.stderr.decode()), 404

    # Transfer exports to Nextcloud
    try:
        utils.upload_dir(oc, nextcloud_corpus_dir, os.path.join(local_corpus_dir, export_dir))
    except Exception as e:
        return utils.response("Failed to upload exports to Nextcloud!", err=True, info=str(e))

    # TODO: cleanup tmp dir
    return utils.response("Sparv run successfully!", sparv_output=sparv_output)


@bp.route("/sparv-status", methods=["GET"])
@utils.login()
def sparv_status(oc, corpora, corpus_id):
    """Check the annotation status for a given corpus."""
    # TODO: Check if this is even possible in Sparv.
    return utils.response("Not yet implemented!", err=True), 501


@bp.route("/clear-annotations", methods=["DELETE"])
@utils.login()
def clear_annotations(oc, corpora, corpus_id):
    """Remove annotation files from Sparv server."""
    return utils.response("Not yet implemented!", err=True), 501
    # try:
    #     oc.delete(annotation_dir)
    #     return utils.response(f"Annotations for '{corpus_id}' successfully removed!")
    # except Exception as e:
    #     return utils.response(f"Could not remove annotations for '{corpus_id}'!", err=True, info=str(e)), 404
