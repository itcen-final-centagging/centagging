"""제품 이미지 등록 초안 1건의 SKU 추천 파이프라인을 조립합니다."""

import hashlib
import io
import typing

from fastapi.concurrency import run_in_threadpool
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.product_image_submission import ProductImageSubmission
from app.services import image_processing_service, sku_service
from app.services.fused_metadata import build_metadata_text
from app.services.gemini_service import GeminiService
from app.services.image_preprocessing_service import preprocess_for_embedding
from app.services.similar_sku_service import SimilarSkuService
from app.services.tagging_service import recommend_for_single_image
from app.services.xai_scoring_service import XaiScoringService


class SubmissionNotFoundError(RuntimeError):
    """추천 대상 제품 이미지 등록 요청이 없는 경우입니다."""


class SubmissionImageUnreadableError(RuntimeError):
    """등록 요청의 원본 이미지를 읽을 수 없는 경우입니다."""


def _image_sha256(image: Image.Image) -> str:
    """전처리 이미지의 고정 PNG 표현을 재색인 식별자로 해시합니다.

    ``approval_service._image_sha256``과 동일한 방식입니다(이 코드베이스의
    기존 관례대로 중복 작성).
    """
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG", optimize=False)
    return hashlib.sha256(buffer.getvalue()).hexdigest()


async def recommend_for_submission(
    session: AsyncSession,
    settings: Settings,
    gemini_service: GeminiService,
    submission_id: int,
) -> dict[str, typing.Any]:
    """등록 초안 1건을 분석해 후보 SKU와 추출 속성을 만듭니다.

    성공하면 같은 세션에 ``ProductImageSubmission``의 ``proposed_*``와
    ``draft_embedding`` 3필드를 채워 넣고(``flush``만 하고 커밋은 호출부에
    맡김), job에 저장할 ``result_payload``를 반환합니다.

    Args:
        session: Worker 범위의 비동기 SQLAlchemy 세션입니다.
        settings: 이미지 저장소 경로·임베딩 파이프라인 버전이 담긴 설정입니다.
        gemini_service: 카테고리/속성 추출과 융합 임베딩에 쓰는 서비스입니다.
        submission_id: 분석 대상 제품 이미지 등록 요청 ID입니다.

    Returns:
        ``proposed_category``/``proposed_sub_category``/``proposed_attributes``/
        ``sku_candidates``가 담긴, job의 ``result_payload``로 저장할 딕셔너리입니다.

    Raises:
        SubmissionNotFoundError: 등록 요청이 없는 경우입니다.
        SubmissionImageUnreadableError: 원본 이미지를 읽을 수 없는 경우입니다.
        image_processing_service.InvalidImageError: 이미지 디코딩에 실패한
            경우입니다.
        sku_service.SkuConfigurationError: Google Gen AI 인증 설정이 없는
            경우입니다.
        sku_service.SkuExtractionError: 카테고리/속성 추출 호출에 실패한
            경우입니다.
    """
    submission = await session.get(ProductImageSubmission, submission_id)
    if submission is None:
        raise SubmissionNotFoundError(submission_id)

    image_bytes = image_processing_service.read_sku_image_bytes(
        submission.image_url,
        settings.sku_image_root,
        settings.image_storage_root,
    )
    if image_bytes is None:
        raise SubmissionImageUnreadableError(submission_id)

    metadata = await run_in_threadpool(
        sku_service.extract_metadata, settings, image_bytes
    )
    category = metadata["category"] or ""

    decoded_image = image_processing_service.decode_image(image_bytes)
    preprocessed = preprocess_for_embedding(decoded_image, settings)
    metadata_text = build_metadata_text(
        category=category,
        sub_category=metadata["sub_category"],
        attributes=metadata["attributes"],
    )

    similar_sku_service = SimilarSkuService(
        session=session,
        gemini_service=gemini_service,
        settings=settings,
    )
    xai_scoring_service = XaiScoringService(settings=settings)

    detected_object, embedding = await recommend_for_single_image(
        similar_sku_service,
        xai_scoring_service,
        preprocessed.image,
        metadata_text,
        category,
    )

    submission.proposed_category = category or None
    submission.proposed_sub_category = metadata["sub_category"]
    submission.proposed_attributes = metadata["attributes"]
    if embedding is not None:
        submission.draft_embedding = embedding
        submission.draft_embedding_pipeline_version = (
            settings.embedding_pipeline_version
        )
        submission.draft_embedding_image_sha256 = _image_sha256(
            preprocessed.image
        )
    await session.flush()

    return {
        "proposed_category": category or None,
        "proposed_sub_category": metadata["sub_category"],
        "proposed_attributes": metadata["attributes"],
        "sku_candidates": [
            candidate.model_dump(mode="json")
            for candidate in detected_object.sku_candidates
        ],
    }
