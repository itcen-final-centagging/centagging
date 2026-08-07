from pydantic import BaseModel, Field

"""
탐지된 객체 예시 데이터 셋.
{
  "detectionId": 301,
  "sceneImageId": 1001,
  "status": "DETECTED",
  "image": {
    "width": 1920,
    "height": 1080,
    "contentType": "image/jpeg"
  },
  "objects": [
    {
      "objectId": 5001,
      "categoryId": 21,
      "category": "의자",
      "subCategory": "사무용 의자",
      "label": "사무용 의자",
      "confidence": null,
      "confidenceSource": "NOT_PROVIDED",
      "bbox": [120, 80, 420, 650],
      "attributes": {
        "color": "black",
        "material": "mesh"
      },
      "cropUrl": null,
      "selected": False
    }
  ],
  "objectCount": 1,
  "processingTimeMs": 1320
}
"""

class ImageSizeResponse(BaseModel):
    width: int
    height: int


class DetectedObjectResponse(BaseModel):
    object_id: int
    label: str
    category: str | None = None
    subCategory: str | None = None
    confidence: float | None = None
    confidenceSource: str = "NOT_PROVIDED"
    bbox: tuple[int, int, int, int]
    attributes: dict[str, object] = {}
    crop_url: str | None = None
    selected: bool = False


class FurnitureDetectionResponse(BaseModel):
    scene_image_id: int
    status: str
    image_size: ImageSizeResponse
    object_count: int
    processing_time_ms: int
    objects: list[DetectedObjectResponse]


class DetectedObjectListResponse(BaseModel):
    scene_image_id: int
    status: str
    image_size: ImageSizeResponse
    object_count: int
    objects: list[DetectedObjectResponse]

class FurnitureDetectionRequest(BaseModel):
    target_description: str = Field(
        min_length=2,
        max_length=100,
    )