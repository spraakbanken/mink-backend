"""Routes related to Sparv."""

import subprocess
import time

from flask import Blueprint
from flask import current_app as app
from flask import request

from minsb import jobs, paths, utils

bp = Blueprint("sparv", __name__)


@bp.route("/run-sparv", methods=["PUT"])
@utils.login()
def run_sparv(oc, user, corpora, corpus_id):
    """Run Sparv on given corpus."""
    # Avoid running multiple jobs on same corpus simultaneously
    status = jobs.get_status(user, corpus_id)
    if status == jobs.Status.running:
        return utils.response(f"There is an unfinished job for '{corpus_id}'!", err=True), 404

    # Parse requested exports
    sparv_exports = request.args.get("exports") or request.form.get("exports") or ""
    sparv_exports = [i for i in sparv_exports.split(",") if i] or app.config.get("SPARV_DEFAULT_EXPORTS")

    # Get relevant directories
    nc_corpus_dir = str(paths.get_corpus_dir(domain="nc", corpus_id=corpus_id))
    local_user_dir = str(paths.get_corpus_dir(user=user, mkdir=True))
    remote_corpus_dir = str(paths.get_corpus_dir(domain="sparv", user=user, corpus_id=corpus_id))

    sparv_user = app.config.get("SPARV_USER")
    sparv_server = app.config.get("SPARV_SERVER")
    nohupfile = app.config.get("SPARV_NOHUP_FILE")
    runscript = app.config.get("SPARV_TMP_RUN_SCRIPT")

    # Check if required corpus contents are present
    corpus_contents = utils.list_contents(oc, nc_corpus_dir, exclude_dirs=False)
    if not app.config.get("SPARV_CORPUS_CONFIG") in [i.get("name") for i in corpus_contents]:
        return utils.response(f"No config file provided for '{corpus_id}'!", err=True), 404
    if not len([i for i in corpus_contents if i.get("path").endswith(app.config.get("SPARV_SOURCE_DIR"))]):
        return utils.response(f"No config file provided for '{corpus_id}'!", err=True), 404

    # Create file index with timestamps
    file_index = utils.create_file_index(corpus_contents, user)

    try:
        utils.download_dir(oc, nc_corpus_dir, local_user_dir, corpus_id, file_index)
    except Exception as e:
        return utils.response(f"Failed to download corpus '{corpus_id}' from Nextcloud!", err=True, info=str(e)), 404

    # Create user and corpus dir on Sparv server
    p = subprocess.run(["ssh", "-i", "~/.ssh/id_rsa", f"{sparv_user}@{sparv_server}",
                        f"cd /home/{sparv_user} && mkdir -p {remote_corpus_dir} && rm -f {nohupfile} {runscript}"],
                       capture_output=True)
    if p.stderr:
        return utils.response("Failed to create corpus dir on Sparv server!", err=True, info=p.stderr.decode()), 404

    # Sync corpus files to Sparv server
    local_source_dir = paths.get_source_dir(user=user, corpus_id=corpus_id)
    p = subprocess.run(["rsync", "-av", "--delete", local_source_dir,
                        f"{sparv_user}@{sparv_server}:~/{remote_corpus_dir}/"],
                       capture_output=True)
    if p.stderr:
        return utils.response("Failed to copy corpus files to Sparv server!", err=True, info=p.stderr.decode()), 404

    # Sync corpus config to Sparv server
    p = subprocess.run(["rsync", "-av", paths.get_config_file(user=user, corpus_id=corpus_id),
                        f"{sparv_user}@{sparv_server}:~/{remote_corpus_dir}/"],
                       capture_output=True)
    if p.stderr:
        return utils.response("Failed to copy corpus config file to Sparv server!", err=True,
                              info=p.stderr.decode()), 404

    # Run Sparv
    sparv_command = app.config.get("SPARV_COMMAND") + " run --log-to-file info " + " ".join(sparv_exports)
    p = subprocess.run(["ssh", "-i", "~/.ssh/id_rsa", f"{sparv_user}@{sparv_server}",
                        (f"cd /home/{sparv_user}/{remote_corpus_dir}"
                         f" && echo 'nohup {sparv_command} >{nohupfile} 2>&1 &\necho $!' > {runscript}"
                         f" && chmod +x {runscript} && ./{runscript}")],
                        #  f" && nohup {sparv_command} > {nohupfile} 2>&1 & echo $!")],
                       capture_output=True)

    if p.returncode != 0:
        stderr = p.stderr.decode() if p.stderr else ""
        return utils.response("Failed to run Sparv!", err=True, stderr=stderr), 404

    # Get pid from Sparv process and store job info
    pid = int(p.stdout.decode())
    jobs.set_status(user, corpus_id, jobs.Status.running, pid=pid)

    # Wait a few seconds and poll to check whether the Sparv terminated early
    time.sleep(5)
    return make_status_response(oc, user, corpus_id)


@bp.route("/check-status", methods=["GET"])
@utils.login()
def check_status(oc, user, corpora, corpus_id):
    """Check the annotation status for a given corpus (wrapper for make_status_response)."""
    return make_status_response(oc, user, corpus_id)


