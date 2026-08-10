"""Gemini 객체 탐지 내부 응답 스키마입니다."""

from typing import Annotated

from pydantic import BaseModel, Field

# 좌표범위 제한(0~1000)
Coordinate = Annotated[float, Field(ge=0, le=1000)]


# Gemini  탐지 객체 label, 박스 크기(좌표 순서: [ymin, xmin, ymax, xmax], 좌표 범위)
class GeminiRawDetection(BaseModel):
    """Gemini가 반환하는 개별 탐지 객체입니다."""

    label: str = Field(min_length=1)
    box_2d: list[Coordinate] = Field(min_length=4, max_length=4)
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
