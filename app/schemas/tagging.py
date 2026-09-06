"""장면 이미지 태깅(유사 SKU 추천) API의 요청·응답 스키마입니다."""

import typing

from pydantic import BaseModel, Field, model_validator


class MatchedSkuImage(BaseModel):
    """매칭 근거가 된 SKU 이미지입니다."""

    sku_image_id: int
    image_type: typing.Literal["MAIN", "ANGLE"]
    image_url: str


class XaiCriterion(BaseModel):
    """XAI 판정 근거 1건입니다.

    v2까지는 루브릭 기준(구조/색상/디테일/맥락)의 점수를 담았고, v3부터는
    메타데이터 1건의 일치 여부를 담습니다. 화면과 저장 구조를 그대로 쓰기
    위해 배열과 필드 이름을 유지합니다.

    crop 판독값은 ``DetectedObject.xai_readings``에 crop당 한 번만 있고,
    ``value``에는 현재 SKU 후보 이미지에서 XAI가 직접 판독한 값을 담습니다.
    DB의 ``SkuCandidate.attrs``와 분리해 시각 판독 결과만 표시합니다.
    """

    # v2는 구조/색상/디테일/맥락을 넣었습니다. v3는 비워 둡니다.
    label: str = ""
    comment: str = ""

    # v3에서 추가한 필드입니다.
    key: str = ""
    value: str = ""
    verdict: typing.Literal["MATCH", "MISMATCH", "UNKNOWN"] | None = None

    # v1·v2 이력 호환용입니다. v3 응답에서는 항상 None입니다.
    score: int | None = Field(default=None, ge=0, le=30)


class VlmMood(BaseModel):
    """크롭 이미지에서 읽어낸 분위기 요약입니다."""

    summary: str = ""
    tags: list[str] = Field(default_factory=list)


class XaiCropReading(BaseModel):
    """crop 이미지에서 판독한 비교 항목 1건입니다.

    비교 항목 정의와 crop 판독값을 겸합니다. crop 하나의 속성이므로
    후보 수와 무관하게 crop당 한 번만 내려갑니다.

    화면 표시명은 담지 않습니다. 프론트엔드가 ``skuAttributes.ts``의
    ``ATTRIBUTE_LABELS``로 key를 한글 라벨로 바꾸고 있어, 백엔드가 같은
    표를 또 들고 있으면 같은 화면에서 문구가 갈립니다.
    """

    key: str
    # crop에서 값을 특정하지 못하면 빈 문자열입니다.
    value: str = ""
    # value가 비었을 때 그 사유입니다.
    note: str = ""


class XaiResult(BaseModel):
    """XAI 판정 요약입니다."""

    summary: str
    criteria: list[XaiCriterion] = Field(default_factory=list)

    # v3에서 추가한 필드입니다.
    common: str = ""
    difference: str = ""
    # 화면의 "XAI 메타데이터 일치도" 표시는 XAI 항목 판정 비율이 아니라
    # 후보 선정에 사용한 이미지 임베딩 유사도입니다.
    match_rate: int | None = Field(default=None, ge=0, le=100)

    # v1·v2 이력 호환용입니다. v3에서는 채우지 않습니다.
    # vlm_mood는 속성 추출 단계가 같은 crop으로 이미 뽑아 DetectedObject에
    # 넣고, crop 판독값은 xai_readings가 대신하므로 XAI가 다시 담지 않습니다.
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

    object_idx: int = Field(ge=0)
    category: str = Field(min_length=1, max_length=100)
    bbox_coord: BoundingBox
    sub_category: str | None = None
    attrs: dict[str, str] = Field(default_factory=dict)
    vlm_mood: VlmMood = Field(default_factory=VlmMood)
    needs_attribute_extraction: bool = True


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
    vlm_mood: VlmMood = Field(default_factory=VlmMood)

    # XAI가 관찰한 객체 속성
    # v3에서는 xai_readings 중 판독에 성공한 항목으로 채웁니다.
    xai_attrs: dict[str, str] = Field(default_factory=dict)

    # XAI 비교 항목 정의와 crop 판독값입니다. 후보마다 반복하지 않고
    # crop당 한 번만 내려가며, 후보의 criteria는 key로 이 목록을 참조합니다.
    xai_readings: list[XaiCropReading] = Field(default_factory=list)

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
    vlm_mood: VlmMood = Field(default_factory=VlmMood)


class SkuMatching(BaseModel):
    """확정할 객체-SKU 매핑 1건입니다.

    tagging_result 한 건에 해당하는 선택된 SKU입니다.
    - RECOMMEND: AI 추천 후보에서 사용자가 선택한 SKU
      → 순위와 유사도가 있어야 합니다.
    - SEARCH: 전체 검색에서 사용자가 직접 선택한 SKU
      → 순위와 유사도가 없어야 합니다.
    DB의 ck_result_source 조건과 같은 규칙을 따릅니다.
    """

    object_idx: int = Field(ge=0)
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


class SearchCandidateMoodRequest(BaseModel):
    """전체 카탈로그 검색으로 선택한 SKU의 VLM 분위기 계산 요청입니다."""

    object: EditedSceneObject
    sku_code: str = Field(min_length=1)


class SearchCandidateMoodResult(BaseModel):
    """검색으로 선택한 SKU의 VLM 분위기 계산 결과입니다.

    match_source가 SEARCH인 태깅 결과는 순위 근거(xai_result)를 저장할
    수 없으므로(SkuMatching.validate_source_consistency), vlm_mood만
    반환합니다.
    """

    vlm_mood: VlmMood = Field(default_factory=VlmMood)
