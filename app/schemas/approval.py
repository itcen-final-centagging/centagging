"""승인 요청 API의 요청·응답 스키마입니다.

명세(``myfolder/승인요청_API_명세 (1).md``)가 camelCase JSON 계약을
요구하므로, 모든 모델이 snake_case 필드에 camelCase 별칭을 자동으로
붙이는 ``_CamelModel``을 상속합니다.
"""

import datetime
import typing

import pydantic
from pydantic import alias_generators


class _CamelModel(pydantic.BaseModel):
    """필드를 camelCase로 직렬화하는 공통 베이스입니다."""

    model_config = pydantic.ConfigDict(
        alias_generator=alias_generators.to_camel,
        populate_by_name=True,
    )


class BoundingBox(_CamelModel):
    """0~1000 정규화 좌표의 바운딩 박스입니다."""

    xmin: int
    ymin: int
    xmax: int
    ymax: int


class XaiResult(_CamelModel):
    """루브릭 채점 결과입니다. ``match_source``가 SEARCH면 항상 없습니다."""

    structure: int
    color: int
    detail: int
    context: int
    total: int
    verdict: typing.Literal["MATCH", "REVIEW", "REJECT"]
    reason: str


class ApprovalListItem(_CamelModel):
    """승인 요청 목록의 행 1건입니다.

    탐지 객체(``detected_object``) 단위로 한 행이 하나의 객체-SKU 매칭
    승인 요청을 나타냅니다.
    """

    request_id: int
    status: typing.Literal["PENDING", "ACTIVE", "REJECTED", "NO_SKU"]
    requested_at: datetime.datetime
    requested_by_name: typing.Optional[str] = None
    reviewed_at: typing.Optional[datetime.datetime] = None
    reviewed_by_name: typing.Optional[str] = None
    scene_image_id: int
    origin_name: str
    object_id: int
    category: typing.Optional[str] = None
    sub_category: typing.Optional[str] = None
    crop_url: typing.Optional[str] = None
    sku_code: typing.Optional[str] = None
    product_name: typing.Optional[str] = None
    similarity_score: typing.Optional[float] = None
    similarity_grade: typing.Optional[typing.Literal["상", "중", "하"]] = None


class ApprovalListResponse(_CamelModel):
    """승인 요청 목록 조회 응답입니다."""

    items: list[ApprovalListItem]


class ApprovalSceneImage(_CamelModel):
    """승인 요청 상세에 포함되는 연출 이미지 정보입니다."""

    scene_image_id: int
    image_url: str
    origin_name: str
    mime_type: str
    file_size: int
    width_px: int
    height_px: int
    created_at: datetime.datetime


class ApprovalObject(_CamelModel):
    """승인 요청 상세의 탐지 객체 정보입니다."""

    object_id: int
    category: typing.Optional[str] = None
    sub_category: typing.Optional[str] = None
    confidence: float
    bbox: BoundingBox
    crop_url: typing.Optional[str] = None
    has_embedding: bool
    mood_summary: typing.Optional[str] = None
    mood_tags: list[str] = pydantic.Field(default_factory=list)
    attributes: dict[str, typing.Any] = pydantic.Field(default_factory=dict)


class ApprovalSku(_CamelModel):
    """승인 요청 상세에 포함되는 매칭 SKU 정보입니다."""

    sku_id: int
    sku_code: str
    product_name: str
    brand: typing.Optional[str] = None
    price: typing.Optional[int] = None
    attributes: dict[str, typing.Any] = pydantic.Field(default_factory=dict)


class ApprovalActions(_CamelModel):
    """프론트가 버튼 활성화 여부를 판단할 때 쓰는 서버 판정입니다."""

    can_confirm: bool
    can_reject: bool


class ApprovalDetailResponse(_CamelModel):
    """승인 요청 상세 조회 응답입니다.

    요청 1건 = 객체-SKU 매칭(``tagging_result``) 1건이라 목록과 달리
    래핑 없이 매칭 정보를 최상위 필드로 바로 내려줍니다. ``status``가
    ``NO_SKU``면 매칭되는 ``tagging_result``가 없어 ``result_id``/``sku``/
    ``match_source`` 등이 전부 ``null``입니다.
    """

    request_id: int
    status: typing.Literal["PENDING", "ACTIVE", "REJECTED", "NO_SKU"]
    requested_by_name: typing.Optional[str] = None
    requested_at: datetime.datetime
    reviewed_by_name: typing.Optional[str] = None
    reviewed_at: typing.Optional[datetime.datetime] = None
    reject_reason: typing.Optional[str] = None
    result_id: typing.Optional[int] = None
    scene_image: ApprovalSceneImage
    object: ApprovalObject
    sku: typing.Optional[ApprovalSku] = None
    match_source: typing.Optional[typing.Literal["RECOMMEND", "SEARCH"]] = None
    match_rank: typing.Optional[int] = None
    similarity_score: typing.Optional[float] = None
    similarity_grade: typing.Optional[typing.Literal["상", "중", "하"]] = None
    matched_sku_image_url: typing.Optional[str] = None
    xai_result: typing.Optional[XaiResult] = None
    actions: ApprovalActions


class RejectRequest(_CamelModel):
    """승인 요청 반려 요청 본문입니다."""

    reject_reason: str = pydantic.Field(default="", max_length=255)


class ConfirmCreatedSkuImage(_CamelModel):
    """승인 확정 시 새로 등록된 SKU 이미지 1건입니다."""

    sku_image_id: int
    sku_id: int
    sku_code: str
    image_type: str
    indexed: bool


class ConfirmResponse(_CamelModel):
    """승인 확정 응답입니다. 요청 1건 = 객체 1건이라 등록 결과도 0/1건입니다."""

    request_id: int
    status: typing.Literal["ACTIVE"]
    reviewed_by_name: typing.Optional[str] = None
    reviewed_at: datetime.datetime
    created_sku_image: typing.Optional[ConfirmCreatedSkuImage] = None
    skipped: bool


class RejectResponse(_CamelModel):
    """승인 요청 반려 응답입니다."""

    request_id: int
    status: typing.Literal["REJECTED"]
    reviewed_by_name: typing.Optional[str] = None
    reviewed_at: datetime.datetime
    reject_reason: str
