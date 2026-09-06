"""장면 이미지 태깅(유사 SKU 추천) API입니다."""

from fastapi import APIRouter, Body, Depends, HTTPException, Path

from app.api.examples import (
    ACTIVE_AI_JOB_EXISTS_RESPONSE,
    AI_JOB_NOT_READY_RESPONSE,
    SCENE_IMAGE_NOT_FOUND_RESPONSE,
    SCENE_OBJECT_UPDATE_REQUEST_EXAMPLE,
    SEARCH_CANDIDATE_MOOD_REQUEST_EXAMPLE,
    SEARCH_CANDIDATE_MOOD_SUCCESS_RESPONSE,
    SKU_MATCHING_REQUEST_EXAMPLE,
    SKU_NOT_FOUND_RESPONSE,
    SKU_RECOMMENDATION_ACCEPTED_RESPONSE,
    TAGGING_RESULT_SAVE_SUCCESS_RESPONSE,
    TAGGING_RESULT_UNPROCESSABLE_RESPONSE,
    TAGGING_TARGET_NOT_FOUND_RESPONSE,
    VALIDATION_ERROR_RESPONSE,
)
from app.core import database
from app.core.error_codes import ErrorCode
from app.dependencies import get_sku_match_service, get_tagging_service
from app.models.ai_job import AiJobType
from app.repositories import ai_job_repository, scene_image_repository
from app.repositories.scene_image_repository import SceneImageNotFoundError
from app.schemas import ai_job as ai_job_schema
from app.schemas import common as common_schema
from app.schemas.tagging import (
    SceneObjectUpdateRequest,
    SearchCandidateMoodRequest,
    SearchCandidateMoodResult,
    SkuMatchingRequest,
    SkuMatchingResult,
)
from app.services import sku_match_service as sku_match
from app.services.tagging_service import SkuNotFoundError, TaggingService

router = APIRouter(prefix="/tagging", tags=["tagging"])

_DETECTED_SCENE_STATUS = "detected"
_RECOMMENDATION_NOT_READY_MESSAGE = (
    "가구 탐지가 완료된 이미지에 대해서만 SKU 추천을 요청할 수 있습니다."
)


async def _enqueue_recommendation_job(
    database_session: database.sqlalchemy_async.AsyncSession,
    scene_id: int,
    recommendation_request: SceneObjectUpdateRequest,
) -> ai_job_schema.AiJobAcceptedResponse:
    """편집 객체를 DB에 저장하지 않고 SKU 추천 Job으로 접수합니다."""
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
            input_payload={
                "objects": [
                    item.model_dump(mode="json")
                    for item in recommendation_request.objects
                ]
            },
        )
    except ai_job_repository.ActiveAiJobExistsError as error:
        raise HTTPException(
            status_code=409,
            detail="이미 진행 중인 SKU 추천 작업이 있습니다.",
        ) from error

    return ai_job_schema.AiJobAcceptedResponse(
        scene_image_id=scene_id,
        job_id=job.job_id,
    )


