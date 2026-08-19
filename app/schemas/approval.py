"""태깅 결과 승인 API의 요청·응답 스키마입니다."""

import datetime
import typing

import pydantic
from pydantic import alias_generators


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
    """승인 대상 객체의 현재 위치·카테고리입니다."""

    object_idx: int
    category: str | None = None
    bbox: BoundingBox


class ApprovalSku(_CamelModel):
    """승인 대상 객체에 매핑된 SKU입니다."""

    sku_id: int
    sku_code: str
    product_name: str
    image_url: str | None = None


class ApprovalActions(_CamelModel):
    """현재 상태에서 가능한 승인 작업입니다."""

    can_confirm: bool
    can_reject: bool


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
    xai_result: dict[str, typing.Any] | None = None
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
