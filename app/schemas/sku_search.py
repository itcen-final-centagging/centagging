"""SKU 키워드 검색 API 스키마입니다."""

import typing

from pydantic import BaseModel


class SkuSearchItem(BaseModel):
    """SKU 검색 결과 한 건입니다."""

    sku_code: str
    product_name: str
    category: str | None
    sub_category: str | None


class SkuSearchData(BaseModel):
    """SKU 검색 결과와 페이지 정보입니다."""

    total_count: int
    page: int
    size: int
    items: list[SkuSearchItem]


class SkuSearchResponse(BaseModel):
    """SKU 검색 성공 응답입니다."""

    status: typing.Literal["success"] = "success"
    data: SkuSearchData

class SkuImageItem(BaseModel):
    """SKU 상품 이미지 정보입니다."""
    sku_image_id: int
    image_type: typing.Literal["MAIN", "ANGLE", "DETAIL", "STYLING"]
    image_url: str

class SkuDetailData(BaseModel):
    """SKU 상품 상세 정보입니다."""
    sku_code: str
    product_name: str
    category: str|None
    sub_category: str|None
    key_features: dict[str, typing.Any]
    description: str|None
    attrs: dict[str, typing.Any]
    images: list[SkuImageItem]


class SkuDetailResponse(BaseModel):
    status: typing.Literal["success"] = "success"
    data: SkuDetailData
