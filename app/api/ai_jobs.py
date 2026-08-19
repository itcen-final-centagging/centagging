"""AI 분석 작업 상태와 결과를 조회하는 API입니다."""

import uuid

import fastapi
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import database
from app.repositories import ai_job_repository
from app.schemas import ai_job as ai_job_schema
from app.schemas import common as common_schema

router = fastapi.APIRouter(prefix="/ai-jobs", tags=["ai-jobs"])


@router.get(
    "/{job_id}",
    response_model=common_schema.SuccessResponse[ai_job_schema.AiJobResponse],
)
async def get_ai_job(
    job_id: uuid.UUID,
    session: AsyncSession = fastapi.Depends(database.get_database_session),
) -> common_schema.SuccessResponse[ai_job_schema.AiJobResponse]:
    """프론트엔드가 폴링할 AI 작업의 현재 상태와 결과를 반환합니다."""
    try:
        job = await ai_job_repository.get_job(session, job_id)
    except ai_job_repository.AiJobNotFoundError as error:
        raise fastapi.HTTPException(
            status_code=404,
            detail="AI 분석 작업을 찾을 수 없습니다.",
        ) from error

    return common_schema.success_response(
        ai_job_schema.AiJobResponse.model_validate(job)
    )
