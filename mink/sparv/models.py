"""Response data models for the sparv module."""

from typing import ClassVar

from fastapi import Query
from pydantic import Field

from mink.core import models, return_codes


class ListResourcesResponse(models.BaseResponse):
    """Model for responses where corpus resources are listed."""
    resources: list[str] = Field(default=[], description="List of resource IDs")
    model_config: ClassVar[dict] = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "success",
                    "message": return_codes.LISTING_CONTENT.message,
                    "return_code": return_codes.LISTING_CONTENT.code,
                    "info": "Listing available corpus resources",
                    "resources": ["mink-dxh6e6wtff", "mink-j86tfreaf9", "mink-3qbh7tra6g"]
                }
            ]
        }
    }


class CheckInputResponse(models.BaseResponse):
    """Model for the /corpus/job/check-input response."""
    input_changed: bool = Field(
        default=False, description="Indicates if the input for the corpus has changed since the last run"
    )
    config_changed: bool = Field(
        default=False, description="Indicates if the configuration has changed since the last run"
    )
    sources_changed: bool = Field(
        default=False, description="Indicates if existing sources have changed since the last run"
    )
    sources_deleted: bool = Field(
        default=False, description="Indicates if sources have been deleted since the last run"
    )
    last_run_started: str | None = Field(default=None, description="Timestamp of when the last run started")

    model_config: ClassVar[dict] = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "success",
                    "message": return_codes.CHECKED_STATUS.message,
                    "return_code": return_codes.CHECKED_STATUS.code,
                    "info": "The input has changed since the last run",
                    "input_changed": True,
                    "config_changed": False,
                    "sources_changed": True,
                    "sources_deleted": False,
                    "last_run_started": "2021-11-19T14:16:10+00:00",
                },
            ]
        }
    }


class SchemaResponse(models.BaseResponse):
    """Model for the /corpus/sparv/get-schema response."""

    sparv_schema: dict = Field(
        default={}, alias="schema", description="The JSON schema for the Sparv configuration format"
    )
    model_config: ClassVar[dict] = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "success",
                    "message": return_codes.LISTING_CONTENT.message,
                    "return_code": return_codes.LISTING_CONTENT.code,
                    "info": "Returning Sparv config schema",
                    "schema": {
                        "type": "object",
                    },
                }
            ]
        }
    }


class LanguagesResponse(models.BaseResponse):
    """Model for the /corpus/sparv/list-languages response."""
    languages: list[str] = Field(default=[], description="List of supported languages (language names and ISO codes)")
    model_config: ClassVar[dict] = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "success",
                    "message": return_codes.LISTING_CONTENT.message,
                    "return_code": return_codes.LISTING_CONTENT.code,
                    "info": "Listing languages available in Sparv",
                    "languages": [

                        {
                            "name": "English",
                            "code": "eng"
                        },
                        {
                            "name": "Finnish",
                            "code": "fin"
                        },
                        {
                            "name": "Swedish",
                            "code": "swe"
                        }
                    ]
                }
            ]
        }
    }


class ExportsResponse(models.BaseResponse):
    """Model for the /corpus/sparv/list-exports response."""
    exports: list[str] = Field(default=[], description="List of available export formats")
    language: str = Field(default="swe", description="ISO code of the language chosen for the export listing")
    model_config: ClassVar[dict] = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "success",
                    "message": return_codes.LISTING_CONTENT.message,
                    "return_code": return_codes.LISTING_CONTENT.code,
                    "info": "Listing exports available in Sparv",
                    "language": "swe",
                    "exports": [
                        {
                            "export": "conll_export:conllu",
                            "description": "CoNLL-U (SBX version) export",
                            "export_files": ["conll_export/{file}.conllu"],
                        },
                        {
                            "export": "csv_export:csv",
                            "description": "CSV export",
                            "export_files": ["csv_export/{file}.csv"],
                        },
                        {
                            "export": "stats_export:freq_list",
                            "description": "Corpus word frequency list",
                            "export_files": ["stats_export.frequency_list/stats_standard-swe.csv"],
                        },
                        {
                            "export": "xml_export:pretty",
                            "description": "XML export with one token element per line",
                            "export_files": ["xml_export.pretty/{file}_export.xml"],
                        },
                        {
                            "export": "xml_export:scrambled",
                            "description": "Scrambled XML export",
                            "export_files": ["xml_export.scrambled/{file}_export.xml"],
                        },
                    ]
                }
            ]
        }
    }


