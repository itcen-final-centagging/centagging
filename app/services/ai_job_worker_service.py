"""AI 작업 한 건을 선점해 실제 분석을 수행하는 Worker 서비스입니다."""

import logging
import pathlib
import typing

from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.ai_job import AiJob, AiJobType
from app.models.scene_image import SceneImage
from app.repositories import ai_job_repository, scene_image_repository
from app.schemas.furniture_detection import (
    BoundingBoxResponse,
    DetectedObjectResponse,
)
from app.schemas.gemini_detection import GeminiDetectionResult
from app.schemas.tagging import EditedSceneObject
from app.services import furniture_attribute_rules, furniture_detection_service
from app.services.gemini_service import GeminiService
from app.services.image_processing_service import crop_scene_objects
from app.services.object_attribute_extraction_service import (
    ObjectAttributeExtractionService,
)
from app.services.similar_sku_service import SimilarSkuService
from app.services.tagging_service import TaggingService
from app.services.xai_scoring_service import XaiScoringService

_LOGGER = logging.getLogger(__name__)
_DETECTION_FAILURE_CODE = "DETECT_SCENE_FAILED"
_DETECTION_FAILURE_MESSAGE = "가구 탐지에 실패했습니다."
_RECOMMENDATION_FAILURE_CODE = "RECOMMEND_SKU_FAILED"
_RECOMMENDATION_FAILURE_MESSAGE = "SKU 추천에 실패했습니다."
_UNSUPPORTED_JOB_CODE = "UNSUPPORTED_JOB_TYPE"
_UNSUPPORTED_JOB_MESSAGE = "지원하지 않는 AI 작업 유형입니다."


class UnsupportedAiJobTypeError(RuntimeError):
    """현재 Worker가 처리하지 않는 AI 작업 유형입니다."""


def _resolve_image_path(settings: Settings, image_url: str) -> pathlib.Path:
    """공개 이미지 URL을 Worker 컨테이너 내부 저장 경로로 변환합니다."""
    storage_root = pathlib.Path(settings.image_storage_root).resolve()
    relative_path = image_url.replace("\\", "/").removeprefix("/uploads/")
    image_path = (storage_root / relative_path).resolve()

    try:
        image_path.relative_to(storage_root)
    except ValueError as error:
        raise ValueError("scene image path escapes storage root") from error
    return image_path


def _build_detected_objects(
    detection_result: GeminiDetectionResult,
) -> list[DetectedObjectResponse]:
    """내부 Gemini 탐지 결과를 공개 응답 객체로 변환합니다."""
    return [
        DetectedObjectResponse(
            object_idx=object_index,
            category=detection.category,
            sub_category=None,
            bbox_coord=BoundingBoxResponse(
                xmin=round(detection.bbox_coord.xmin),
                ymin=round(detection.bbox_coord.ymin),
                xmax=round(detection.bbox_coord.xmax),
                ymax=round(detection.bbox_coord.ymax),
            ),
            confidence=detection.confidence,
            evidence=detection.evidence,
        )
        for object_index, detection in enumerate(detection_result.detections)
    ]


def _build_enriched_evidence(
    category: str,
    attrs: dict[str, str],
    original_evidence: str,
) -> str:
    """추출된 객체 속성을 기반으로 화면용 탐지 근거를 생성합니다."""
    descriptors = furniture_attribute_rules.build_evidence_descriptors(
        category, attrs
    )

    if not descriptors:
        normalized_evidence = original_evidence.strip()
        if normalized_evidence.endswith("판단했습니다."):
            return normalized_evidence
        return (
            f"{normalized_evidence.rstrip('.')}. 해당 형태와 구조를 근거로 "
            f"{category}로 판단했습니다."
        )

    return f"{', '.join(descriptors[:3])} 등이 확인되어 {category}로 판단했습니다."


def _mark_detection_succeeded(scene: SceneImage) -> None:
    """장면 이미지의 탐지 완료 상태만 기록합니다."""
    scene.analysis_status = "detected"
    scene.analysis_error = None


async def _detect_scene(
    session: AsyncSession,
    job: AiJob,
    settings: Settings,
) -> dict[str, object]:
    """장면 원본을 탐지하고 DB에 저장할 성공 결과를 구성합니다."""
    scene = await scene_image_repository.get_scene_image(
        session, job.scene_image_id
    )
    image_path = _resolve_image_path(settings, scene.image_url)
    image_bytes = await run_in_threadpool(image_path.read_bytes)
    detection_result = await run_in_threadpool(
        furniture_detection_service.detect_furniture_from_bytes,
        image_bytes,
        settings,
    )
    detections = _build_detected_objects(detection_result)

    object_metadata = [
        detection.model_dump(mode="json") for detection in detections
    ]
    crops = await run_in_threadpool(
        crop_scene_objects,
        image_path,
        object_metadata,
    )
    category_by_idx = {
        detection.object_idx: detection.category for detection in detections
    }
    attribute_extraction_service = ObjectAttributeExtractionService(
        settings=settings,
        gemini_service=GeminiService(settings=settings),
    )
    attributes_by_idx = await attribute_extraction_service.extract_for_crops(
        crops,
        category_by_idx,
    )

    for detection in detections:
        attribute_result = attributes_by_idx.get(detection.object_idx)

        if attribute_result is None:
            continue

        detection.sub_category = attribute_result.sub_category
        detection.attrs = attribute_result.attributes
        detection.vlm_mood = attribute_result.vlm_mood
        detection.evidence = _build_enriched_evidence(
            category=detection.category,
            attrs=detection.attrs,
            original_evidence=detection.evidence,
        )

    _mark_detection_succeeded(scene)
    await session.flush()

    return {
        "scene_image_id": scene.scene_image_id,
        "objects": [
            detection.model_dump(mode="json") for detection in detections
        ],
    }


