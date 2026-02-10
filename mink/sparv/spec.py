"""Sparv resource spec registration."""

from mink.core.resource import ResourceType
from mink.core.resource_specs import ResourceSpec, register_spec
from mink.core.status import ProcessName
from mink.sparv.config import sparv_settings
from mink.sparv.jobs import SparvJob
from mink.sparv.storage import storage

register_spec(
    ResourceType.corpus,
    ResourceSpec(
        storage=storage,
        job_cls=SparvJob,
        allowed_extensions=tuple(sparv_settings.SPARV_IMPORTER_MODULES.keys()),
        max_files=-1,
        config_filename=sparv_settings.SPARV_CORPUS_CONFIG,
        process_names=tuple(p.name for p in ProcessName),
    ),
)
