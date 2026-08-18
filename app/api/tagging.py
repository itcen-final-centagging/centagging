"""장면 이미지 태깅(유사 SKU 추천) API입니다."""

from fastapi import APIRouter, Depends, HTTPException

from app.core import database
from app.dependencies import get_sku_match_service
from app.models.ai_job import AiJobType
from app.repositories import ai_job_repository, scene_image_repository
from app.repositories.scene_image_repository import SceneImageNotFoundError
from app.schemas import ai_job as ai_job_schema
from app.schemas import common as common_schema
from app.schemas.tagging import (
    SceneObjectUpdateRequest,
    SceneObjectUpdateResult,
    SkuMatchingRequest,
    SkuMatchingResult,
)
from app.services import sku_match_service as sku_match

router = APIRouter(prefix="/tagging", tags=["tagging"])

_DETECTED_SCENE_STATUS = "detected"
_RECOMMENDATION_NOT_READY_MESSAGE = (
    "가구 탐지가 완료된 이미지에 대해서만 SKU 추천을 요청할 수 있습니다."
)


@router.post("/scenes/{scene_id}")
async def update_scene_objects(
    scene_id: int,
    update_request: SceneObjectUpdateRequest,
    database_session: database.sqlalchemy_async.AsyncSession = Depends(
        database.get_database_session
    ),
) -> common_schema.SuccessResponse[SceneObjectUpdateResult]:
    """사용자가 편집한 바운딩 박스와 카테고리를 추천 전에 저장합니다."""
    try:
        await scene_image_repository.update_scene_object_metadata(
            database_session,
            scene_id,
            [object.model_dump() for object in update_request.objects],
        )
    except SceneImageNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return common_schema.success_response(
        SceneObjectUpdateResult(object_count=len(update_request.objects))
    )


@router.post(
    "/scenes/{scene_id}/recommendations",
    response_model=common_schema.SuccessResponse[
        ai_job_schema.AiJobAcceptedResponse
    ],
    status_code=202,
)
async def enqueue_sku_recommendation(
    scene_id: int,
    database_session: database.sqlalchemy_async.AsyncSession = Depends(
        database.get_database_session
    ),
) -> common_schema.SuccessResponse[ai_job_schema.AiJobAcceptedResponse]:
    """탐지 완료된 장면의 SKU 추천 작업을 비동기로 접수합니다."""
    try:
        scene = await scene_image_repository.get_scene_image(
            database_session,
            scene_id,
        )
    except SceneImageNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail="연출 이미지를 찾을 수 없습니다.",
        ) from error

    if scene.analysis_status != _DETECTED_SCENE_STATUS:
        raise HTTPException(
            status_code=409,
            detail=_RECOMMENDATION_NOT_READY_MESSAGE,
        )

    try:
        job = await ai_job_repository.create_job(
            database_session,
            scene_id,
            AiJobType.RECOMMEND_SKU,
        )
    except ai_job_repository.ActiveAiJobExistsError as error:
        raise HTTPException(
            status_code=409,
            detail="이미 진행 중인 SKU 추천 작업이 있습니다.",
        ) from error

    return common_schema.success_response(
        ai_job_schema.AiJobAcceptedResponse(
            scene_image_id=scene_id,
            job_id=job.job_id,
        )
    )


@router.put("/scenes/{scene_id}")
async def confirm_scene_matching(
    scene_id: int,
    match_request: SkuMatchingRequest,
    match_service: sku_match.SkuMatchService = Depends(get_sku_match_service),
) -> common_schema.SuccessResponse[SkuMatchingResult]:
    """탐지 객체별로 선택한 SKU를 최종 확정해 저장합니다.

    Args:
        scene_id: 확정할 장면 이미지 ID입니다.
        match_request: 확정할 객체-SKU 매핑 목록입니다.
        match_service: SKU 확정 저장 서비스입니다.

    Returns:
        저장된 tagging_result의 result_id 목록입니다.

    Raises:
        HTTPException: 장면 이미지나 SKU가 없으면 404, 객체 인덱스가
            중복되거나 범위를 벗어나면 422를 반환합니다.
    """
    try:
        result_ids = await match_service.confirm_matching(
            scene_id, match_request.matching
        )
    except (
        sku_match.SceneImageNotFoundError,
        sku_match.MatchingTargetNotFoundError,
    ) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        sku_match.DuplicateObjectIndexError,
        sku_match.ObjectIndexOutOfRangeError,
    ) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    return common_schema.success_response(
        SkuMatchingResult(
            processing_status="CONFIRMED",
            result_ids=result_ids,
        )
    )
