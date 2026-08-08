from pydantic import BaseModel, Field

"""
객체 탐지 결과 예시
{
  "detections": [
    {
      "label": "chair",
      "box_2d": [
        251,
        99,
        977,
        631
      ],
      evidence: "팔걸이 모양을 보았을 때 의자로 추정된다.",
      processing_time_ms: 123,
      confidence: 0.82
    }
  ]
}
"""


class DetectedObjectResponse(BaseModel):
    label: str
    box_2d: list[int] = Field(
        min_length=4,
        max_length=4,
    )


class FurnitureDetectionResponse(BaseModel):
    scene_image_id: int
    analysis_status: str
    object_count: int
    processing_time_ms: int
    width_px: int
    height_px: int
    detections: list[DetectedObjectResponse] = Field(default_factory=dict)

class FurnitureDetectionRequest(BaseModel):
    target_description: str = Field(
        min_length=2,
        max_length=100,
    )