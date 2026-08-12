"""가구 객체 탐지 API 요청 및 응답 스키마입니다."""

from typing import Annotated

from pydantic import BaseModel, Field, model_validator

NormalizedCoordinate = Annotated[int, Field(ge=0, le=1000)]


class DetectedObjectResponse(BaseModel):
    """외부 API에 노출하는 탐지 객체입니다."""

    category: str
    box_2d: list[NormalizedCoordinate] = Field(
        min_length=4,
        max_length=4,
    )
    @model_validator(mode="after")
    def validate_box_2d(self) -> "DetectedObjectResponse":
        ymin, xmin, ymax, xmax = self.box_2d
        
        if ymin >= ymax:
            raise ValueError("ymin 값은 ymax 값보다 작아야 합니다.")

        if xmin >= xmax:
            raise ValueError("xmin 값은 xmax 값보다 작아야 합니다.")

        return self


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
