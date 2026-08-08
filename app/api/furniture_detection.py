from app.core import config
from app.schemas.gemini_detection import GeminiDetectionResult
from app.services import gemini_service
from PIL import Image
import fastapi

router = fastapi.APIRouter(prefix="/tagging", tags=["furniture-detection"])

@router.post("/{scene_image_id}", response_model=GeminiDetectionResult)
def detect_furniture(scene_image_id:int, image: fastapi.UploadFile = fastapi.File(...)) -> GeminiDetectionResult:
    """가구 탐지 API 엔드포인트입니다."""

    del scene_image_id # 현재 검증 단계에서는 DB 조회에 사용 X

    if image.content_type not in {"image/jpeg", "image/png"}:
        raise fastapi.HTTPException(
            status_code=400,
            detail="JPEG 이미지나 PNG 이미지만 가능합니다."
        )

    with Image.open(image.file) as uploaded_image:
        pil_image = uploaded_image.convert("RGB")

    service = gemini_service.GeminiService(config.get_settings())
    return service.detect_furniture(pil_image)