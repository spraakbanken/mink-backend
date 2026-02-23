"""Metadata resource spec registration."""

from mink.core.resource import ResourceType
from mink.metadata.config import metadata_settings


def register() -> None:
    """Register the metadata resource spec."""
    from mink.core.jobs import BaseJob  # noqa: PLC0415
    from mink.core.resource_specs import ResourceSpec, register_spec  # noqa: PLC0415
    from mink.metadata.storage import storage  # noqa: PLC0415

    register_spec(
        ResourceType.metadata,
        ResourceSpec(
            storage=storage,
            job_cls=BaseJob,
            allowed_extensions=(".yaml", ".yml"),
            config_filename="",
            process_names=(),
            router_modules=("mink.metadata.routes",),
            info_builder=lambda: {
                "description": metadata_settings.METADATA_RES_INFO,
            },
        ),
    )
