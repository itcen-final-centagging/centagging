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


# 추가 — 기존 object_metadata의 좌표 dict를 대체합니다.
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


class SkuMatching(BaseModel):
    """확정할 객체-SKU 매핑 1건입니다.

    tagging_result 테이블 1행에 대응하며, 추천 응답에서 사용자가 선택한
    후보를 그대로 돌려받습니다.
    """

    # scene_image.object_metadata 배열의 인덱스입니다.
    object_index: int = Field(ge=0)
    sku_code: str = Field(min_length=1)
    match_rank: int = Field(ge=1)
    similarity_score: int = Field(ge=0, le=100)
    xai_result: XaiResult
    vlm_mood: VlmMood = Field(default_factory=VlmMood)


class SkuMatchingRequest(BaseModel):
    """탐지 객체별 SKU 확정 요청입니다."""

    # 빈 배열은 확정할 대상이 없다는 뜻이라 요청 자체를 거부합니다.
    matching: list[SkuMatching] = Field(min_length=1)


class SkuMatchingResult(BaseModel):
    """SKU 확정 결과 본문입니다."""

    processing_status: typing.Literal["CONFIRMED"] = "CONFIRMED"
    result_ids: list[int]
