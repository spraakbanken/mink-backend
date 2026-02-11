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
        info_builder=lambda: {
            "description": sparv_settings.SPARV_RES_INFO,
            "importer_modules": {
                "info": "Sparv importer modules for different file extensions",
                "data": [
                    {"file_extension": k, "importer": v} for k, v in sparv_settings.SPARV_IMPORTER_MODULES.items()
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
