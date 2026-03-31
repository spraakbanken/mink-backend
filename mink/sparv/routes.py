
"""General Sparv routes (not directly related to resources)."""

from fastapi import APIRouter, Query, status
from fastapi.responses import JSONResponse

from mink.core import exceptions, models, return_codes, utils
from mink.sparv import models as sparv_models
from mink.sparv.jobs import SparvDefaultJob

router = APIRouter(tags=["Documentation"])


@router.get(
    "/sparv-schema",
    deprecated=True,
    name="sparv-schema-deprecated",
)
@router.get(
    "/corpus/sparv/get-schema",
    response_model=sparv_models.SchemaResponse,
    responses={
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": models.ErrorResponse500,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.FAILED_LISTING_CONTENT.message,
                        "return_code": return_codes.FAILED_LISTING_CONTENT.code,
                        "info": "Failed getting Sparv config schema",
                    },
                }
            },
        }
    },
)
async def sparv_schema(update_cache: bool = sparv_models.update_cache_param) -> JSONResponse:
    """Get the JSON schema for the Sparv config format.

    ### Example

    ```bash
    curl -X GET '{{host}}/corpus/sparv/get-schema'
    ```
    """
    try:
        job = SparvDefaultJob()
        schema = job.get_sparv_schema(update_cache=update_cache)
    except Exception as e:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.FAILED_LISTING_CONTENT, info=f"Failed getting Sparv config schema: {e}"
        ) from e
    return utils.response(
        return_code=return_codes.LISTING_CONTENT, info="Returning Sparv config schema", sparv_schema=schema
    )


@router.get(
    "/sparv-languages",
    deprecated=True,
    name="sparv-languages-deprecated",
)
@router.get(
    "/corpus/sparv/list-languages",
    response_model=sparv_models.LanguagesResponse,
    responses={
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": models.ErrorResponse500,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.FAILED_LISTING_CONTENT.message,
                        "return_code": return_codes.FAILED_LISTING_CONTENT.code,
                        "info": "Failed listing languages",
                    },
                }
            },
        }
    },
)
async def sparv_languages(update_cache: bool = sparv_models.update_cache_param) -> JSONResponse:
    """List languages available in Sparv along with their language codes (ISO 639-3).

    ### Example

    ```bash
    curl -X GET '{{host}}/corpus/sparv/list-languages'
    ```
    """
    try:
        job = SparvDefaultJob()
        languages = job.list_languages(update_cache=update_cache)
    except Exception as e:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.FAILED_LISTING_CONTENT,
            info=f"Failed listing languages: {e}",
        ) from e
    return utils.response(
        return_code=return_codes.LISTING_CONTENT, info="Listing languages available in Sparv", languages=languages
    )


@router.get(
    "/sparv-exports",
    deprecated=True,
    name="sparv-exports-deprecated",
)
@router.get(
    "/corpus/sparv/list-exports",
    response_model=sparv_models.ExportsResponse,
    responses={
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": models.ErrorResponse422},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": models.ErrorResponse500,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.FAILED_LISTING_CONTENT.message,
                        "return_code": return_codes.FAILED_LISTING_CONTENT.code,
                        "info": "Failed listing exports",
                    }
                }
            },
        },
    },
)
async def sparv_exports(
    language: str = Query("swe", description="languages for which to list exports"),
    update_cache: bool = sparv_models.update_cache_param,
) -> JSONResponse:
    """List available Sparv export formats for the chosen language (default: 'swe').

    The language is specified with the `language` as ISO 639-3 code. See available languages by calling
    <{{host}}/corpus/sparv/list-languages>.

    ### Example

    ```bash
    curl -X GET '{{host}}/corpus/sparv/list-exports?language=swe'
    ```
    """
    try:
        job = SparvDefaultJob(language=language)
        exports = job.list_exports(update_cache=update_cache)
    except Exception as e:
        raise exceptions.MinkHTTPException(
            return_code=return_codes.FAILED_LISTING_CONTENT, info=f"Failed listing exports: {e}"
        ) from e
    return utils.response(
        return_code=return_codes.LISTING_CONTENT,
        info="Listing exports available in Sparv",
        language=language,
        exports=exports,
    )