@router.post(
    "/scenes/{scene_id}",
    response_model=common_schema.SuccessResponse[
        ai_job_schema.AiJobAcceptedResponse
    ],
    status_code=202,
    summary="편집 객체별 SKU 추천 작업 접수",
    description=(
        "사용자가 편집한 바운딩 박스와 카테고리를 추천 Job 입력으로 접수합니다. "
        "객체 정보는 최종 SKU 확정 전까지 DB에 저장하지 않습니다."
    ),
    response_description=(
        "공통 성공 응답으로 연출 이미지 ID와 대기 중인 AI 작업 ID를 반환합니다."
    ),
    responses={
        202: SKU_RECOMMENDATION_ACCEPTED_RESPONSE,
        404: SCENE_IMAGE_NOT_FOUND_RESPONSE,
        409: {
            "description": "가구 탐지가 완료되지 않았거나 같은 추천 작업이 진행 중입니다.",
            "content": {
                "application/json": {
                    "examples": {
                        "detection_not_ready": AI_JOB_NOT_READY_RESPONSE[
                            "content"
                        ]["application/json"]["example"],
                        "active_recommendation_job": (
                            ACTIVE_AI_JOB_EXISTS_RESPONSE["content"][
                                "application/json"
                            ]["example"]
                        ),
                    }
                }
            },
        },
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
) -> common_schema.SuccessResponse[ai_job_schema.AiJobAcceptedResponse]:
    """편집 객체를 비동기 SKU 추천 Job으로 접수합니다."""
    result = await _enqueue_recommendation_job(
        database_session,
        scene_id,
        update_request,
    )
    return common_schema.success_response(result)


@router.post(
    "/scenes/{scene_id}/recommendations",
    response_model=common_schema.SuccessResponse[
        ai_job_schema.AiJobAcceptedResponse
    ],
    status_code=202,
    summary="편집 객체별 SKU 추천 작업 접수",
    description=(
        "가구 탐지가 완료된 연출 이미지의 편집 객체에 대해 유사 SKU 추천 작업을 "
        "대기열에 접수합니다. 객체 정보는 Job payload로만 전달하며, 추천 결과는 "
        "응답의 job_id로 GET /ai-jobs/{job_id}를 폴링해 확인합니다."
    ),
    response_description=(
        "공통 성공 응답으로 연출 이미지 ID와 대기 중인 AI 작업 ID를 반환합니다."
    ),
    responses={
        202: SKU_RECOMMENDATION_ACCEPTED_RESPONSE,
        404: SCENE_IMAGE_NOT_FOUND_RESPONSE,
        409: {
            "description": "가구 탐지가 완료되지 않았거나 같은 추천 작업이 진행 중입니다.",
            "content": {
                "application/json": {
                    "examples": {
                        "detection_not_ready": AI_JOB_NOT_READY_RESPONSE[
                            "content"
                        ]["application/json"]["example"],
                        "active_recommendation_job": (
                            ACTIVE_AI_JOB_EXISTS_RESPONSE["content"][
                                "application/json"
                            ]["example"]
                        ),
                    }
                }
            },
        },
        422: VALIDATION_ERROR_RESPONSE,
    },
)
async def enqueue_sku_recommendation(
    scene_id: int = Path(
        description="SKU 추천 작업을 접수할 연출 이미지 ID입니다.",
        openapi_examples={"scene": {"summary": "연출 이미지", "value": 101}},
    ),
    recommendation_request: SceneObjectUpdateRequest = Body(
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
) -> common_schema.SuccessResponse[ai_job_schema.AiJobAcceptedResponse]:
    """탐지 완료된 장면의 편집 객체를 비동기 SKU 추천 Job으로 접수합니다."""
    result = await _enqueue_recommendation_job(
        database_session,
        scene_id,
        recommendation_request,
    )
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
    """탐지 객체별로 선택한 SKU를 최종 확정해 저장합니다."""
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


@router.post(
    "/scenes/{scene_id}/search-candidates/mood",
    response_model=common_schema.SuccessResponse[SearchCandidateMoodResult],
    summary="검색으로 선택한 SKU의 VLM 분위기·스타일 태그 계산",
    description=(
        "전체 카탈로그 검색으로 선택한 SKU에 대해, AI 추천 후보와 같은 XAI "
        "채점 방식으로 크롭과 SKU 이미지를 비교해 공간 분위기와 스타일 "
        "태그를 계산합니다. match_source가 SEARCH인 결과는 순위 근거"
        "(xai_result)를 저장할 수 없으므로 vlm_mood만 반환합니다. VLM "
        "채점 자체가 실패해도 SKU 선택 흐름을 막지 않도록, 실패 시 빈 "
        "vlm_mood(200)를 반환합니다."
    ),
    response_description=(
        "공통 성공 응답으로 공간 분위기 요약과 스타일 태그를 반환합니다."
    ),
    responses={
        200: SEARCH_CANDIDATE_MOOD_SUCCESS_RESPONSE,
        404: {
            "description": "연출 이미지 또는 SKU 코드를 찾지 못한 경우입니다.",
            "content": {
                "application/json": {
                    "examples": {
                        "scene_not_found": SCENE_IMAGE_NOT_FOUND_RESPONSE[
                            "content"
                        ]["application/json"]["example"],
                        "sku_not_found": SKU_NOT_FOUND_RESPONSE["content"][
                            "application/json"
                        ]["example"],
                    }
                }
            },
        },
        422: VALIDATION_ERROR_RESPONSE,
    },
)
async def score_search_candidate_mood(
    scene_id: int = Path(
        description="크롭을 잘라낼 연출 이미지 ID입니다.",
        openapi_examples={"scene": {"summary": "연출 이미지", "value": 101}},
    ),
    mood_request: SearchCandidateMoodRequest = Body(
        openapi_examples={
            "search_selected_sofa": {
                "summary": "검색으로 선택한 소파 SKU의 분위기를 계산하는 경우",
                "value": SEARCH_CANDIDATE_MOOD_REQUEST_EXAMPLE,
            }
        },
    ),
    tagging_service: TaggingService = Depends(get_tagging_service),
) -> common_schema.SuccessResponse[SearchCandidateMoodResult]:
    """검색으로 선택한 SKU의 VLM 공간 분위기·스타일 태그를 계산합니다."""
    try:
        vlm_mood = await tagging_service.score_search_selected_sku(
            scene_id, mood_request.object, mood_request.sku_code
        )
    except SceneImageNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except SkuNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail={
                "code": ErrorCode.SKU_NOT_FOUND.value,
                "message": ErrorCode.SKU_NOT_FOUND.default_message,
            },
        ) from error

    return common_schema.success_response(
        SearchCandidateMoodResult(vlm_mood=vlm_mood)
    )
