"""Metadata resource spec registration."""

from mink.core.jobs import BaseJob
from mink.core.resource import ResourceType
from mink.core.resource_specs import ResourceSpec, register_spec
from mink.metadata.config import metadata_settings
from mink.metadata.storage import storage

register_spec(
    ResourceType.metadata,
    ResourceSpec(
        storage=storage,
        job_cls=BaseJob,
        allowed_extensions=(".yaml", ".yml"),
        max_files=1,
        config_filename="",
        process_names=(),
        info_builder=lambda: {
            "description": metadata_settings.METADATA_RES_INFO,
        },
    ),
)
