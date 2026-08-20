"""관리자 제품 이미지 등록 요청의 요청·응답 스키마입니다."""

import datetime
import typing

import pydantic

SubmissionStatus = typing.Literal[
    "DRAFT",
    "PENDING",
    "APPROVED",
    "REJECTED",
]
SubmissionTargetType = typing.Literal["EXISTING", "NEW"]
SkuImageType = typing.Literal["MAIN", "ANGLE", "DETAIL", "STYLING"]


class ProductImageSubmissionItem(pydantic.BaseModel):
    """일괄 업로드 큐의 제품 이미지 등록 요청 한 건입니다."""

    submission_id: int
    status: SubmissionStatus
    target_type: SubmissionTargetType | None = None
    image_url: str
    image_type: SkuImageType
    target_sku_code: str | None = None
    target_product_name: str | None = None
    proposed_sku_code: str | None = None
    proposed_product_name: str | None = None
    requested_by_name: str
    requested_at: datetime.datetime
    submitted_at: datetime.datetime | None = None
    reviewed_by_name: str | None = None
    reviewed_at: datetime.datetime | None = None
    reject_reason: str | None = None
    final_sku_id: int | None = None
    final_sku_image_id: int | None = None


class ProductImageSubmissionDetail(ProductImageSubmissionItem):
    """제품 이미지 등록 요청의 메타데이터를 포함한 상세입니다."""

    proposed_brand: str | None = None
    proposed_price: int | None = None
    proposed_category: str | None = None
    proposed_sub_category: str | None = None
    proposed_attributes: dict[str, typing.Any] = pydantic.Field(
        default_factory=dict
    )


class ProductImageSubmissionListResponse(pydantic.BaseModel):
    """상태와 권한 범위로 필터링한 등록 요청 목록입니다."""

    items: list[ProductImageSubmissionItem]


class ProductImageSubmissionBatchResponse(pydantic.BaseModel):
    """여러 업로드 파일로 만든 초안 요청 목록입니다."""

    items: list[ProductImageSubmissionItem]


class ConfigureProductImageSubmissionRequest(pydantic.BaseModel):
    """초안 요청을 기존 SKU 연결 또는 신규 SKU 정보로 구성합니다."""

    target_type: SubmissionTargetType
    target_sku_code: str | None = None
    proposed_sku_code: str | None = pydantic.Field(default=None, max_length=50)
    proposed_product_name: str | None = pydantic.Field(
        default=None, max_length=200
    )
    proposed_brand: str | None = pydantic.Field(default=None, max_length=100)
    proposed_price: int | None = pydantic.Field(default=None, ge=0)
    proposed_category: str | None = pydantic.Field(default=None, max_length=50)
    proposed_sub_category: str | None = pydantic.Field(
        default=None, max_length=50
    )
    proposed_attributes: dict[str, typing.Any] = pydantic.Field(
        default_factory=dict
    )
    image_type: SkuImageType = "MAIN"


class RejectProductImageSubmissionRequest(pydantic.BaseModel):
    """최종 관리자가 입력하는 반려 사유입니다."""

    reject_reason: str = pydantic.Field(min_length=1, max_length=255)
