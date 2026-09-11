"""Response data models for the sparv module."""

from typing import Any, ClassVar

from fastapi import Query
from pydantic import ConfigDict, Field

from mink.core import models, return_codes


class ListResourcesResponse(models.BaseResponse):
    """Model for responses where corpus resources are listed."""

    resources: list[str] = Field(default=[], description="List of resource IDs")
    model_config: ClassVar[ConfigDict] = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "success",
                    "message": return_codes.LISTING_CONTENT.message,
                    "return_code": return_codes.LISTING_CONTENT.code,
                    "info": "Listing available corpus resources",
                    "resources": ["mink-dxh6e6wtff", "mink-j86tfreaf9", "mink-3qbh7tra6g"],
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

    model_config: ClassVar[ConfigDict] = {
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
    model_config: ClassVar[ConfigDict] = {
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

    languages: list[str] = Field(
        default=[], description="List of supported languages (language names, ISO codes and varieties if applicable)"
    )
    model_config: ClassVar[ConfigDict] = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "success",
                    "message": return_codes.LISTING_CONTENT.message,
                    "return_code": return_codes.LISTING_CONTENT.code,
                    "info": "Listing languages available in Sparv",
                    "languages": [
                        {"name": "English", "code": "eng"},
                        {"name": "Finnish", "code": "fin"},
                        {"name": "Swedish", "code": "swe"},
                        {"name": "Swedish (1800)", "code": "swe", "variety": "1800"},
                        {"name": "Swedish (fsv)", "code": "swe", "variety": "fsv"},
                    ],
                }
            ]
        }
    }


class ExportsResponse(models.BaseResponse):
    """Model for the /corpus/sparv/list-exports response."""

    exports: list[str] = Field(default=[], description="List of available export formats")
    language: str = Field(default="swe", description="ISO code of the language chosen for the export listing")
    model_config: ClassVar[ConfigDict] = {
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
                    ],
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
                    "public_id": "mink-ezodmp4wxm",
                    "name": {"swe": "txt-korpus", "eng": "txt-korpus"},
                    "type": "corpus",
                    "custom_config": False,
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
                "resource": models.resource_model_example,
                "job": job_model_examples[1],
            },
        ],
    }
]


class AnalysesResponse(models.BaseResponse):
    """Model for the /corpus/sparv/list-analyses response."""

    language: str | None = Field(default=None, description="Language used to filter the analyses")
    variety: str | None = Field(default=None, description="Language variety used to filter the analyses")
    analyses: list[dict[str, Any]] = Field(default=[], description="List of available Sparv analyses")
    model_config: ClassVar[ConfigDict] = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "success",
                    "message": return_codes.LISTING_CONTENT.message,
                    "return_code": return_codes.LISTING_CONTENT.code,
                    "info": "Listing available Sparv analyses",
                    "analyses": [
                        {
                            "id": "sbx-swe-dependency-stanza-stanzasynt",
                            "name": {"swe": "Dependensparsning med Stanza", "eng": "Dependency parsing with Stanza"},
                            "annotations": [
                                "<token>:stanza.dephead_ref as dephead",
                                "<token>:stanza.deprel",
                                "<token>:stanza.ref",
                            ],
                            "task": {"eng": "dependency parsing", "swe": "dependensparsning"},
                            "analysis_unit": {"eng": "token", "swe": "token"},
                            "languages": [{"code": "swe", "name": {"swe": "svenska", "eng": "Swedish"}}],
                        },
                        {
                            "id": "sbx-swe-msd-hunpos-suc3_1800",
                            "name": {
                                "swe": "Morfosyntaktisk SUC-taggning med Hunpos för 1800-talssvenska",
                                "eng": "Tagging of morphological features (SUC) by Hunpos for Swedish from the 1800s",
                            },
                            "annotations": ["<token>:hunpos.msd"],
                            "task": {"eng": "morphosyntactic tagging", "swe": "morfosyntaktisk taggning"},
                            "analysis_unit": {"eng": "token", "swe": "token"},
                            "languages": [{"code": "swe", "name": {"swe": "svenska", "eng": "Swedish"}}],
                            "language_varieties": ["1800"],
                        },
                    ],
                }
            ]
        }
    }


class InputResponse(models.BaseResponse):
    """Model for the /demo/corpus/input/get/{resource_id} response."""

    input_text: str = Field(default="", description="The input text of the corpus resource")
    config: str = Field(default="", description="The Sparv configuration of the corpus resource")
    model_config: ClassVar[ConfigDict] = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "success",
                    "message": "Retrieved content successfully",
                    "return_code": "retrieved_content",
                    "input_text": "Detta är en text.",
                    "config": (
                        "export:\n  annotations:\n  - <sentence>\n  - <token>:saldo.baseform2 as baseform\n  - "
                        "<token>:saldo.lemgram\n  - <token>:wsd.sense\n  - <token>:stanza.pos\n  - <token>:stanza.msd\n"
                        "import:\n  importer: text_import:parse\nmetadata:\n  id: mink-demo-220fee71\n"
                    ),
                }
            ]
        }
    }


class OutputResponse(models.BaseResponse):
    """Model for the /demo/corpus/export/get/{resource_id} response."""

    output: str = Field(default="", description="The annotated output from the processed corpus")
    model_config: ClassVar[ConfigDict] = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "success",
                    "message": "Retrieved content successfully",
                    "return_code": "retrieved_content",
                    "output": (
                        "<?xml version='1.0' encoding='utf-8'?>\n"
                        "<sentence>\n"
                        "  <text>\n"
                        '    <token baseform="|denna|" lemgram="|denna..pn.1|" msd="PN.NEU.SIN.DEF.SUB+OBJ" '
                        'pos="PN" sense="|denna..1:-1.000|">Detta</token>\n'
                        '    <token baseform="|vara|" lemgram="|vara..vb.1|" msd="VB.PRS.AKT" pos="VB" '
                        'sense="|vara..1:-1.000|">är</token>\n'
                        '    <token baseform="|en|" lemgram="|en..al.1|" msd="DT.UTR.SIN.IND" pos="DT" '
                        'sense="|den..1:-1.000|en..2:-1.000|">en</token>\n'
                        '    <token baseform="|text|" lemgram="|text..nn.1|" msd="NN.UTR.SIN.IND.NOM" '
                        'pos="NN" sense="|text..1:-1.000|">text</token>\n'
                        '    <token baseform="|" lemgram="|" msd="MAD" pos="MAD" sense="|">.</token>\n'
                        "  </text>\n"
                        "</sentence>\n"
                    ),
                }
            ]
        }
    }


class RemovedResourcesResponse(models.BaseResponse):
    """Model for the /demo/corpus/remove-expired response."""

    removed_resources: list[str] = Field(default=[], description="List of removed resource IDs")
    failed_removals: list[str] = Field(default=[], description="List of resource IDs that failed to be removed")
    model_config: ClassVar[ConfigDict] = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "success",
                    "message": return_codes.REMOVED_RESOURCES.message,
                    "return_code": return_codes.REMOVED_RESOURCES.code,
                    "removed_resources": ["mink-demo-871eabc3", "mink-demo-845eabgh"],
                    "failed_removals": ["mink-demo-abc12345"],
                }
            ]
        }
    }


# ------------------------------------------------------------------------------
# Reusable query parameters
# ------------------------------------------------------------------------------
update_cache_param: bool = Query(False, description="If true, force update the cached Sparv data", alias="update-cache")
