"""이미지 바이트와 Gemini 탐지 서비스를 연결합니다."""

from app.core.config import Settings
from app.schemas.gemini_detection import GeminiDetectionResult
from app.services.gemini_service import GeminiService
from app.services.image_processing_service import decode_image


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

    return service.detect_furniture(pil_image)
