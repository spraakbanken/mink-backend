"""Karp resource spec registration."""

from enum import StrEnum, auto
from typing import Any, cast

from mink.core.resource import ResourceType
from mink.karp.config import karp_settings

LEXICON = ResourceType("lexicon")


class ProcessName(StrEnum):
    """Enum class for Karp process names."""

    karp_pipeline = auto()
    karps = auto()


def register() -> None:
    """Register the Karp resource spec."""
    from mink.core import exceptions  # noqa: PLC0415, avoids circular import
    from mink.core.config import settings  # noqa: PLC0415, avoids circular import
    from mink.core.logging import logger  # noqa: PLC0415, avoids circular import
    from mink.core.resource_specs import ResourceSpec, register_spec  # noqa: PLC0415, avoids circular import
    from mink.karp.jobs import KarpJob  # noqa: PLC0415, avoids circular import
    from mink.karp.storage import storage  # noqa: PLC0415, avoids circular import

    def startup_check() -> None:
        for var in ["KARP_HOST", "KARP_USER", "KARP_DATA_DIR", "KARP_PARENT_CONFIG", "KARP_COMMAND"]:
            if not getattr(karp_settings, var):
                if settings.ENV != "development":
                    raise exceptions.ConfigVariableNotSetError(var)
                logger.warning(f"'{var}' not set, Karp will not be available!")
                karp_settings.KARP_ENABLED = False

    def process_running(job: Any) -> bool:
        return cast(KarpJob, job).process_running()

    def run_karp_pipeline(job: Any) -> None:
        cast(KarpJob, job).run_karp_pipeline()

    def install_karps(job: Any) -> None:
        cast(KarpJob, job).install_karps()

    register_spec(
        LEXICON,
        ResourceSpec(
            storage=storage,
            job_cls=KarpJob,
            allowed_extensions=(".jsonl",),
            config_filename=karp_settings.KARP_CONFIG,
            process_names=tuple(p.name for p in ProcessName),
            sbauth_resource_type="lexica",
            router_modules=("mink.karp.storage_routes", "mink.karp.process_routes"),
            process_running=process_running,
            queue_handlers={
                ProcessName.karp_pipeline.name: run_karp_pipeline,
                ProcessName.karps.name: install_karps,
            },
            sync_processes=(),
            no_output_processes=(),
            startup_check=startup_check,
            info_builder=lambda: {
                "description": karp_settings.KARP_RES_INFO,
            },
        ),
    )
