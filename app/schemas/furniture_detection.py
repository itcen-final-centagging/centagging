"""가구 객체 탐지 API 요청 및 응답 스키마입니다."""

from pydantic import BaseModel, Field


class DetectedObjectResponse(BaseModel):
    """외부 API에 노출하는 탐지 객체입니다."""

    label: str
    box_2d: list[int] = Field(
        min_length=4,
        max_length=4,
    )


class FurnitureDetectionResponse(BaseModel):
    """가구 객체 탐지 API 응답입니다."""

    scene_image_id: int
    analysis_status: str
    object_count: int
    processing_time_ms: int
    width_px: int
    height_px: int
    detections: list[DetectedObjectResponse] = Field(default_factory=list)


class FurnitureDetectionRequest(BaseModel):
    """가구 객체 탐지 API 요청입니다."""

    target_description: str = Field(
        min_length=2,
        max_length=100,
    )
