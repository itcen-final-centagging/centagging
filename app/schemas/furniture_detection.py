"""가구 객체 탐지 API 요청 및 응답 스키마입니다."""

from typing import Annotated
import datetime
from pydantic import BaseModel, Field, model_validator

NormalizedCoordinate = Annotated[int, Field(ge=0, le=1000)]


class BoundingBoxResponse(BaseModel):
    xmin: NormalizedCoordinate
    ymin: NormalizedCoordinate
    xmax: NormalizedCoordinate
    ymax: NormalizedCoordinate

    @model_validator(mode="after")
    def validate_direction(self) -> "BoundingBoxResponse":
        
        if self.ymin >= self.ymax:
            raise ValueError("ymin 값은 ymax 값보다 작아야 합니다.")

        if self.xmin >= self.xmax:
            raise ValueError("xmin 값은 xmax 값보다 작아야 합니다.")

        return self

class DetectedObjectResponse(BaseModel):
    """외부 API에 노출하는 탐지 객체입니다."""

    object_index: int = Field(ge=0)
    category: str = Field(min_length=1)
    sub_category: str | None = None
    bbox_coord: BoundingBoxResponse
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence: str = Field(min_length=1)


class SceneImageResponse(BaseModel):
    scene_image_id: int
    image_url: str
    origin_name: str
    mime_type: str
    file_size: int
    analysis_status: str
    analysis_error: str | None
    width_px: int
    height_px: int
    created_at: datetime.datetime

class FurnitureDetectionResponse(BaseModel):
    """가구 객체 탐지 API 응답입니다."""

    scene_image: SceneImageResponse
    object_count: int = Field(ge=0)
    objects: list[DetectedObjectResponse] = Field(default_factory=list)


class FurnitureDetectionRequest(BaseModel):
    """가구 객체 탐지 API 요청입니다."""

    target_description: str = Field(
        min_length=2,
        max_length=100,
    )
