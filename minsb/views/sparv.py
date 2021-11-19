"""Routes related to Sparv."""

import time

from flask import Blueprint
from flask import current_app as app
from flask import request

from minsb import exceptions, jobs, queue, utils

bp = Blueprint("sparv", __name__)


@bp.route("/run-sparv", methods=["PUT"])
@utils.login()
def run_sparv(oc, user, _corpora, corpus_id):
    """Run Sparv on given corpus."""
    # Parse requested exports
    sparv_exports = request.args.get("exports") or request.form.get("exports") or ""
    sparv_exports = [i.strip() for i in sparv_exports.split(",") if i] or app.config.get("SPARV_DEFAULT_EXPORTS")

    files = request.args.get("files") or request.form.get("files") or ""
    files = [i.strip() for i in files.split(",") if i]

    # Queue job
    job = jobs.get_job(user, corpus_id, sparv_exports=sparv_exports, files=files)
    try:
        job = queue.add(job)
    except Exception as e:
        return utils.response(f"Failed to queue job for '{corpus_id}'", err=True, info=str(e)), 404

    # Start syncing
    try:
        job.sync_to_sparv(oc)
    except Exception as e:
        return utils.response(f"Failed to start job for '{corpus_id}'", err=True, info=str(e)), 404

    # Wait a few seconds to check whether anything terminated early
    time.sleep(3)
    return make_status_response(job, oc)


@bp.route("/advance-queue", methods=["PUT"])
@utils.gatekeeper
def advance_queue():
    """Check the job queue and attempt to advance it.

    1. Unqueue jobs that are done, aborted or erroneous
    2. For jobs with status "annotating", check if process is still running
    3. Run the next job in the queue if there are fewer running jobs than allowed

    For internal use only!
    """
    # Unqueue jobs that are done, aborted or erroneous
    queue.unqueue_old()

    # For jobs with status "annotating", check if process is still running
    running_jobs, waiting_jobs = queue.get_running_waiting()
    app.logger.debug(f"Running jobs: {len(running_jobs)}  Waiting jobs: {len(waiting_jobs)}")
    for job in running_jobs:
        try:
            if not job.process_running():
                running_jobs.remove(job)
        except Exception as e:
            app.logger.error(f"Failed to check if process is running for '{job.id}' {str(e)}")

    # If there are fewer running jobs than allowed, start the next one in the queue
    while waiting_jobs and len(running_jobs) < app.config.get("SPARV_WORKERS", 1):
        job = waiting_jobs.pop(0)
        try:
            job.run_sparv()
            running_jobs.append(job)
            app.logger.info(f"Started annotation process for '{job.id}'")
        except Exception as e:
            app.logger.error(f"Failed to run Sparv on '{job.id}' {str(e)}")

    return utils.response("Queue advancing completed")


@bp.route("/check-status", methods=["GET"])
@utils.login(require_corpus_id=False)
def check_status(oc, user, corpora):
    """Check the annotation status for all jobs belonging to a user or a given corpus."""
    corpus_id = request.args.get("corpus_id") or request.form.get("corpus_id")
    if corpus_id:
        try:
            # Check if corpus exists
            if corpus_id not in corpora:
                return utils.response(f"Corpus '{corpus_id}' does not exist", err=True), 404
            job = jobs.get_job(user, corpus_id)
            return make_status_response(job, oc)
        except Exception as e:
            return utils.response(f"Failed to get job status for '{corpus_id}'", err=True, info=str(e)), 404

    try:
        # Get all job statuses for user
        job_list = []
        user_jobs = queue.get_user_jobs(user)
        for job in user_jobs:
            resp = make_status_response(job, oc)
            if isinstance(resp, tuple):
                resp = resp[0]
            job_status = {"corpus_id": job.corpus_id}
            job_status.update(resp.get_json())
            job_status.pop("status")
            job_list.append(job_status)
        return utils.response("Listing jobs", jobs=job_list)
    except Exception as e:
        return utils.response("Failed to get job statuses", err=True, info=str(e)), 404


