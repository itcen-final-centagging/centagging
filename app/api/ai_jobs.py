"""AI 분석 작업 상태와 결과를 조회하는 API입니다."""

import uuid

import fastapi
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.examples import AI_JOB_NOT_FOUND_RESPONSE, AI_JOB_STATUS_RESPONSE
from app.core import database
from app.repositories import ai_job_repository
from app.schemas import ai_job as ai_job_schema
from app.schemas import common as common_schema

router = fastapi.APIRouter(prefix="/ai-jobs", tags=["ai-jobs"])


@router.get(
    "/{job_id}",
    response_model=common_schema.SuccessResponse[ai_job_schema.AiJobResponse],
    summary="AI 분석 작업 상태 및 결과 조회",
    description=(
        "비동기로 접수한 가구 탐지 또는 SKU 추천 작업의 상태를 조회합니다. "
        "클라이언트는 PENDING 또는 RUNNING 상태인 동안 이 API를 주기적으로 "
        "호출하고, SUCCEEDED가 되면 result_payload에서 분석 결과를 사용합니다. "
        "FAILED 상태에서는 error_code와 error_message를 확인합니다."
    ),
    response_description="공통 성공 응답으로 AI 작업의 상태와 결과를 반환합니다.",
    responses={
        200: AI_JOB_STATUS_RESPONSE,
        404: AI_JOB_NOT_FOUND_RESPONSE,
    },
)
async def get_ai_job(
    job_id: uuid.UUID = fastapi.Path(
        description="조회할 비동기 AI 작업 UUID입니다.",
        openapi_examples={
            "detection_job": {
                "summary": "가구 탐지 작업",
                "value": "f3d4a95c-0e40-4cbb-a8ed-f0b1b2098f12",
            }
        },
    ),
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
