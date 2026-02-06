"""Metadata resource spec registration."""

from mink.core.jobs import BaseJob
from mink.core.resource import ResourceType
from mink.core.resource_specs import ResourceSpec, register_spec
from mink.metadata import storage

register_spec(
    ResourceType.metadata,
    ResourceSpec(
        storage=storage,
        job_cls=BaseJob,
        allowed_extensions=(".yaml", ".yml"),
        max_files=1,
        config_filename="",
        process_names=(),
    ),
)
