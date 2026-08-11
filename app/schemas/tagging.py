"""장면 이미지 태깅(유사 SKU 추천) API의 요청·응답 스키마입니다."""

import typing

from pydantic import BaseModel, Field


class MatchedSkuImage(BaseModel):
    """매칭 근거가 된 SKU 이미지입니다."""

    sku_image_id: int
    image_type: typing.Literal["MAIN", "ANGLE"]
    image_url: str

class XaiCriterion(BaseModel):
    """루브릭 기준 1건의 점수와 근거입니다."""

    label: typing.Literal["구조", "색상", "디테일", "맥락"]
    score: int = Field(ge=0, le=30)
    comment: str

class VlmMood(BaseModel):
    """크롭 이미지에서 읽어낸 분위기 요약입니다."""

    summary: str = ""
    tags: list[str] = Field(default_factory=list)


class XaiResult(BaseModel):
    """XAI 판정 요약입니다."""

    summary: str
    criteria: list[XaiCriterion] = Field(default_factory=list)
    vlm_mood: VlmMood = Field(default_factory=VlmMood)


class SkuCandidate(BaseModel):
    """탐지된 객체 1건에 대한 SKU 후보입니다."""

    sku_code: str
    product_name: str
    category: str
    sub_category: str
    attrs: dict[str, str]
    similarity_score: int
    matched_sku_image: MatchedSkuImage
    xai_result: XaiResult

class SceneImageInfo(BaseModel):
    """응답에 포함하는 장면 이미지 메타데이터입니다."""

    scene_image_id: int
    image_url: str
    origin_name: str
    mime_type: str
    file_size: int
    width_px: int
    height_px: int

# 추가 — 기존 bbox_coord: dict를 대체합니다.
class BoundingBox(BaseModel):
    """0~1000으로 정규화된 탐지 객체 좌표입니다."""

    xmin: float
    ymin: float
    xmax: float
    ymax: float


class DetectedObject(BaseModel):
    """탐지된 가구 객체 1건과 해당 SKU 후보 목록입니다."""

    object_index: int
    label: str = ""
    bbox: BoundingBox
    confidence: int = Field(default=0, ge=0, le=100)
    attrs: dict[str, str] = Field(default_factory=dict)
    sku_candidates: list[SkuCandidate]


class DetectionResult(BaseModel):
    """객체 탐지 결과 본문입니다."""

    processing_status: str
    scene_image: SceneImageInfo
    objects: list[DetectedObject]


class DetectionResponse(BaseModel):
    """객체 탐지 API 응답입니다."""

    status: typing.Literal["success", "error"]
    data: DetectionResult
