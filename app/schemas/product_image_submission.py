"""관리자 제품 이미지 등록 요청의 요청·응답 스키마입니다."""

import datetime
import typing
import uuid

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
    job_id: uuid.UUID | None = None
    target_sku_code: str | None = None
    target_product_name: str | None = None
    target_main_image_url: str | None = None
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


class ProductImageSubmissionCandidateSku(pydantic.BaseModel):
    """추천 당시 함께 제시됐던 후보 SKU 1건입니다.

    match_rank는 추천 후보 배열에서의 순번(1부터)이다. 검색으로 직접
    선택해 연결한 SKU가 후보 목록에 없으면 이 항목을 맨 앞에 끼워
    넣고 via_search=True, match_rank=0으로 표시한다.
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
    xai_common: str = ""
    xai_difference: str = ""
    via_search: bool = False


class ProductImageSubmissionDetail(ProductImageSubmissionItem):
    """제품 이미지 등록 요청의 메타데이터를 포함한 상세입니다."""

    proposed_brand: str | None = None
    proposed_price: int | None = None
    proposed_category: str | None = None
    proposed_sub_category: str | None = None
    target_brand: str | None = None
    target_price: int | None = None
    target_category: str | None = None
    target_sub_category: str | None = None
    proposed_attributes: dict[str, typing.Any] = pydantic.Field(
        default_factory=dict
    )
    target_attributes: dict[str, typing.Any] = pydantic.Field(
        default_factory=dict
    )
    candidates: list[ProductImageSubmissionCandidateSku] = pydantic.Field(
        default_factory=list
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
