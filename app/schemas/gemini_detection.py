from typing import Annotated
from pydantic import BaseModel, Field

# 좌표범위 제한(0~1000)
Coordinate = Annotated[float, Field(ge=0, le=1000)]

# Gemini  탐지 객체 label, 박스 크기(좌표 순서: [ymin, xmin, ymax, xmax], 좌표 범위)
class GeminiRawDetection(BaseModel):
    label:str = Field(min_length=1)
    box_2d: list[Coordinate] = Field(min_length=4, max_length=4)

# Gemini 탐지 결과 리스트
class GeminiDetectionResult(BaseModel):
    detections: list[GeminiRawDetection] = Field(default_factory=list)