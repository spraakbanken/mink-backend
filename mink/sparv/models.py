"""Response data models for the sparv module."""

from typing import ClassVar

from pydantic import BaseModel, Field

from mink.core import models


class CreateCorpusResponse(models.BaseResponse):
    """Model for the /create-corpus response."""
    resource_id: str = Field(default="", description="The ID of the created resource")
    model_config: ClassVar[dict] = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "success",
                    "message": "Corpus 'mink-dxh6e6wtff' created successfully",
                    "return_code": "created_corpus",
                    "resource_id": "mink-dxh6e6wtff",
                }
            ]
        }
    }


class ListCorporaResponse(models.BaseResponse):
    """Model for responses where corpora as listed."""
    corpora: list[str] = Field(default=[], description="List of resource IDs")
    model_config: ClassVar[dict] = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "success",
                    "message": "Listing corpora",
                    "return_code": "listing_corpora",
                    "corpora": ["mink-dxh6e6wtff", "mink-j86tfreaf9", "mink-3qbh7tra6g"]
                }
            ]
        }
    }


class CheckChangesResponse(models.BaseResponse):
    """Model for the /check-changes response."""
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
                    "message": "Your input for the corpus 'mink-dxh6e6wtff' has changed since the last run",
                    "return_code": "input_changed",
                    "input_changed": True,
                    "config_changed": False,
                    "sources_changed": True,
                    "sources_deleted": False,
                    "last_run_started": "2021-11-19T14:16:10+00:00",
                },
            ]
        }
    }


class LanguagesResponse(models.BaseResponse):
    """Model for the /languages response."""
    languages: list[str] = Field(default=[], description="List of supported languages (language names and ISO codes)")
    model_config: ClassVar[dict] = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "success",
                    "message": "Listing languages available in Sparv",
                    "return_code": "listing_languages",
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
    """Model for the /exports response."""
    exports: list[str] = Field(default=[], description="List of available export formats")
    language: str = Field(default="swe", description="ISO code of the language chosen for the export listing")
    model_config: ClassVar[dict] = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "success",
                    "message": "Listing exports available in Sparv",
                    "return_code": "listing_sparv_exports",
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


class ResourceModel(BaseModel):
    """Model for the resource object."""
    resource_id: str = Field(default="", alias="id", description="Mink resource ID")
    public_id: str = Field(default="", description="Public resource ID")
    name: dict[str, str] = Field(
        default={},
        description="Name of the resource in different languages",
    )
    resource_type: str = Field(
        default="", alias="type", description="Type of the resource (e.g., 'corpus', 'metadata')"
    )
    source_files: list[models.FileModel] = Field(
        default=[],
        description="List of source files associated with the resource",
    )

    model_config: ClassVar[dict] = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "mink-dxh6e6wtff",
                    "public_id": "mink-dxh6e6wtff",
                    "name": {"swe": "Min testkorpus", "eng": ""},
                    "type": "corpus",
                    "source_files": models.FileModel.model_config["json_schema_extra"]["examples"],
                }
            ]
        }
    }


class ResourceStatusModel(BaseModel):
    """Model for the status of a resource."""

    message: str = Field(default="", description="Message describing the status of the resource")
    resource: ResourceModel = Field(
        default=ResourceModel(),
        description="Resource object containing information about the corpus",
    )
    owner: models.UserModel = Field(
        default=models.UserModel(), description="User object containing information about the resource owner"
    )
    job: models.JobModel = Field(
        default=models.JobModel(),
        description="Job object containing information about the job status",
    )

    model_config: ClassVar[dict] = {
        "json_schema_extra": {
            "examples": [
                    {
                "message": "Job has been queued",
                "resource": ResourceModel.model_config["json_schema_extra"]["examples"][0],
                "owner": models.UserModel.model_config["json_schema_extra"]["examples"][0],
                "job": models.JobModel.model_config["json_schema_extra"]["examples"][0],
            }
            ]
        }
    }


class StatusResponse(models.BaseResponse, ResourceStatusModel):
    """Model for Sparv job status responses."""

    model_config: ClassVar[dict] = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "success",
                    "message": "Job has been queued",
                    "return_code": "job_queued",
                    "resource": ResourceModel.model_config["json_schema_extra"]["examples"][0],
                    "job": models.JobModel.model_config["json_schema_extra"]["examples"],
                }
            ]
        }
    }


class StatusesResponse(models.BaseResponse):
    """Model for multiple Sparv job statuses responses."""
    resources: list[ResourceStatusModel] = Field(
        default=[], description="List of resource objects containing information about the corpus"
    )

    model_config: ClassVar[dict] = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "success",
                    "message": "Listing resource infos",
                    "return_code": "listing_jobs",
                    "resources": [
                        {
                            "message": "Job was completed successfully",
                            "return_code": "job_completed",
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
                            "job": models.JobModel.model_config["json_schema_extra"]["examples"][0],
                        },
                        {
                            "message": "Job was completed successfully",
                            "return_code": "job_completed",
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
                            "job": models.JobModel.model_config["json_schema_extra"]["examples"][1],
                        }
                    ]
                }
            ]
        }
    }
