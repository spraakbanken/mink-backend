"""General Sparv routes (not directly related to resources)."""

from fastapi import APIRouter, Query, status
from fastapi.responses import JSONResponse

from mink.core import exceptions, models, return_codes, utils
from mink.sparv import cache
from mink.sparv import models as sparv_models
from mink.sparv import utils as sparv_utils
from mink.sparv.jobs import SparvDefaultJob

router = APIRouter(tags=["Documentation"], prefix="/corpus")


@router.get(
    "/sparv/get-schema",
    operation_id="get-sparv-schema",
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
    "/sparv/list-languages",
    operation_id="list-sparv-languages",
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
    "/sparv/list-exports",
    operation_id="list-sparv-exports",
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


@router.get(
    "/sparv/list-analyses",
    operation_id="list-sparv-analyses",
    response_model=sparv_models.AnalysesResponse,
    responses={
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": models.ErrorResponse500,
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": return_codes.FAILED_LISTING_CONTENT.message,
                        "return_code": return_codes.FAILED_LISTING_CONTENT.code,
                        "info": "Failed getting Sparv analyses",
                    },
                }
            },
        }
    },
)
async def sparv_analyses(
    language: str | None = Query(None, description="ISO 639-3 language code to filter analyses"),
    variety: str | None = Query(None, description="Language variety to filter analyses"),
    update_cache: bool = sparv_models.update_cache_param,
) -> JSONResponse:
    """Get the Sparv analyses available in Mink, optionally filtered by language and variety.

    Analyses without a language, or with the `mul` or `zxx` language code, are included for every language.
    Analyses with a language variety are included only when that variety is requested.

    ### Example

    ```bash
    curl -X GET '{{host}}/corpus/sparv/list-analyses'
    ```
    """
    analyses = []
    if not update_cache:
        # Get from cache if available
        cached_analyses = cache.get_sparv_analyses()
        if cached_analyses:
            analyses = cached_analyses
    if update_cache or not analyses:
        # Load from file and update cache
        try:
            analyses = sparv_utils.load_available_analyses()
            cache.set_sparv_analyses(analyses)

        except Exception as e:
            raise exceptions.MinkHTTPException(
                return_code=return_codes.FAILED_LISTING_CONTENT, info=f"Failed getting Sparv analyses: {e}"
            ) from e

    analyses = sparv_utils.filter_available_analyses(analyses, language, variety)
    return utils.response(
        return_code=return_codes.LISTING_CONTENT,
        info="Listing available Sparv analyses",
        language=language,
        variety=variety,
        analyses=analyses,
    )
