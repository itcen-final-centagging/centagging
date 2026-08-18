"""장면 이미지 태깅(유사 SKU 추천) API입니다."""

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query

from app.api.examples import (
    SCENE_IMAGE_NOT_FOUND_RESPONSE,
    SCENE_OBJECT_UPDATE_REQUEST_EXAMPLE,
    SCENE_OBJECT_UPDATE_SUCCESS_RESPONSE,
    SKU_MATCHING_REQUEST_EXAMPLE,
    SKU_RECOMMENDATION_SUCCESS_RESPONSE,
    TAGGING_RESULT_SAVE_SUCCESS_RESPONSE,
    TAGGING_RESULT_UNPROCESSABLE_RESPONSE,
    TAGGING_TARGET_NOT_FOUND_RESPONSE,
    VALIDATION_ERROR_RESPONSE,
)
from app.core import database
from app.dependencies import get_sku_match_service, get_tagging_service
from app.repositories import scene_image_repository
from app.repositories.scene_image_repository import SceneImageNotFoundError
from app.schemas import common as common_schema
from app.schemas.tagging import (
    DetectionResult,
    SceneObjectUpdateRequest,
    SceneObjectUpdateResult,
    SkuMatchingRequest,
    SkuMatchingResult,
)
from app.services import sku_match_service as sku_match
from app.services.tagging_service import TaggingService

router = APIRouter(prefix="/tagging", tags=["tagging"])


@router.post(
    "/scenes/{scene_id}",
    response_model=common_schema.SuccessResponse[SceneObjectUpdateResult],
    summary="편집한 탐지 객체 저장",
    description=(
        "사용자가 화면에서 수정한 바운딩 박스와 카테고리를 "
        "유사 SKU 추천 이전에 연출 이미지에 저장합니다. "
        "bbox_coord는 0~1000으로 정규화된 좌표이며 "
        "xmin < xmax, ymin < ymax를 만족해야 합니다."
    ),
    response_description=(
        "공통 성공 응답으로 저장된 객체 개수와 처리 상태를 반환합니다."
    ),
    responses={
        200: SCENE_OBJECT_UPDATE_SUCCESS_RESPONSE,
        404: SCENE_IMAGE_NOT_FOUND_RESPONSE,
        422: VALIDATION_ERROR_RESPONSE,
    },
)
async def update_scene_objects(
    scene_id: int = Path(
        description="편집 결과를 저장할 연출 이미지 ID입니다.",
        openapi_examples={"scene": {"summary": "연출 이미지", "value": 101}},
    ),
    update_request: SceneObjectUpdateRequest = Body(
        openapi_examples={
            "edited_objects": {
                "summary": "소파와 테이블 2건을 편집한 경우",
                "value": SCENE_OBJECT_UPDATE_REQUEST_EXAMPLE,
            }
        },
    ),
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


@router.get(
    "/scenes/{scene_id}",
    response_model=common_schema.SuccessResponse[DetectionResult],
    summary="탐지 객체별 유사 SKU 추천 조회",
    description=(
        "연출 이미지에서 탐지된 객체마다 임베딩 유사도가 높은 SKU 후보와 "
        "XAI 판정 근거(구조·색상·디테일·맥락 루브릭)를 함께 조회합니다. "
        "object_idxs는 기존 클라이언트 호환을 위해 유지하고 있으며, "
        "현재는 장면의 모든 객체를 반환합니다."
    ),
    response_description=(
        "공통 성공 응답으로 탐지 객체별 SKU 후보 목록을 반환합니다."
    ),
    responses={
        200: SKU_RECOMMENDATION_SUCCESS_RESPONSE,
        404: SCENE_IMAGE_NOT_FOUND_RESPONSE,
        422: VALIDATION_ERROR_RESPONSE,
    },
)
async def get_recommendation_sku(
    scene_id: int = Path(
        description="추천을 조회할 연출 이미지 ID입니다.",
        openapi_examples={"scene": {"summary": "연출 이미지", "value": 101}},
    ),
    object_idxs: list[int] | None = Query(
        default=None,
        description=(
            "조회할 탐지 객체 인덱스 목록입니다. "
            "생략하면 장면의 모든 객체를 조회합니다."
        ),
        openapi_examples={
            "all": {"summary": "전체 객체 조회", "value": None},
            "selected": {"summary": "0번, 1번 객체만 선택", "value": [0, 1]},
        },
    ),
    taggin_service: TaggingService = Depends(get_tagging_service),
) -> common_schema.SuccessResponse[DetectionResult]:
    """장면 이미지에서 탐지된 객체들의 유사 SKU를 추천합니다.

    Args:
        scene_id: 조회할 장면 이미지 ID입니다.
        object_idxs: 조회할 탐지 객체의 인덱스 목록입니다.
        taggin_service: 유사 SKU 조회 및 XAI 근거 산출 서비스입니다.

    Returns:
        탐지된 객체 별 유사 SKU 후보 정보 목록을 반환합니다.

    Raises:
        HTTPException: scene_id에 해당하는 장면 이미지가 없는 경우
            404를 반환합니다.
    """
    # NOTE: 기존 클라이언트의 선택 인덱스 쿼리 호환성은 유지합니다.
    # 추천 서비스가 현재 장면의 모든 객체를 처리하므로 아직 필터링하지 않습니다.
    _ = object_idxs
    try:
        result = await taggin_service.get_sku_candidates(
            scene_id,
            object_idxs=object_idxs,
        )
    except SceneImageNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return common_schema.success_response(result)


@router.post(
    "/scenes/{scene_id}/results",
    response_model=common_schema.SuccessResponse[SkuMatchingResult],
    summary="선택한 SKU를 태깅 결과로 확정 저장",
    description=(
        "탐지 객체별로 사용자가 최종 선택한 SKU를 태깅 결과로 확정합니다. "
        "저장과 동시에 승인 대기(PENDING) 상태의 검수 건이 생성되며, "
        "같은 객체를 다시 확정하면 기존 결과를 갱신합니다."
    ),
    response_description=(
        "공통 성공 응답으로 확정 상태와 저장된 결과 ID 목록을 반환합니다."
    ),
    responses={
        200: TAGGING_RESULT_SAVE_SUCCESS_RESPONSE,
        404: TAGGING_TARGET_NOT_FOUND_RESPONSE,
        422: TAGGING_RESULT_UNPROCESSABLE_RESPONSE,
    },
)
async def save_tagging_results(
    scene_id: int = Path(
        description="확정할 연출 이미지 ID입니다.",
        openapi_examples={"scene": {"summary": "연출 이미지", "value": 101}},
    ),
    match_request: SkuMatchingRequest = Body(
        openapi_examples={
            "confirm_sofa": {
                "summary": "소파 객체의 1순위 후보를 확정하는 경우",
                "value": SKU_MATCHING_REQUEST_EXAMPLE,
            }
        },
    ),
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
        result_ids = await match_service.save_tagging_results(
            scene_id, match_request.tagging_results
        )
    except (
        sku_match.SceneImageNotFoundError,
        sku_match.MatchingTargetNotFoundError,
    ) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        sku_match.DuplicateObjectIdxError,
        sku_match.ObjectIdxOutOfRangeError,
    ) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    return common_schema.success_response(
        SkuMatchingResult(
            processing_status="CONFIRMED",
            result_ids=result_ids,
        )
    )
