"""장면 이미지 태깅(유사 SKU 추천) API입니다."""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_similar_sku_service, get_sku_match_service
from app.schemas.tagging import (
    DetectionResponse,
    SkuMatchingRequest,
    SkuMatchingResponse,
    SkuMatchingResult,
)
from app.services import sku_match_service as sku_match
from app.services.similar_sku_service import (
    SceneImageNotFoundError,
    SimilarSkuService,
)

router = APIRouter(prefix="/tagging", tags=["tagging"])


@router.get("/scenes/{scene_id}")
async def get_recommendation_sku(
    scene_id: int,
    object_indexes: list[int] = Query(default=[]),
    similar_sku_service: SimilarSkuService = Depends(get_similar_sku_service),
) -> DetectionResponse:
    """장면 이미지에서 탐지된 객체들의 유사 SKU를 추천합니다.

    Args:
        scene_id: 조회할 장면 이미지 ID입니다.
        object_indexes: 탐지된 객체 인덱스입니다.
        similar_sku_service: 유사 SKU 조회 서비스입니다.

    Returns:
        탐지된 객체 별 유사 SKU 후보 정보 목록을 반환합니다.

    Raises:
        HTTPException: scene_id에 해당하는 장면 이미지가 없는 경우
            404를 반환합니다.
    """
    try:
        result = await similar_sku_service.orchestrate_similar_skus(
            scene_id, object_indexes
        )
    except SceneImageNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return DetectionResponse(status="success", data=result)


@router.put("/scenes/{scene_id}")
async def confirm_scene_matching(
    scene_id: int,
    match_request: SkuMatchingRequest,
    match_service: sku_match.SkuMatchService = Depends(get_sku_match_service),
) -> SkuMatchingResponse:
    """탐지 객체별로 선택한 SKU를 최종 확정해 저장합니다.

    Args:
        scene_id: 확정할 장면 이미지 ID입니다.
        match_request: 확정할 객체-SKU 매핑 목록입니다.
        match_service: SKU 확정 저장 서비스입니다.

    Returns:
        저장된 tagging_result의 result_id 목록입니다.

    Raises:
        HTTPException: 장면 이미지가 없으면 404, 요청 값이 장면·카탈로그와
            맞지 않으면 422를 반환합니다.
    """
    try:
        result_ids = await match_service.confirm_matching(
            scene_id, match_request.matching
        )
    except sku_match.SceneImageNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        sku_match.DuplicateObjectIndexError,
        sku_match.ObjectIndexOutOfRangeError,
        sku_match.MatchingTargetNotFoundError,
    ) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    return SkuMatchingResponse(
        status="success",
        data=SkuMatchingResult(
            processing_status="CONFIRMED",
            result_ids=result_ids,
        ),
    )
