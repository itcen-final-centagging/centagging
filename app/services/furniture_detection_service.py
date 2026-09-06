"""이미지 바이트와 Gemini 탐지 서비스를 연결합니다."""

from functools import partial

from app.core.config import Settings
from app.schemas.gemini_detection import (
    GeminiBoundingBox,
    GeminiDetectionResult,
    GeminiRawDetection,
)
from app.services.gemini_service import GeminiService
from app.services.image_processing_service import decode_image

MIN_VISIBLE_AREA_RATIO = 0.75


def _bbox_area(bbox: GeminiBoundingBox) -> float:
    """정규화 바운딩 박스의 면적을 반환합니다."""
    return (bbox.xmax - bbox.xmin) * (bbox.ymax - bbox.ymin)


def _intersection_area(
    target: GeminiBoundingBox,
    occluder: GeminiBoundingBox,
) -> float:
    """대상 객체와 가림 객체 바운딩 박스의 교차 면적을 반환합니다."""
    width = max(
        0.0,
        min(target.xmax, occluder.xmax) - max(target.xmin, occluder.xmin),
    )
    height = max(
        0.0,
        min(target.ymax, occluder.ymax) - max(target.ymin, occluder.ymin),
    )
    return width * height


def _evaluate_visible_area(
    detection: GeminiRawDetection,
    *,
    minimum_visible_ratio: float,
) -> tuple[GeminiRawDetection, bool]:
    """탐지 객체와 가림 면적 기준 통과 여부를 함께 반환합니다."""
    occluder_bbox = detection.occluder_bbox_coord

    if occluder_bbox is None:
        return detection, True

    target_area = _bbox_area(detection.bbox_coord)
    occluded_area = _intersection_area(
        detection.bbox_coord,
        occluder_bbox,
    )

    if occluded_area == 0:
        return detection, True

    visible_ratio = (target_area - occluded_area) / target_area
    return detection, visible_ratio >= minimum_visible_ratio


def filter_detections_by_visible_area(
    result: GeminiDetectionResult,
    minimum_visible_ratio: float = MIN_VISIBLE_AREA_RATIO,
) -> GeminiDetectionResult:
    """가림 객체를 제외한 면적이 기준 이상인 탐지만 유지합니다."""
    evaluator = partial(
        _evaluate_visible_area,
        minimum_visible_ratio=minimum_visible_ratio,
    )
    evaluations = map(evaluator, result.detections)
    detections = [
        detection for detection, should_keep in evaluations if should_keep
    ]

    return result.model_copy(update={"detections": detections})


def detect_furniture_from_bytes(
    image_bytes: bytes, settings: Settings
) -> GeminiDetectionResult:
    """이미지 바이트에서 가구 객체를 탐지합니다.

    Args:
        image_bytes: 디코딩할 이미지 바이트입니다.
        settings: Gemini 설정입니다.

    Returns:
        탐지 객체와 처리 시간이 포함된 결과입니다.
    """
    pil_image = decode_image(image_bytes)
    service = GeminiService(settings)

    result = service.detect_furniture(pil_image)
    return filter_detections_by_visible_area(result)
