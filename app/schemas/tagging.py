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
    vlm_mood: VlmMood = Field(default_factory=VlmMood)


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

    label: str = Field(min_length=1, max_length=100)
    bbox: BoundingBox


class SceneObjectUpdateRequest(BaseModel):
    """추천 전에 반영할 최종 탐지 객체 목록입니다."""

    objects: list[EditedSceneObject] = Field(min_length=1)


class SceneObjectUpdateResult(BaseModel):
    """객체 편집 반영 결과입니다."""

    object_count: int
    processing_status: typing.Literal["DETECTED"] = "DETECTED"


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


class ObjectAttributes(BaseModel):
    """탐지 객체 속성입니다."""

    color: str
    material: str
    style: str


class ObjectMetadata(BaseModel):
    """확정 시점의 탐지 객체 속성입니다."""

    object_index: int
    category: str
    sub_category: str
    bbox_coord: BoundingBox
    attrs: ObjectAttributes

class SkuMatching(BaseModel):
    """확정할 객체-SKU 매핑 1건입니다.

     tagging_result 한 건에 해당하는 선택된 SKU입니다.
     - RECOMMEND: AI 추천 후보에서 사용자가 선택한 SKU
       → 순위와 유사도가 있어야 합니다.
     - SEARCH: 전체 검색에서 사용자가 직접 선택한 SKU
       → 순위와 유사도가 없어야 합니다.
     DB의 ck_result_source 조건과 같은 규칙을 따릅니다.
    """

    object_index: int = Field(ge=0)
    sku_id: int = Field(ge=1)
    sku_image_id: int | None = None
    match_source: typing.Literal["RECOMMEND", "SEARCH"]
    match_rank: int | None = Field(default=None, ge=1)
    similarity_score: int | None = Field(default=None, ge=0, le=100)
    object_metadata: ObjectMetadata
    xai_result: XaiResult | None = None
    vlm_mood: VlmMood = Field(default_factory=VlmMood)

    @model_validator(mode="after")
    def validate_source_consistency(self) -> "SkuMatching":
        """match_source별 필드 조합이 DB 제약(ck_result_source)과 맞는지 검증합니다."""
        if self.match_source == "SEARCH":
            if (
                self.match_rank is not None
                or self.similarity_score is not None
                or self.xai_result is not None
            ):
                raise ValueError(
                    "match_source가 SEARCH이면 match_rank/similarity_score/"
                    "xai_result는 비어 있어야 합니다."
                )
        elif self.match_rank is None or self.similarity_score is None:
            raise ValueError(
                "match_source가 RECOMMEND이면 match_rank와 similarity_score가 "
                "필요합니다."
            )
        return self


class SkuMatchingRequest(BaseModel):
    """탐지 객체 저장 요청입니다."""

    tagging_results: list[SkuMatching] = Field(min_length=1)


class SkuMatchingResult(BaseModel):
    """SKU 확정 결과 본문입니다."""

    processing_status: typing.Literal["CONFIRMED"] = "CONFIRMED"
    result_ids: list[int]