job_model_examples = [
    {
        "status": {
            "sync2sparv": "done",
            "sync2storage": "running",
            "sparv": "waiting",
            "korp": "error",
            "strix": "none",
        },
        "current_process": "sparv",
        "pid": None,
        "sparv_exports": ["csv_export:csv", "stats_export:freq_list", "xml_export:pretty"],
        "current_files": ["dokument1", "dokument2"],
        "install_scrambled": True,
        "installed_korp": True,
        "installed_strix": True,
        "priority": 1,
        "warnings": "",
        "errors": "",
        "sparv_output": "Nothing to be done.",
        "started": "2024-01-02T14:31:26+01:00",
        "ended": "",
        "duration": 10,
        "progress": "0%",
    },
    {
        "status": {
            "sync2sparv": "none",
            "sync2storage": "none",
            "sparv": "done",
            "korp": "aborted",
            "strix": "done",
        },
        "current_process": "sparv",
        "pid": None,
        "sparv_exports": ["xml_export:pretty", "csv_export:csv", "stats_export:sbx_freq_list"],
        "current_files": [],
        "install_scrambled": True,
        "installed_korp": True,
        "installed_strix": True,
        "priority": "",
        "warnings": "",
        "errors": "",
        "sparv_output": "The exported files can be found in the following locations:\n • export"
        "/csv_export/\n • export/stats_export.frequency_list_sbx/\n • export/"
        "xml_export.pretty/",
        "started": "2023-12-11T13:24:09+01:00",
        "ended": "",
        "duration": 20,
        "progress": "100%",
    },
]

job_status_examples = [
    {
        "info": "Job has been queued",
        "resource": models.resource_model_example,
        "owner": models.user_model_example,
        "job": job_model_examples[0],
    }
]

status_response_examples = [
    {
        "status": "success",
        "message": return_codes.CHECKED_STATUS.message,
        "return_code": return_codes.CHECKED_STATUS.code,
        "job_status": "waiting",
        "info": "Job has been queued",
        "resource": models.resource_model_example,
        "job": job_model_examples[0],
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
                "resource": {
                    "id": "mink-ezodmp4wxm",
                    "name": {"swe": "txt-korpus", "eng": "txt-korpus"},
                    "type": "corpus",
                    "source_files": [
                        {
                            "name": "text1.txt",
                            "type": "text/plain",
                            "last_modified": "2023-05-15T10:40:44+02:00",
                            "size": 825,
                            "path": "text1.txt",
                        },
                        {
                            "name": "text2.txt",
                            "type": "text/plain",
                            "last_modified": "2023-05-15T10:40:45+02:00",
                            "size": 1169,
                            "path": "text2.txt",
                        },
                    ],
                },
                "job": job_model_examples[0],
            },
            {
                "job_status": "done",
                "info": "Job was completed successfully",
                "resource": {
                    "id": "mink-dxh6e6wtff",
                    "name": {"swe": "Annes och Martins testkorpus", "eng": ""},
                    "type": "corpus",
                    "source_files": [
                        {
                            "name": "dokument2.xml",
                            "type": "text/xml",
                            "last_modified": "2022-12-22T11:25:25+01:00",
                            "size": 115,
                            "path": "dokument2.xml",
                        },
                        {
                            "name": "dokument3.xml",
                            "type": "text/xml",
                            "last_modified": "2023-06-13T13:26:44+02:00",
                            "size": 41,
                            "path": "dokument3.xml",
                        },
                        {
                            "name": "dokument4.xml",
                            "type": "text/xml",
                            "last_modified": "2023-06-13T13:26:44+02:00",
                            "size": 461,
                            "path": "dokument4.xml",
                        },
                        {
                            "name": "dokument1.xml",
                            "type": "text/xml",
                            "last_modified": "2023-06-13T13:26:49+02:00",
                            "size": 1394,
                            "path": "dokument1.xml",
                        },
                    ],
                },
                "job": job_model_examples[1],
            },
        ],
    }
]


# ------------------------------------------------------------------------------
# Reusable query parameters
# ------------------------------------------------------------------------------
update_cache_param: bool = Query(False, description="If true, force update the cached Sparv data", alias="update-cache")
