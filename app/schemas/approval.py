"""태깅 결과 승인 API의 요청·응답 스키마입니다."""

import datetime
import typing

import pydantic
from pydantic import alias_generators

from app.schemas import tagging as tagging_schema


class _CamelModel(pydantic.BaseModel):
    """JSON 응답을 camelCase로 직렬화하는 공통 모델입니다."""

    model_config = pydantic.ConfigDict(
        alias_generator=alias_generators.to_camel,
        populate_by_name=True,
    )


ApprovalStatus = typing.Literal["PENDING", "ACTIVE", "REJECTED"]


class BoundingBox(_CamelModel):
    """0~1000으로 정규화된 객체 바운딩 박스입니다."""

    xmin: float
    ymin: float
    xmax: float
    ymax: float


class ApprovalListItem(_CamelModel):
    """승인 요청 목록의 객체-SKU 매칭 1건입니다."""

    request_id: int
    status: ApprovalStatus
    requested_at: datetime.datetime
    requested_by_name: str | None = None
    reviewed_at: datetime.datetime | None = None
    reviewed_by_name: str | None = None
    scene_image_id: int
    origin_name: str
    scene_image_url: str
    object_idx: int
    category: str | None = None
    sku_code: str
    product_name: str
    similarity_score: float | None = None


class ApprovalListResponse(_CamelModel):
    """필터된 승인 요청 목록입니다."""

    items: list[ApprovalListItem]


class ApprovalSceneImage(_CamelModel):
    """승인 대상 원본 장면 이미지입니다."""

    scene_image_id: int
    image_url: str
    origin_name: str


class ApprovalObject(_CamelModel):
    """승인 대상 객체의 현재 위치·카테고리·추출된 속성입니다."""

    object_idx: int
    category: str | None = None
    sub_category: str | None = None
    attrs: dict[str, typing.Any] = pydantic.Field(default_factory=dict)
    bbox: BoundingBox | None = None


class ApprovalSku(_CamelModel):
    """승인 대상 객체에 매핑된 SKU입니다."""

    sku_id: int
    sku_code: str
    product_name: str
    brand: str | None = None
    price: int | None = None
    category: str | None = None
    sub_category: str | None = None
    attributes: dict[str, typing.Any] = pydantic.Field(default_factory=dict)
    image_url: str | None = None


class ApprovalXaiResult(_CamelModel):
    """승인 화면에 표시할 XAI 판단 근거입니다."""

    summary: str
    common: str = ""
    difference: str = ""
    criteria: list[tagging_schema.XaiCriterion] = pydantic.Field(
        default_factory=list
    )


class ApprovalActions(_CamelModel):
    """현재 상태에서 가능한 승인 작업입니다."""

    can_confirm: bool
    can_reject: bool


class ApprovalCandidateSku(_CamelModel):
    """추천 당시 함께 제시됐던 후보 SKU 1건입니다.

    match_rank는 추천 후보 배열에서의 순번(1부터)이다. 검색으로 직접
    선택해 확정한 SKU가 추천 후보 목록에 없으면 이 항목을 맨 앞에
    끼워 넣고 via_search=True, match_rank=0으로 표시한다(검색 확정은
    유사도·순위 개념이 없어 similarity_score도 항상 비어 있다).
    """

    sku_id: int
    sku_code: str
    product_name: str
    match_rank: int
    brand: str | None = None
    price: int | None = None
    category: str | None = None
    sub_category: str | None = None
    attributes: dict[str, typing.Any] = pydantic.Field(default_factory=dict)
    image_url: str | None = None
    similarity_score: float | None = None
    via_search: bool = False


class ApprovalDetailResponse(_CamelModel):
    """승인 화면에 표시할 요청 상세입니다."""

    request_id: int
    status: ApprovalStatus
    requested_by_name: str | None = None
    requested_at: datetime.datetime
    reviewed_by_name: str | None = None
    reviewed_at: datetime.datetime | None = None
    reject_reason: str | None = None
    scene_image: ApprovalSceneImage
    object: ApprovalObject
    sku: ApprovalSku
    similarity_score: float | None = None
    xai_result: ApprovalXaiResult | None = None
    candidates: list[ApprovalCandidateSku] = pydantic.Field(
        default_factory=list
    )
    actions: ApprovalActions


class RejectRequest(_CamelModel):
    """반려 사유 입력입니다."""

    reject_reason: str = pydantic.Field(min_length=1, max_length=255)


class ConfirmCreatedSkuImage(_CamelModel):
    """승인 후 SKU에 추가된 스타일링 이미지입니다."""

    sku_image_id: int
    image_url: str
    skipped: bool


class ConfirmResponse(_CamelModel):
    """승인 처리 결과입니다."""

    request_id: int
    status: typing.Literal["ACTIVE"] = "ACTIVE"
    reviewed_by_name: str
    reviewed_at: datetime.datetime
    created_sku_image: ConfirmCreatedSkuImage | None = None


class RejectResponse(_CamelModel):
    """반려 처리 결과입니다."""

    request_id: int
    status: typing.Literal["REJECTED"] = "REJECTED"
    reviewed_by_name: str
    reviewed_at: datetime.datetime
    reject_reason: str
