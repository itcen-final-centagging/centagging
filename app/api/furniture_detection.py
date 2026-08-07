from app.schemas.furniture_detection import FurnitureDetectionResponse, ImageSizeResponse
import fastapi
import pydantic


class FurnitureDetectionRequest(pydantic.BaseModel):
    """가구 감지 API 요청 모델입니다."""
    image_url: str

router = fastapi.APIRouter(prefix="/api/v1/scene-images", tags=["furniture-detection"])

@router.post("/{scene_image_id}/detections", response_model=FurnitureDetectionResponse)
def detect_furniture(scene_image_id:int) -> FurnitureDetectionResponse:
    """가구 감지 API 엔드포인트입니다."""
    return FurnitureDetectionResponse(
        scene_image_id=scene_image_id,
        status="DETECTED",
        image_size=ImageSizeResponse(width=1920, height=1080),
        object_count=0,
        processing_time_ms=1320,
        objects=[]
    )