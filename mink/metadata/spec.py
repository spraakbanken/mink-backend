"""Metadata resource spec registration."""

# ruff: file-ignore[import-outside-top-level], avoids circular import

from mink.core.resource import ResourceType
from mink.metadata.config import metadata_settings

METADATA = ResourceType("metadata")


def register() -> None:
    """Register the metadata resource spec."""
    from mink.core.jobs import BaseJob
    from mink.core.resource_specs import ResourceSpec, register_spec
    from mink.metadata.storage import storage

    register_spec(
        METADATA,
        ResourceSpec(
            storage=storage,
            job_cls=BaseJob,
            allowed_extensions=(".yaml", ".yml"),
            config_filename="",
            process_names=(),
            sbauth_resource_type="metadata",
            router_modules=("mink.metadata.routes",),
            info_builder=lambda: {
                "description": metadata_settings.METADATA_RES_INFO,
            },
        ),
    )
