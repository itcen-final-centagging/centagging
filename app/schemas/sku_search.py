"""SKU 키워드 검색 API 스키마입니다."""

import typing

from pydantic import BaseModel, Field


class SkuSearchItem(BaseModel):
    """SKU 검색 결과 한 건입니다."""

    sku_code: str
    product_name: str
    category: str | None
    sub_category: str | None
    image_url: str | None
    brand: str | None
    price: int | None
    similarity_score: float
    # 승인(ACTIVE)된 tagging_result.vlm_mood를 매 조회 시 다시 모아 채운
    # 값입니다. 별도 컬럼이 아니라 항상 최신 승인 상태를 반영합니다.
    space_moods: list[str] = Field(default_factory=list)
    style_tags: list[str] = Field(default_factory=list)


class SkuSearchData(BaseModel):
    """SKU 검색 결과 목록입니다."""

    skus: list[SkuSearchItem]


class SkuSearchResponse(BaseModel):
    """SKU 검색 성공 응답입니다."""

    status: typing.Literal["success"] = "success"
    data: SkuSearchData


class SkuDetailData(BaseModel):
    """SKU 상세 정보입니다. attrs는 카테고리별 속성을 그대로 담습니다."""

    sku_id: int
    sku_code: str
    product_name: str
    brand: str | None
    price: int | None
    category: str | None
    sub_category: str | None
    attrs: dict[str, typing.Any]
    image_url: str | None
    sku_image_id: int | None
    # 승인(ACTIVE)된 tagging_result.vlm_mood를 매 조회 시 다시 모아 채운
    # 값입니다. 별도 컬럼이 아니라 항상 최신 승인 상태를 반영합니다.
    space_moods: list[str] = Field(default_factory=list)
    style_tags: list[str] = Field(default_factory=list)


class SkuDetailResponse(BaseModel):
    """SKU 상세 조회 성공 응답입니다."""

    status: typing.Literal["success"] = "success"
    data: SkuDetailData
