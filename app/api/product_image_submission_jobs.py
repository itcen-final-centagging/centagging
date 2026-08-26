"""제품 이미지 등록 추천 작업 상태와 결과를 조회하는 API입니다."""

import uuid

import fastapi
from sqlalchemy.ext.asyncio import AsyncSession

from app import dependencies
from app.api.examples import (
    PRODUCT_IMAGE_SUBMISSION_JOB_NOT_FOUND_RESPONSE,
    PRODUCT_IMAGE_SUBMISSION_JOB_STATUS_RESPONSE,
)
from app.core import database
from app.repositories import product_image_submission_job_repository
from app.repositories.product_image_submission_job_repository import (
    ProductImageSubmissionJobNotFoundError,
)
from app.schemas import common as common_schema
from app.schemas import product_image_submission_job as job_schema

router = fastapi.APIRouter(
    prefix="/product-image-submission-jobs",
    tags=["product-image-submission-jobs"],
)


@router.get(
    "/{job_id}",
    response_model=common_schema.SuccessResponse[
        job_schema.ProductImageSubmissionJobResponse
    ],
    summary="제품 이미지 등록 추천 작업 상태 및 결과 조회",
    description=(
        "업로드 직후 접수한 제품 이미지 추천 작업의 상태를 조회합니다. "
        "클라이언트는 PENDING 또는 RUNNING 상태인 동안 이 API를 주기적으로 "
        "호출하고, SUCCEEDED가 되면 result_payload에서 후보와 추출 속성을 "
        "사용합니다. FAILED 상태에서는 재시도 없이 수동 입력 경로로 "
        "안내합니다."
    ),
    response_description="공통 성공 응답으로 추천 작업의 상태와 결과를 반환합니다.",
    responses={
        200: PRODUCT_IMAGE_SUBMISSION_JOB_STATUS_RESPONSE,
        404: PRODUCT_IMAGE_SUBMISSION_JOB_NOT_FOUND_RESPONSE,
    },
)
async def get_product_image_submission_job(
    job_id: uuid.UUID = fastapi.Path(
        description="조회할 제품 이미지 등록 추천 작업 UUID입니다.",
    ),
    _user: dependencies.AdminUser = fastapi.Depends(
        dependencies.get_admin_user
    ),
    session: AsyncSession = fastapi.Depends(database.get_database_session),
) -> common_schema.SuccessResponse[
    job_schema.ProductImageSubmissionJobResponse
]:
    """프론트엔드가 폴링할 추천 작업의 현재 상태와 결과를 반환합니다."""
    try:
        job = await product_image_submission_job_repository.get_job(
            session, job_id
        )
    except ProductImageSubmissionJobNotFoundError as error:
        raise fastapi.HTTPException(
            status_code=404,
            detail="제품 이미지 등록 추천 작업을 찾을 수 없습니다.",
        ) from error

    return common_schema.success_response(
        job_schema.ProductImageSubmissionJobResponse.model_validate(job)
    )
