"""HTTP endpoints for the integrated furniture tagging workflow."""

import functools

import fastapi

from app.core import config
from app.models import tagging
from app.services import tagging_service

router = fastapi.APIRouter(prefix="/api/v1/taggings", tags=["taggings"])

MAX_IMAGE_SIZE = 10 * 1024 * 1024


@functools.lru_cache(maxsize=1)
def get_tagging_service() -> tagging_service.TaggingService:
    """Build the process-wide workflow service and initialize persistence once."""
    service = tagging_service.TaggingService(config.get_settings())
    service.initialize()
    return service


@router.post("/analyze", response_model=tagging.AnalyzeTaggingResponse)
async def analyze_tagging(
    image: fastapi.UploadFile,
    target_description: str | None = fastapi.Form(default=None),
) -> tagging.AnalyzeTaggingResponse:
    """Analyze an uploaded lifestyle image through the complete tag pipeline."""
    if image.content_type not in {"image/jpeg", "image/png"}:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only JPEG and PNG images are supported.",
        )

    image_bytes = await image.read()
    if len(image_bytes) > MAX_IMAGE_SIZE:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="The image must be 10MB or smaller.",
        )

    try:
        return get_tagging_service().analyze(
            image_bytes,
            image.filename or "untitled-image",
            target_description,
        )
    except tagging_service.TaggingInputError as error:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error


@router.get("/catalog", response_model=list[tagging.SkuCandidateResponse])
async def search_catalog(
    query: str = fastapi.Query(min_length=1),
) -> list[tagging.SkuCandidateResponse]:
    """Search catalog candidates for a manual SKU selection."""
    return get_tagging_service().search_catalog(query)


@router.get(
    "/catalog/{sku}/image",
    response_class=fastapi.responses.FileResponse,
)
async def get_catalog_image(sku: str) -> fastapi.responses.FileResponse:
    """Serve the packaged representative image of a known catalog SKU."""
    image_path = get_tagging_service().get_catalog_image_path(sku)
    if image_path is None:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_404_NOT_FOUND,
            detail="The catalog image does not exist.",
        )
    return fastapi.responses.FileResponse(image_path, media_type="image/jpeg")


@router.post("/reviews", response_model=tagging.TaggingHistoryResponse)
async def save_review(
    request: tagging.SaveReviewRequest,
) -> tagging.TaggingHistoryResponse:
    """Persist a human-validated tag decision to the HITL queue."""
    try:
        return get_tagging_service().save_review(request)
    except tagging_service.TaggingInputError as error:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error


@router.get("/history", response_model=list[tagging.TaggingHistoryResponse])
async def get_history() -> list[tagging.TaggingHistoryResponse]:
    """Return most-recent-first persisted HITL reviews."""
    return get_tagging_service().get_history()