@bp.route("/clear-annotations", methods=["DELETE"])
@utils.login()
def clear_annotations(oc, user, corpora, corpus_id):
    """Remove annotation files from Sparv server."""
    # Check if there is an active job
    if jobs.get_status(user, corpus_id) == jobs.Status.running:
        return utils.response("Cannot clear annotations while a job is running!", err=True), 404

    remote_corpus_dir = paths.get_corpus_dir(domain="sparv", user=user, corpus_id=corpus_id)
    sparv_user = app.config.get("SPARV_USER")
    sparv_server = app.config.get("SPARV_SERVER")
    nohupfile = app.config.get("SPARV_NOHUP_FILE")
    runscript = app.config.get("SPARV_TMP_RUN_SCRIPT")

    # Run sparv clean
    sparv_command = app.config.get("SPARV_COMMAND") + " clean --all"
    p = subprocess.run([
        "ssh", "-i", "~/.ssh/id_rsa", f"{sparv_user}@{sparv_server}",
        f"cd /home/{sparv_user}/{remote_corpus_dir} && rm -f {nohupfile} {runscript} && {sparv_command}"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if p.stderr:
        return utils.response("Failed to clear annotations!", err=True, info=p.stderr.decode()), 404
    sparv_output = p.stdout.decode() if p.stdout else ""
    sparv_output = ", ".join([line for line in sparv_output.split("\n") if line])

    return utils.response(f"Annotations for '{corpus_id}' successfully removed!", sparv_output=sparv_output)


def remove_corpus(user, corpus_id):
    """Remove entire corpus from Sparv server."""
    remote_corpus_dir = paths.get_corpus_dir(domain="sparv", user=user, corpus_id=corpus_id)
    sparv_user = app.config.get("SPARV_USER")
    sparv_server = app.config.get("SPARV_SERVER")

    # Check if there is an active job
    if jobs.get_status(user, corpus_id) == jobs.Status.running:
        app.logger.error(f"Failed to remove corpus dir '{remote_corpus_dir}' due to an active job!")

    # Run sparv clean
    p = subprocess.run(["ssh", "-i", "~/.ssh/id_rsa", f"{sparv_user}@{sparv_server}",
                        f"rm -rf /home/{sparv_user}/{remote_corpus_dir}"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.stderr:
        app.logger.error(f"Failed to remove corpus dir '{remote_corpus_dir}'!")


def make_status_response(oc, user, corpus_id):
    """Check the annotation status for a given corpus and return response."""
    status = jobs.get_status(user, corpus_id)
    if status == jobs.Status.none:
        return utils.response(f"There is no job for '{corpus_id}'!", sparv_status=status.name, err=True), 404

    output = jobs.get_output(user, corpus_id)

    if status == jobs.Status.running:
        return utils.response("Sparv is running!", sparv_output=output, sparv_status=status.name)

    # If done retrieve exports from Sparv
    if status == jobs.Status.done:
        nc_corpus_dir = str(paths.get_corpus_dir(domain="nc", corpus_id=corpus_id))
        corpus_contents = utils.list_contents(oc, nc_corpus_dir, exclude_dirs=False)
        file_index = utils.create_file_index(corpus_contents, user)
        try:
            sync_exports(user, corpus_id, oc, file_index)
        except Exception as e:
            return utils.response("Failed to upload exports to Nextcloud!", err=True, info=str(e)), 404
        return utils.response("Sparv was run successfully!", sparv_output=output, sparv_status=status.name)

    # TODO: Error handling
    # if status == jobs.Status.error:
    #     return utils.response("An error occurred while annotating!", err=True), 404

    return utils.response("Cannot handle this Sparv status yet!", sparv_output=output, sparv_status=status.name)


def sync_exports(user, corpus_id, oc, file_index):
    """Sync exports from Sparv server to Nextcloud."""
    sparv_user = app.config.get("SPARV_USER")
    sparv_server = app.config.get("SPARV_SERVER")
    local_corpus_dir = str(paths.get_corpus_dir(user=user, corpus_id=corpus_id, mkdir=True))
    nc_corpus_dir = str(paths.get_corpus_dir(domain="nc", corpus_id=corpus_id))

    remote_export_dir = paths.get_export_dir(domain="sparv", user=user, corpus_id=corpus_id)
    p = subprocess.run(["rsync", "-av", f"{sparv_user}@{sparv_server}:~/{remote_export_dir}",
                        local_corpus_dir], capture_output=True)
    if p.stderr:
        return utils.response("Failed to retrieve Sparv exports!", err=True, info=p.stderr.decode()), 404

    # Transfer exports to Nextcloud
    local_export_dir = paths.get_export_dir(user=user, corpus_id=corpus_id)
    try:
        utils.upload_dir(oc, nc_corpus_dir, local_export_dir, corpus_id, user, file_index)
    except Exception as e:
        raise Exception(f"Failed to upload exports to Nextcloud! {e}")