@bp.route("/abort-job", methods=["POST"])
@utils.login()
def abort_job(_oc, user, _corpora, corpus_id):
    """Try to abort a running job."""
    job = jobs.get_job(user, corpus_id)
    try:
        job.abort_sparv()
    except exceptions.ProcessNotRunning:
        return utils.response(f"No running job found for '{corpus_id}'")
    except Exception as e:
        return utils.response(f"Failed to abort job for '{corpus_id}'", err=True, info=str(e)), 404
    return utils.response(f"Successfully aborted running job for '{corpus_id}'", job_status=job.status.name)


@bp.route("/clear-annotations", methods=["DELETE"])
@utils.login()
def clear_annotations(oc, user, _corpora, corpus_id):
    """Remove annotation files from Sparv server."""
    # Check if there is an active job
    job = jobs.get_job(user, corpus_id)
    if jobs.Status.none < job.status < jobs.Status.done_annotating:
        return utils.response("Cannot clear annotations while a job is running", err=True), 404

    try:
        sparv_output = job.clean()
        return utils.response(f"Annotations for '{corpus_id}' successfully removed", sparv_output=sparv_output)
    except Exception as e:
        return utils.response("Failed to clear annotations", err=True, info=str(e)), 404


def make_status_response(job, oc):
    """Check the annotation status for a given corpus and return response."""
    status = job.status
    job_attrs = {"job_status": status.name, "sparv_exports": job.sparv_exports, "started": job.started}
    if job.files:
        job_attrs["files"] = job.files

    if status == jobs.Status.none:
        return utils.response(f"There is no active job for '{job.corpus_id}'", job_status=status.name, err=True), 404

    if status == jobs.Status.syncing_corpus:
        return utils.response("Corpus files are being synced to the Sparv server", **job_attrs)

    if status == jobs.Status.waiting:
        return utils.response("Job has been queued", **job_attrs, priority=queue.get_priority(job))

    if status == jobs.Status.aborted:
        return utils.response("Job was aborted by the user", **job_attrs)

    progress, warnings, errors, output = job.get_output()

    if status == jobs.Status.annotating:
        return utils.response("Sparv is running", progress=progress, warnings=warnings, errors=errors,
                              sparv_output=output, **job_attrs)

    # If done annotating, retrieve exports from Sparv
    if status == jobs.Status.done_annotating:
        try:
            job.sync_results(oc)
        except Exception as e:
            return utils.response("Sparv was run successfully but exports failed to upload to Nextcloud",
                                  err=True, info=str(e)), 404
        return utils.response("Sparv was run successfully! Starting to sync results",
                              warnings=warnings, errors=errors, sparv_output=output, **job_attrs)

    if status == jobs.Status.syncing_results:
        return utils.response("Result files are being synced from the Sparv server", **job_attrs)

    if status == jobs.Status.done:
        return utils.response("Corpus is done processing and the results have been synced", warnings=warnings,
                              errors=errors, sparv_output=output, **job_attrs)

    if status == jobs.Status.error:
        return utils.response("An error occurred while annotating", err=True, warnings=warnings,
                              errors=errors, sparv_output=output, **job_attrs), 404

    return utils.response("Cannot handle this Sparv status yet", warnings=warnings, errors=errors, sparv_output=output,
                          **job_attrs), 501


@bp.route("/sparv-languages", methods=["GET"])
def sparv_languages():
    """List languages available in Sparv."""
    try:
        job = jobs.DefaultJob()
        languages = job.list_languages()
    except Exception as e:
        return utils.response("Failed to retrieve languages listing", err=True, info=str(e)), 404
    return utils.response("Listing languages available in Sparv", languages=languages)


@bp.route("/sparv-exports", methods=["GET"])
def sparv_exports():
    """List available Sparv exports for current language (default: swe)."""
    language = request.args.get("language") or request.form.get("language") or "swe"
    try:
        job = jobs.DefaultJob(language=language)
        exports = job.list_exports()
    except Exception as e:
        return utils.response("Failed to retrieve exports listing", err=True, info=str(e)), 404
    return utils.response("Listing exports available in Sparv", language=language, exports=exports)
