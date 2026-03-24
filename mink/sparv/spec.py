"""Sparv resource spec registration."""

from enum import StrEnum
from typing import Any, cast

from mink.core import return_codes
from mink.core.resource import ResourceType
from mink.sparv.config import sparv_settings

CORPUS = ResourceType("corpus")


class ProcessName(StrEnum):
    """Enum class for Sparv process names."""

    sync2sparv = "sync2sparv"
    sync2storage = "sync2storage"
    sparv = "sparv"
    korp = "korp"
    strix = "strix"


def register() -> None:
    """Register the Sparv resource spec."""
    from mink.core import exceptions  # noqa: PLC0415, avoids circular import
    from mink.core.config import settings  # noqa: PLC0415, avoids circular import
    from mink.core.logging import logger  # noqa: PLC0415, avoids circular import
    from mink.core.resource_specs import ResourceSpec, register_spec  # noqa: PLC0415, avoids circular import
    from mink.sparv import models as sparv_models  # noqa: PLC0415, avoids circular import
    from mink.sparv.jobs import SparvJob  # noqa: PLC0415, avoids circular import
    from mink.sparv.storage import storage  # noqa: PLC0415, avoids circular import

    def startup_check() -> None:
        if not sparv_settings.SPARV_HOST:
            if settings.ENV != "development":
                raise exceptions.ConfigVariableNotSetError("SPARV_HOST")
            logger.warning("'SPARV_HOST' not set, Sparv will not be available!")
            sparv_settings.SPARV_ENABLED = False
        if not sparv_settings.SPARV_USER:
            if settings.ENV != "development":
                raise exceptions.ConfigVariableNotSetError("SPARV_USER")
            logger.warning("'SPARV_USER' not set, Sparv will not be available!")
            sparv_settings.SPARV_ENABLED = False

    def process_running(job: Any) -> bool:
        return cast(SparvJob, job).process_running()

    def run_sparv(job: Any) -> None:
        cast(SparvJob, job).run_sparv()

    def install_korp(job: Any) -> None:
        cast(SparvJob, job).install_korp()

    def install_strix(job: Any) -> None:
        cast(SparvJob, job).install_strix()

    def on_done_sync(info_obj: Any, admin: bool) -> dict[str, Any] | None:
        if admin or storage.local:
            return None
        job = cast(SparvJob, info_obj.job)
        try:
            job.sync_results()
        except Exception as e:
            return {
                "message": return_codes.FAILED_SYNCING.message,
                "return_code": return_codes.FAILED_SYNCING.code,
                "info": f"Job was run successfully but syncing to storage server failed: {e}",
            }
        return {
            "message": return_codes.STARTED_SYNCING.message,
            "return_code": return_codes.STARTED_SYNCING.code,
        }

    register_spec(
        CORPUS,
        ResourceSpec(
            storage=storage,
            job_cls=SparvJob,
            allowed_extensions=tuple(sparv_settings.SPARV_IMPORTER_MODULES.keys()),
            config_filename=sparv_settings.SPARV_CORPUS_CONFIG,
            process_names=tuple(p.name for p in ProcessName),
            sbauth_resource_type="corpora",
            router_modules=("mink.sparv.storage_routes", "mink.sparv.process_routes"),
            process_running=process_running,
            queue_handlers={
                ProcessName.sparv.name: run_sparv,
                ProcessName.korp.name: install_korp,
                ProcessName.strix.name: install_strix,
            },
            sync_processes=(ProcessName.sync2sparv.name, ProcessName.sync2storage.name),
            no_output_processes=(ProcessName.sync2sparv.name, ProcessName.sync2storage.name),
            on_done_sync=on_done_sync,
            startup_check=startup_check,
            openapi_examples={
                "JobModel": sparv_models.job_model_examples,
                "JobStatusModel": sparv_models.job_status_examples,
                "StatusResponse": sparv_models.status_response_examples,
                "StatusesResponse": sparv_models.statuses_response_examples,
            },
            info_builder=lambda: {
                "description": sparv_settings.SPARV_RES_INFO,
                "importer_modules": {
                    "info": "Sparv importer modules for different file extensions",
                    "data": [
                        {"file_extension": k, "importer": v}
                        for k, v in sparv_settings.SPARV_IMPORTER_MODULES.items()
                    ],
                },
                "recommended_file_size": {
                    "info": "approximate recommended file sizes (in bytes) when processing many files with Sparv",
                    "data": [
                        {
                            "name": "recommended_min_file_length",
                            "description": "recommended min size for one corpus source file",
                            "value": sparv_settings.SPARV_RECOMMENDED_MIN_FILE_LENGTH,
                        },
                        {
                            "name": "recommended_max_file_length",
                            "description": "recommended max size for one corpus source file",
                            "value": sparv_settings.SPARV_RECOMMENDED_MAX_FILE_LENGTH,
                        },
                    ],
                },
            },
        ),
    )