def _build_tagging_service(
    session: AsyncSession,
    settings: Settings,
) -> TaggingService:
    """Worker가 SKU 추천에 사용할 태깅 서비스를 조립합니다."""
    gemini_service = GeminiService(settings=settings)

    return TaggingService(
        session=session,
        settings=settings,
        gemini_service=gemini_service,
        similar_sku_service=SimilarSkuService(
            session=session,
            gemini_service=gemini_service,
            settings=settings,
        ),
        xai_scoring_service=XaiScoringService(settings=settings),
    )


async def _recommend_sku(
    session: AsyncSession,
    job: AiJob,
    settings: Settings,
) -> dict[str, object]:
    """장면의 탐지 객체에 대한 SKU 추천 결과를 작업 결과로 만듭니다."""
    raw_objects = job.input_payload.get("objects")
    if not isinstance(raw_objects, list) or not raw_objects:
        raise ValueError("SKU 추천 작업에 편집 객체 목록이 없습니다.")
    if not all(isinstance(item, dict) for item in raw_objects):
        raise ValueError("SKU 추천 작업의 객체 입력 형식이 올바르지 않습니다.")

    objects = [EditedSceneObject.model_validate(item) for item in raw_objects]

    result = await _build_tagging_service(
        session,
        settings,
    ).get_sku_candidates(job.scene_image_id, objects=objects)
    return typing.cast(dict[str, object], result.model_dump(mode="json"))


async def _record_detection_failure(
    session: AsyncSession,
    job: AiJob,
    error_code: str,
    error_message: str,
) -> AiJob:
    """실패한 작업과 장면 상태를 재시도 횟수에 맞춰 함께 기록합니다."""
    job_id = job.job_id
    scene_image_id = job.scene_image_id
    is_final_attempt = job.attempt_count >= job.max_attempts
    await session.rollback()
    try:
        scene = await scene_image_repository.get_scene_image(
            session, scene_image_id
        )
    except scene_image_repository.SceneImageNotFoundError:
        scene = None

    if scene is not None:
        scene.analysis_status = "failed" if is_final_attempt else "pending"
        scene.analysis_error = error_message if is_final_attempt else None
        await session.flush()

    return await ai_job_repository.mark_job_failed(
        session,
        job_id,
        error_code,
        error_message,
    )


async def _record_job_failure(
    session: AsyncSession,
    job: AiJob,
    error_code: str,
    error_message: str,
) -> AiJob:
    """장면 상태를 바꾸지 않고 추천 작업의 실패 상태만 기록합니다."""
    job_id = job.job_id
    await session.rollback()
    return await ai_job_repository.mark_job_failed(
        session,
        job_id,
        error_code,
        error_message,
    )


async def process_next_job(
    session: AsyncSession,
    settings: Settings,
    worker_id: str,
) -> AiJob | None:
    """가장 오래된 대기 작업 한 건을 선점하고 완료 상태까지 처리합니다."""
    job = await ai_job_repository.claim_next_job(session, worker_id)
    if job is None:
        return None

    job_id = job.job_id
    try:
        if job.job_type == AiJobType.DETECT_SCENE.value:
            result_payload = await _detect_scene(session, job, settings)
        elif job.job_type == AiJobType.RECOMMEND_SKU.value:
            result_payload = await _recommend_sku(session, job, settings)
        else:
            raise UnsupportedAiJobTypeError(job.job_type)
        return await ai_job_repository.mark_job_succeeded(
            session,
            job_id,
            result_payload,
        )
    except UnsupportedAiJobTypeError:
        _LOGGER.exception("지원하지 않는 AI 작업입니다: %s", job_id)
        return await _record_job_failure(
            session,
            job,
            _UNSUPPORTED_JOB_CODE,
            _UNSUPPORTED_JOB_MESSAGE,
        )
    except Exception:  # pylint: disable=broad-exception-caught
        if job.job_type == AiJobType.DETECT_SCENE.value:
            _LOGGER.exception("가구 탐지 작업에 실패했습니다: %s", job_id)
            return await _record_detection_failure(
                session,
                job,
                _DETECTION_FAILURE_CODE,
                _DETECTION_FAILURE_MESSAGE,
            )

        _LOGGER.exception("SKU 추천 작업에 실패했습니다: %s", job_id)
        return await _record_job_failure(
            session,
            job,
            _RECOMMENDATION_FAILURE_CODE,
            _RECOMMENDATION_FAILURE_MESSAGE,
        )
