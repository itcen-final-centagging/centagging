"""Gemini 객체 탐지 내부 응답 스키마입니다."""

from typing import Annotated

from pydantic import BaseModel, Field, model_validator

# 좌표범위 제한(0~1000)
Coordinate = Annotated[float, Field(ge=0, le=1000)]


# Gemini 탐지 객체 좌표
class GeminiBoundingBox(BaseModel):
    """Gemini가 반환하는 0~1000 정규화 좌표입니다."""

    xmin: Coordinate
    ymin: Coordinate
    xmax: Coordinate
    ymax: Coordinate

    @model_validator(mode="after")
    def validate_direction(self) -> "GeminiBoundingBox":
        """좌표의 최솟값이 최댓값보다 작은지 검증합니다."""
        if self.xmin >= self.xmax:
            raise ValueError("xmin 값은 xmax 값보다 작아야 합니다.")
        if self.ymin >= self.ymax:
            raise ValueError("ymin 값은 ymax 값보다 작아야 합니다.")
        return self


# Gemini  탐지 객체 category, 박스 크기(좌표 순서: [ymin, xmin, ymax, xmax], 좌표 범위)
class GeminiRawDetection(BaseModel):
    """Gemini가 반환하는 개별 탐지 객체입니다."""

    category: str = Field(min_length=1)
    bbox_coord: GeminiBoundingBox
    evidence: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0, le=1)


# Gemini 탐지 결과 리스트
class GeminiModelDetectionResult(BaseModel):
    """Gemini 구조화 응답의 탐지 객체 목록입니다."""

    detections: list[GeminiRawDetection] = Field(default_factory=list)


# Gemini 반환 데이터(서버시간은 생성할 필요 없니 서버에서 확인)
class GeminiDetectionResult(BaseModel):
    """처리 시간을 포함한 내부 탐지 결과입니다."""

    detections: list[GeminiRawDetection] = Field(default_factory=list)
    processing_time_ms: int = Field(ge=0)
