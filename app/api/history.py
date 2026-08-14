"""태깅 이력 목록과 상세 조회 경로입니다."""

import fastapi
from sqlalchemy.ext import asyncio as sqlalchemy_async

from app.core import database
from app.repositories import tagging_history_repository
from app.schemas import common as common_schema
from app.schemas import history as history_schema

router = fastapi.APIRouter(prefix="/history", tags=["history"])


@router.get(
    "/results",
    response_model=common_schema.SuccessResponse[
        history_schema.TaggingHistoryListData
    ],
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
)
async def get_tagging_history_detail(
    result_id: int,
    session: sqlalchemy_async.AsyncSession = fastapi.Depends(
        database.get_database_session
    ),
) -> common_schema.SuccessResponse[history_schema.TaggingHistoryDetail]:
    """결과 ID에 해당하는 태깅 이력 상세를 조회합니다.

    Args:
        result_id: 조회할 태깅 결과 ID입니다.
        session: 요청 범위의 비동기 DB 세션입니다.

    Returns:
        연출 이미지와 확정 SKU가 포함된 태깅 이력 상세입니다.

    Raises:
        HTTPException: 결과 ID에 해당하는 이력이 없을 때 발생합니다.
    """
    detail = await tagging_history_repository.get_tagging_history_detail(
        session,
        result_id,
    )
    if detail is None:
        raise fastapi.HTTPException(
            status_code=404,
            detail="태깅 이력을 찾을 수 없습니다.",
        )

    return common_schema.success_response(detail)
