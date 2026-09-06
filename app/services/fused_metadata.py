"""융합 임베딩에 넣을 SKU·객체 메타데이터를 결정적으로 문자열화합니다."""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from typing import Any

from app.core import catalog_spec

_SKU_ATTRIBUTE_FIELDS = {"brand", "selling_price"}


def build_metadata_text(
    *,
    category: str | None,
    attributes: Mapping[str, Any] | None,
    sub_category: str | None = None,
    product_name: str | None = None,
    brand: str | None = None,
    price: int | None = None,
) -> str:
    """스펙에 맞는 메타데이터만 고정 순서의 임베딩 텍스트로 변환합니다.

    SKU 색인과 연출 이미지 객체 검색이 같은 조립 규칙을 쓰도록, 누락값·
    허용값 밖 속성·정의되지 않은 카테고리는 제외합니다.
    """
    normalized_category = _normalize_text(category)
    if normalized_category not in catalog_spec.PRODUCT_CATEGORY:
        return ""

    lines = _build_head_lines(
        category=normalized_category,
        sub_category=sub_category,
        product_name=product_name,
        brand=brand,
        price=price,
    )
    normalized_attributes = _normalize_attributes(
        normalized_category,
        attributes or {},
    )
    lines.extend(
        f"{attribute}: {value}"
        for attribute, value in normalized_attributes.items()
    )
    return "\n".join(lines)


def _build_head_lines(
    *,
    category: str,
    sub_category: str | None,
    product_name: str | None,
    brand: str | None,
    price: int | None,
) -> list[str]:
    """SKU와 객체가 공유하는 상단 필드를 조립합니다."""
    lines = []
    if normalized_product_name := _normalize_text(product_name):
        lines.append(f"상품명: {normalized_product_name}")
    lines.append(f"카테고리: {category}")

    normalized_sub_category = _normalize_text(sub_category)
    if normalized_sub_category in catalog_spec.PRODUCT_CATEGORY[category]:
        lines.append(f"소분류: {normalized_sub_category}")

    if normalized_brand := _normalize_text(brand):
        lines.append(f"브랜드: {normalized_brand}")
    if price is not None and not isinstance(price, bool):
        lines.append(f"가격: {price}")
    return lines


def _normalize_attributes(
    category: str,
    attributes: Mapping[str, Any],
) -> dict[str, str]:
    """카테고리 스펙의 속성 순서와 허용값만 보존합니다."""
    normalized_input = {
        _normalize_text(key): _normalize_text(value)
        for key, value in attributes.items()
        if _normalize_text(key) and _normalize_text(value)
    }
    normalized_attributes = {}
    for attribute in catalog_spec.attribute_names(category):
        if attribute in _SKU_ATTRIBUTE_FIELDS:
            continue
        value = normalized_input.get(attribute)
        if value is None:
            continue
        allowed_values = catalog_spec.allowed_values(category, attribute)
        if not isinstance(allowed_values, list):
            continue
        normalized_allowed_values = {
            _normalize_text(str(allowed_value))
            for allowed_value in allowed_values
        }
        if value in normalized_allowed_values:
            normalized_attributes[attribute] = value
    return normalized_attributes


def _normalize_text(value: object) -> str:
    """문자열 입력의 공백과 유니코드 표현 차이를 제거합니다."""
    if not isinstance(value, str):
        return ""
    return unicodedata.normalize("NFC", value.strip())
