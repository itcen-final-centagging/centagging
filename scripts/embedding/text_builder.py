"""sku.json 항목 -> 텍스트 임베딩용 문자열.

sku_catalog.text_embedding 컬럼 주석대로 "상품명·카테고리·속성·대표 특징"을
근거로 삼는다. 순수 함수만 두고 API·DB 호출은 하지 않는다.
"""

from __future__ import annotations

from typing import Any


def build_embedding_text(sku: dict[str, Any]) -> str:
    """SKU 1건을 임베딩에 넣을 한 덩어리 텍스트로 만든다.

    Args:
        sku: data/catalog/answer/sku.json의 항목 1건입니다.
            (sku_id, sku_code, product_name, category, sub_category,
            key_features, attributes)

    Returns:
        상품명 -> 카테고리 -> 속성 -> 대표 특징 순으로 이어붙인 텍스트입니다.
    """
    lines: list[str] = [sku["product_name"]]

    category_line = f"카테고리: {sku['category']}"
    if sku.get("sub_category"):
        category_line += f" > {sku['sub_category']}"
    lines.append(category_line)

    attributes = sku.get("attributes") or {}
    if attributes:
        attr_text = ", ".join(f"{key}: {value}" for key, value in attributes.items())
        lines.append(f"속성: {attr_text}")

    key_features = sku.get("key_features") or []
    if key_features:
        lines.append("특징: " + " ".join(key_features))

    return "\n".join(lines)
