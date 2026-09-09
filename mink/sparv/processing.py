"""Shared services for starting Sparv corpus jobs."""

from mink.core import exceptions, registry, return_codes
from mink.core.info import Info
from mink.core.status import Status
from mink.sparv import utils as sparv_utils
from mink.sparv.config import sparv_settings
from mink.sparv.jobs import SparvJob
from mink.sparv.spec import ProcessName
from mink.sparv.storage import storage


def require_job(job: object) -> SparvJob:
    """Ensure that 'job' is a Sparv job, raise an error if not."""
    if not isinstance(job, SparvJob):
        raise exceptions.MinkHTTPException(
            return_code=return_codes.INVALID_RESOURCE_TYPE, info="Expected a corpus resource"
        )
    return job


def run_sparv(info_item: Info, exports: list[str] | None = None, files: list[str] | None = None) -> None:
    """Validate inputs and queue a Sparv annotation job.

    Args:
        info_item: The corpus resource and job to process.
        exports: Export formats to produce, or None to use the configured defaults.
        files: Source file names without extensions, or None to process all files.
    """
    resource_id = info_item.id

    # Parse requested exports
    if exports is None:
        exports = []
    exports = [i.strip() for i in exports if i] or sparv_settings.SPARV_DEFAULT_EXPORTS

    # Parse list of files to be processed
    if files is None:
        files = []
    files = [i.strip() for i in files if i]

    # Get list of available source files to be stored in the job info
    try:
        source_files = storage.list_contents(storage.get_source_dir(resource_id))
    except Exception as e:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.FAILED_RUNNING, info=f"Failed to list source files: {e}"
        ) from e

    if not source_files:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.FILE_NOT_FOUND, info="No source files found for this resource"
        )

    # Check compatibility between source files and config
    try:
        config_contents = storage.get_file_contents(storage.get_config_file(resource_id))
    except Exception as e:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.FAILED_RUNNING, info=f"Failed to get config file: {e}"
        ) from e
    sparv_utils.require_compatible_config(config_contents, source_files)

    # Check for changes and remove exports if necessary
    sources_deleted = config_changed = False

    try:
        if info_item.job.started:
            _, sources_deleted, config_changed = storage.get_file_changes(resource_id, info_item)
    except Exception as e:
        raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_RUNNING, info=str(e)) from e
    if sources_deleted or config_changed:
        sparv_output = None
        try:
            job = require_job(info_item.job)
            success, sparv_output = job.clean_export()
            assert success
        except Exception as e:
            raise exceptions.MinkHTTPException(
                return_code=return_codes.FAILED_RUNNING,
                info=f"Failed to remove outdated export files before running Sparv: {e}",
                sparv_message=sparv_output,
            ) from e

    job = require_job(info_item.job)
    job.set_attribute("sparv_exports", exports)
    job.set_attribute("current_files", files)

    # Queue job
    try:
        job = registry.add_to_queue(job)
    except Exception as e:
        raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_QUEUING, info=str(e)) from e

    # Check that all required files are present
    job = require_job(job)
    job.check_requirements()

    if storage.local:
        job.set_status(Status.waiting, ProcessName.sparv)
    else:
        # Sync files
        try:
            job.sync_to_sparv()
        except Exception as e:
            raise exceptions.MinkHTTPException(
                return_code=return_codes.FAILED_RUNNING, info=f"Failed to sync files to Sparv: {e}"
            ) from e
