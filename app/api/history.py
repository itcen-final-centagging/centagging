"""태깅 이력 목록과 상세 조회 경로입니다."""

import fastapi
from sqlalchemy.ext import asyncio as sqlalchemy_async

from app import dependencies
from app.api.examples import (
    HISTORY_DETAIL_SUCCESS_RESPONSE,
    HISTORY_LIST_SUCCESS_RESPONSE,
    HISTORY_NOT_FOUND_RESPONSE,
    VALIDATION_ERROR_RESPONSE,
)
from app.core import database
from app.repositories import tagging_history_repository
from app.schemas import common as common_schema
from app.schemas import history as history_schema
from app.services import sku_image_storage

router = fastapi.APIRouter(prefix="/history", tags=["history"])


@router.get(
    "/results",
    response_model=common_schema.SuccessResponse[
        history_schema.TaggingHistoryListData
    ],
    summary="태깅 이력 목록 조회",
    description=(
        "확정 저장된 태깅 결과를 최신순으로 조회합니다. "
        "각 항목에는 검수 이력 화면에 필요한 SKU 정보, 유사도, "
        "스타일 태그와 연출 이미지의 해당 객체 좌표가 포함됩니다."
    ),
    response_description=(
        "공통 성공 응답으로 최신순 태깅 이력 목록을 반환합니다."
    ),
    responses={200: HISTORY_LIST_SUCCESS_RESPONSE},
)
async def list_tagging_history(
    session: sqlalchemy_async.AsyncSession = fastapi.Depends(
        database.get_database_session
    ),
) -> common_schema.SuccessResponse[history_schema.TaggingHistoryListData]:
    """저장된 태깅 결과를 최신순으로 조회합니다.

    Args:
        session: 요청 범위의 비동기 DB 세션입니다.

    Returns:
        검수 이력 화면에 표시할 태깅 결과 목록입니다.
    """
    items = await tagging_history_repository.list_tagging_history(session)
    return common_schema.success_response(
        history_schema.TaggingHistoryListData(items=items)
    )


@router.get(
    "/results/{result_id}",
    response_model=common_schema.SuccessResponse[
        history_schema.TaggingHistoryDetail
    ],
    summary="태깅 이력 상세 조회",
    description=(
        "결과 ID로 태깅 이력 1건의 상세를 조회합니다. "
        "연출 이미지, 탐지 객체의 속성과 좌표, 확정된 SKU 정보, "
        "XAI 판정 근거를 함께 반환합니다."
    ),
    response_description=(
        "공통 성공 응답으로 연출 이미지와 확정 SKU가 포함된 상세 정보를 "
        "반환합니다."
    ),
    responses={
        200: HISTORY_DETAIL_SUCCESS_RESPONSE,
        404: HISTORY_NOT_FOUND_RESPONSE,
        422: VALIDATION_ERROR_RESPONSE,
    },
)
async def get_tagging_history_detail(
    result_id: int = fastapi.Path(
        description="조회할 태깅 결과 ID입니다.",
        openapi_examples={
            "result": {"summary": "확정된 태깅 결과", "value": 501}
        },
    ),
    session: sqlalchemy_async.AsyncSession = fastapi.Depends(
        database.get_database_session
    ),
    image_storage: sku_image_storage.SkuImageStorage = fastapi.Depends(
        dependencies.get_sku_image_storage
    ),
) -> common_schema.SuccessResponse[history_schema.TaggingHistoryDetail]:
    """결과 ID에 해당하는 태깅 이력 상세를 조회합니다.

    Args:
        result_id: 조회할 태깅 결과 ID입니다.
        session: 요청 범위의 비동기 DB 세션입니다.
        image_storage: SKU 이미지 공개 URL 변환기입니다.

    Returns:
        연출 이미지와 확정 SKU가 포함된 태깅 이력 상세입니다.

    Raises:
        HTTPException: 결과 ID에 해당하는 이력이 없을 때 발생합니다.
    """
    detail = await tagging_history_repository.get_tagging_history_detail(
        session,
        result_id,
        image_storage,
    )
    if detail is None:
        raise fastapi.HTTPException(
            status_code=404,
            detail="태깅 이력을 찾을 수 없습니다.",
        )

    return common_schema.success_response(detail)
