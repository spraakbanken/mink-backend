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
