"""장면 이미지 태깅(유사 SKU 추천) API의 요청·응답 스키마입니다."""

import typing

from pydantic import BaseModel, Field, model_validator


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
    xai_attrs: dict[str, str] = Field(default_factory=dict)


class SkuCandidate(BaseModel):
    """탐지된 객체 1건에 대한 SKU 후보입니다."""

    sku_id: int
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


class BoundingBox(BaseModel):
    """0~1000으로 정규화된 탐지 객체 좌표입니다."""

    xmin: float = Field(ge=0, le=1000)
    ymin: float = Field(ge=0, le=1000)
    xmax: float = Field(ge=0, le=1000)
    ymax: float = Field(ge=0, le=1000)

    @model_validator(mode="after")
    def validate_area(self) -> "BoundingBox":
        """크롭 가능한 넓이를 가진 좌표인지 검증합니다."""
        if self.xmin >= self.xmax or self.ymin >= self.ymax:
            raise ValueError(
                "bbox는 xmin < xmax 및 ymin < ymax를 만족해야 합니다."
            )
        return self


class EditedSceneObject(BaseModel):
    """사용자가 편집 완료한 탐지 객체입니다."""

    category: str = Field(min_length=1, max_length=100)
    bbox_coord: BoundingBox


class SceneObjectUpdateRequest(BaseModel):
    """추천 전에 반영할 최종 탐지 객체 목록입니다."""

    objects: list[EditedSceneObject] = Field(min_length=1)


class SceneObjectUpdateResult(BaseModel):
    """객체 편집 반영 결과입니다."""

    object_count: int
    processing_status: typing.Literal["DETECTED"] = "DETECTED"


class DetectedObject(BaseModel):
    """탐지된 가구 객체의 속성과 SKU 후보 목록입니다."""

    object_idx: int
    category: str = ""
    sub_category: str | None = None
    bbox_coord: BoundingBox
    confidence: int = Field(default=0, ge=0, le=100)

    # furniture attribute extraction 결과
    attrs: dict[str, str] = Field(default_factory=dict)

    # XAI가 관찰한 객체 속성
    xai_attrs: dict[str, str] = Field(default_factory=dict)

    sku_candidates: list[SkuCandidate]


class DetectionResult(BaseModel):
    """객체 탐지 결과 본문입니다."""

    processing_status: str
    scene_image: SceneImageInfo
    objects: list[DetectedObject]


class ObjectAttributes(BaseModel):
    """탐지 객체 속성입니다."""

    color: str
    material: str
    style: str


class ObjectMetadata(BaseModel):
    """확정 시점의 탐지 객체 속성입니다."""

    object_idx: int
    category: str
    sub_category: str | None
    bbox_coord: BoundingBox
    attrs: dict[str, str]


class SkuMatching(BaseModel):
    """확정할 객체-SKU 매핑 1건입니다.

    tagging_result 테이블 1행에 대응하며, 추천 응답에서 사용자가 선택한
    후보를 그대로 돌려받습니다.
    """

    object_idx: int = Field(ge=0)
    sku_id: int = Field(ge=1)
    match_rank: int = Field(ge=1)
    similarity_score: int = Field(ge=0, le=100)
    object_metadata: ObjectMetadata
    xai_result: XaiResult
    vlm_mood: VlmMood = Field(default_factory=VlmMood)


class SkuMatchingRequest(BaseModel):
    """탐지 객체 저장 요청입니다."""

    tagging_results: list[SkuMatching] = Field(min_length=1)


class SkuMatchingResult(BaseModel):
    """SKU 확정 결과 본문입니다."""

    processing_status: typing.Literal["CONFIRMED"] = "CONFIRMED"
    result_ids: list[int]
