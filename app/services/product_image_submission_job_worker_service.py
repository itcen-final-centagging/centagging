"""제품 이미지 등록 추천 작업 한 건을 선점해 처리하는 Worker 서비스입니다."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.product_image_submission_job import ProductImageSubmissionJob
from app.repositories import product_image_submission_job_repository
from app.services.gemini_service import GeminiService
from app.services.product_image_recommendation_service import (
    recommend_for_submission,
)

_LOGGER = logging.getLogger(__name__)
_RECOMMENDATION_FAILURE_CODE = "PRODUCT_IMAGE_RECOMMENDATION_FAILED"
_RECOMMENDATION_FAILURE_MESSAGE = "제품 이미지 SKU 추천에 실패했습니다."


async def process_next_job(
    session: AsyncSession,
    settings: Settings,
    worker_id: str,
) -> ProductImageSubmissionJob | None:
    """가장 오래된 대기 작업 한 건을 선점하고 완료 상태까지 처리합니다."""
    job = await product_image_submission_job_repository.claim_next_job(
        session, worker_id
    )
    if job is None:
        return None

    job_id = job.job_id
    try:
        result_payload = await recommend_for_submission(
            session,
            settings,
            GeminiService(settings=settings),
            job.submission_id,
        )
        return await product_image_submission_job_repository.mark_job_succeeded(
            session,
            job_id,
            result_payload,
        )
    except Exception:  # pylint: disable=broad-exception-caught
        _LOGGER.exception("제품 이미지 추천 작업에 실패했습니다: %s", job_id)
        await session.rollback()
        return await product_image_submission_job_repository.mark_job_failed(
            session,
            job_id,
            _RECOMMENDATION_FAILURE_CODE,
            _RECOMMENDATION_FAILURE_MESSAGE,
        )
