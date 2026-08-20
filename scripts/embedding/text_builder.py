"""sku.json 항목 -> 텍스트 임베딩용 문자열. (baseline, 버전 1)

sku_catalog.text_embedding 컬럼 주석대로 "상품명·카테고리·속성·대표 특징"을
근거로 삼는다. 순수 함수만 두고 API·DB 호출은 하지 않는다.

이 파일은 실험 비교용 baseline 원본입니다. noise_removal/natural_attribute_phrasing
이전, 가장 처음 버전 그대로입니다 — attributes 값이 None이어도 걸러내지 않고
"key: None" 형태로 그대로 이어붙입니다.

baseline 지표를 다시 측정해야 할 때만 이 파일 내용을 scripts/embedding/text_builder.py에
그대로 덮어쓰고, 612건 전체를 재임베딩한 뒤 검색 테스트를 돌리세요. 테스트가 끝나면
반드시 현재 버전(noise_removal + natural_attribute_phrasing)으로 되돌리고 다시
재임베딩해야 합니다 — 이 파일 자체를 그대로 두고 쓰면 안 됩니다.
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
