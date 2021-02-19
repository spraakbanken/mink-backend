"""Routes related to Sparv."""

import time

from flask import Blueprint
from flask import current_app as app
from flask import request

from minsb import jobs, queue, utils

bp = Blueprint("sparv", __name__)


@bp.route("/run-sparv", methods=["PUT"])
@utils.login()
def run_sparv(oc, user, _corpora, corpus_id):
    """Run Sparv on given corpus."""
    # Parse requested exports
    sparv_exports = request.args.get("exports") or request.form.get("exports") or ""
    sparv_exports = [i for i in sparv_exports.split(",") if i] or app.config.get("SPARV_DEFAULT_EXPORTS")

    # Queue job
    job = jobs.get_job(user, corpus_id, sparv_exports=sparv_exports)
    try:
        job = queue.add(job)
    except Exception as e:
        return utils.response(f"Failed to queue job for '{corpus_id}'!", err=True, info=str(e)), 404

    # Start syncing
    try:
        job.sync_to_sparv(oc)
    except Exception as e:
        return utils.response(f"Failed to start job for '{corpus_id}'!", err=True, info=str(e)), 404

    # Wait a few seconds to check whether anything terminated early
    time.sleep(3)
    return make_status_response(job, oc)


@bp.route("/check-status", methods=["GET"])
@utils.login()
def check_status(oc, user, _corpora, corpus_id):
    """Check the annotation status for a given corpus (wrapper for make_status_response)."""
    job = jobs.get_job(user, corpus_id)
    return make_status_response(job, oc)


@bp.route("/clear-annotations", methods=["DELETE"])
@utils.login()
def clear_annotations(oc, user, _corpora, corpus_id):
    """Remove annotation files from Sparv server."""
    # Check if there is an active job
    job = jobs.get_job(user, corpus_id)
    if jobs.Status.none < job.status < jobs.Status.synced:
        return utils.response("Cannot clear annotations while a job is running!", err=True), 404

    try:
        sparv_output = job.clean()
        return utils.response(f"Annotations for '{corpus_id}' successfully removed!", sparv_output=sparv_output)
    except Exception as e:
        return utils.response("Failed to clear annotations!", err=True, info=e), 404


def make_status_response(job, oc):
    """Check the annotation status for a given corpus and return response."""
    status = job.status

    if status == jobs.Status.none:
        return utils.response(f"There is no active job for '{job.corpus_id}'!", job_status=status.name, err=True), 404

    if status == jobs.Status.syncing:
        return utils.response("Corpus files are being synced to the Sparv server!", job_status=status.name)

    if status == jobs.Status.queued:
        return utils.response("Job has been queued!", job_status=status.name, priority=queue.get_priority(job))

    output = job.get_output()

    if status == jobs.Status.running:
        return utils.response("Sparv is running!", sparv_output=output, job_status=status.name)

    # If done retrieve exports from Sparv
    if status == jobs.Status.done:
        try:
            job.sync_exports(oc)
        except Exception as e:
            return utils.response("Failed to upload exports to Nextcloud!", err=True, info=str(e)), 404
        return utils.response("Sparv was run successfully!", sparv_output=output, job_status=status.name)

    # TODO: Error handling
    # if status == jobs.Status.error:
    #     return utils.response("An error occurred while annotating!", err=True), 404

    return utils.response("Cannot handle this Sparv status yet!", sparv_output=output, job_status=status.name), 501
