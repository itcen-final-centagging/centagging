"""AI 작업 한 건을 선점해 실제 분석을 수행하는 Worker 서비스입니다."""

import logging
import pathlib

from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.ai_job import AiJob, AiJobType
from app.models.scene_image import SceneImage
from app.repositories import ai_job_repository, scene_image_repository
from app.schemas.furniture_detection import DetectedObjectResponse
from app.schemas.gemini_detection import GeminiDetectionResult
from app.services import furniture_detection_service

_LOGGER = logging.getLogger(__name__)
_DETECTION_FAILURE_CODE = "DETECT_SCENE_FAILED"
_DETECTION_FAILURE_MESSAGE = "가구 탐지에 실패했습니다."
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
            label=detection.label,
            box_2d=[round(coordinate) for coordinate in detection.box_2d],
            evidence=detection.evidence,
            confidence=(
                round(detection.confidence * 100)
                if detection.confidence is not None
                else None
            ),
        )
        for detection in detection_result.detections
    ]


def _store_detection_result(
    scene: SceneImage,
    detections: list[DetectedObjectResponse],
) -> None:
    """장면 이미지 엔티티에 탐지 객체와 성공 상태를 기록합니다."""
    scene.object_metadata = [
        {
            "object_idx": object_index,
            "bbox_coord": {
                "xmin": detection.box_2d[1],
                "ymin": detection.box_2d[0],
                "xmax": detection.box_2d[3],
                "ymax": detection.box_2d[2],
            },
            "attribute": {"label": detection.label},
        }
        for object_index, detection in enumerate(detections)
    ]
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
    _store_detection_result(scene, detections)
    await session.flush()

    return {
        "scene_image_id": scene.scene_image_id,
        "detections": [
            detection.model_dump(mode="json") for detection in detections
        ],
    }


async def _record_failure(
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
        if job.job_type != AiJobType.DETECT_SCENE.value:
            raise UnsupportedAiJobTypeError(job.job_type)
        result_payload = await _detect_scene(session, job, settings)
        return await ai_job_repository.mark_job_succeeded(
            session,
            job_id,
            result_payload,
        )
    except UnsupportedAiJobTypeError:
        _LOGGER.exception("지원하지 않는 AI 작업입니다: %s", job_id)
        return await _record_failure(
            session,
            job,
            _UNSUPPORTED_JOB_CODE,
            _UNSUPPORTED_JOB_MESSAGE,
        )
    except Exception:  # pylint: disable=broad-exception-caught
        _LOGGER.exception("가구 탐지 작업에 실패했습니다: %s", job_id)
        return await _record_failure(
            session,
            job,
            _DETECTION_FAILURE_CODE,
            _DETECTION_FAILURE_MESSAGE,
        )
