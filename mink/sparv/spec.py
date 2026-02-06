"""Sparv resource spec registration."""

from mink.core.config import settings
from mink.core.jobs import Job
from mink.core.resource import ResourceType
from mink.core.resource_specs import ResourceSpec, register_spec
from mink.core.status import ProcessName
from mink.sparv import storage

register_spec(
    ResourceType.corpus,
    ResourceSpec(
        storage=storage,
        job_cls=Job,
        allowed_extensions=tuple(settings.SPARV_IMPORTER_MODULES.keys()),
        max_files=-1,
        config_filename=settings.SPARV_CORPUS_CONFIG,
        process_names=tuple(p.name for p in ProcessName),
    ),
)
