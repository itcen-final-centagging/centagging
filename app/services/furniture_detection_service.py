from app.core.config import Settings
from app.schemas.gemini_detection import GeminiDetectionResult
from app.services.gemini_service import GeminiService
from app.services.image_processing_service import decode_image


def detect_furniture_from_bytes(
    image_bytes: bytes,
    settings: Settings
) -> GeminiDetectionResult:
    """이미지 바이트를 받아서 바이트 결과를 반환합니다."""

    pil_image = decode_image(image_bytes)
    service = GeminiService(settings)

    return service.detect_furniture(pil_image)