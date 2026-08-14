"""Response data models for the sparv module."""

from typing import ClassVar

from pydantic import Field

from mink.core import models, return_codes


class ListResourcesResponse(models.BaseResponse):
    """Model for responses where lexicon resources are listed."""
    resources: list[str] = Field(default=[], description="List of resource IDs")
    model_config: ClassVar[dict] = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "success",
                    "message": return_codes.LISTING_CONTENT.message,
                    "return_code": return_codes.LISTING_CONTENT.code,
                    "info": "Listing lexicons",
                    "resources": ["mink-dxh6e6wtff", "mink-j86tfreaf9", "mink-3qbh7tra6g"]
                }
            ]
        }
    }


lexicon_model_example = {
    "id": "mink-vajfgwcqdw",
    "public_id": "mink-vajfgwcqdw",
    "name": {"swe": "Mitt testlexikon", "eng": "My test lexicon"},
    "custom_config": True,
    "source_files": [
        {
            "name": "test_lexicon_data2.jsonl",
            "type": "unknown",
            "last_modified": "2026-04-22T12:50:37+02:00",
            "size": 62,
            "path": "test_lexicon_data2.jsonl"
        }
    ],
    "sources_deleted": "2026-04-22T12:50:37+02:00",
}


job_model_example = {
    "status": {
        "karp_pipeline": "waiting",
        "karps": "none"
    },
    "current_process": "karp_pipeline",
    "pid": None,
    "installed_karps": False,
    "priority": 1,
    "warnings": "",
    "errors": "",
    "output": (
        "Running mink-vajfgwcqdw\n"
        "Reading source files: /data/sbdata01/mink-dev-data/lexicon/v/"
        "mink-vajfgwcqdw/source/test_lexicon_data2.jsonl\n"
        'Using entry schema: {"baseform":{"type":"text","name":'
        '"baseform","collection":false,"fields":{},"extra":'
        '{"length":4},"categories":[]}}\n'
        "Reading source files: /data/sbdata01/mink-dev-data/lexicon/v/"
        "mink-vajfgwcqdw/source/test_lexicon_data2.jsonl"
    ),
    "queued": "2026-06-02T10:25:14+02:00",
    "started": "",
    "ended": "",
    "duration": 0,
    "progress": "0%"
}


job_status_examples = [
    {
        "info": "Job has been queued",
        "resource": lexicon_model_example,
        "owner": models.user_model_example,
        "job": job_model_example,
    }
]

status_response_examples = [
    {
        "status": "success",
        "message": return_codes.CHECKED_STATUS.message,
        "return_code": return_codes.CHECKED_STATUS.code,
        "job_status": "waiting",
        "info": "Job has been queued",
        "resource": lexicon_model_example,
        "job": job_model_example,
    }
]

statuses_response_examples = [
    {
        "status": "success",
        "message": return_codes.LISTING_CONTENT.message,
        "return_code": return_codes.LISTING_CONTENT.code,
        "info": "Listing resource infos",
        "resources": [
            {
                "job_status": "done",
                "info": "Job was completed successfully",
                "resource": lexicon_model_example,
                "job": job_model_example,
            },
        ],
    }
]
