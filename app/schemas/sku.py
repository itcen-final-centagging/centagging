"""신규 SKU 등록 API의 요청·응답 스키마입니다."""

import datetime
import typing

import pydantic

SkuImageType = typing.Literal["MAIN", "ANGLE", "DETAIL", "STYLING"]


class MetadataExtractResponse(pydantic.BaseModel):
    """AI가 추출한 메타데이터 응답입니다."""

    category: str | None = None
    sub_category: str | None = None
    space: str | None = None
    attributes: dict[str, typing.Any] = pydantic.Field(default_factory=dict)


class SkuCreateResponse(pydantic.BaseModel):
    """신규 SKU 저장 응답입니다."""

    sku_id: int
    sku_code: str
    product_name: str
    main_image_url: str


class SkuImageUploadItem(pydantic.BaseModel):
    """기존 SKU에 새로 연결한 이미지 1건입니다."""

    sku_image_id: int
    image_url: str
    image_type: SkuImageType


class SkuImageBatchCreateResponse(pydantic.BaseModel):
    """기존 SKU 이미지 일괄 추가 응답입니다."""

    sku_id: int
    sku_code: str
    images: list[SkuImageUploadItem]


class SkuCatalogItem(pydantic.BaseModel):
    """카탈로그 목록의 SKU 한 건입니다."""

    sku_id: int
    sku_code: str
    product_name: str
    brand: str | None = None
    price: int | None = None
    space: str | None = None
    category: str | None = None
    sub_category: str | None = None
    attributes: dict[str, typing.Any] = pydantic.Field(default_factory=dict)
    main_image_url: str | None = None
    created_at: datetime.datetime


class SkuCatalogListResponse(pydantic.BaseModel):
    """전체 카탈로그 목록 응답입니다."""

    items: list[SkuCatalogItem]


class SkuCatalogFilters(pydantic.BaseModel):
    """카탈로그 목록 조회에 적용할 필터입니다."""

    category: str | None = None
    sub_category: str | None = None
    color: str | None = None
    style: str | None = None
    pattern: str | None = None
    q: str | None = None


class SkuCatalogFilterOptions(pydantic.BaseModel):
    """카탈로그 목록 필터 드롭다운의 선택지입니다."""

    categories: list[str]
    sub_categories_by_category: dict[str, list[str]]
    colors: list[str]
    styles: list[str]
    pattern: list[str]
