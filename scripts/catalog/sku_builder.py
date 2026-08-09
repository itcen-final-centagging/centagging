"""확정 속성 + 옵션 -> SKU row 생성

이 단계에서는 VLM을 사용하지 않는다.
metadata_builder에서 확정된 상품 공통 속성과 product.json에 들어 있는 실제 옵션 정보를 조합해서 최종 SKU를 만든다.

    상품 1건
      ├─ 상품 공통 속성 (metadata_builder가 확정한 값)
      └─ 옵션 N개
              ├─ 옵션 색상 / 사이즈  (text_rules)
              └─ 옵션 규칙               (verified_attrs.json)
      -> 속성 조합이 같은 옵션은 하나로 합쳐 SKU가 된다

같은 상품에서 attributes 조합이 같으면 하나의 SKU로 합친다.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
from typing import Any

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core import catalog_spec
from scripts.catalog import text_rules as rules


def option_pair(option: dict) -> tuple[str, str]:
    """옵션의 1차/2차 텍스트를 공백 정리된 문자열 쌍으로 돌려준다."""
    return (
        str(option.get("first_option") or "").strip(),
        str(option.get("second_option") or "").strip(),
    )


def pick_color_text(first: str, second: str, spec: dict[str, Any] | None) -> str:
    """색상 판정에 쓸 텍스트를 고른다.

    기본값은 `2차 옵션 -> 1차 옵션`이다. 프레임 색과 제품 색이 한 줄에 같이
    적힌 상품만 verified_attrs.json에서 `color_text`로 규칙을 지정한다."""
    if not spec:
        return ""

    text = second if spec.get("field") == "second" else first
    # 선택한 텍스트에서 어느 부분을 사용할지 결정한다.
    take = spec.get("take")
    # "화이트_철제" → "철제"
    if take == "last_segment":
        return rules.last_segment(text, spec.get("separator", "_"))
    # "화이트(프레임)" → "화이트"
    if take == "before":
        return rules.text_before(text, spec.get("marker", ""))
    return text


def build_attributes(category: str, base_attributes: dict[str, Any], option: dict, option_spec: dict[str, Any],) -> dict[str, Any]:
    """옵션 1개의 attributes를 만든다.

    상품 공통값 -> 옵션 색상 -> 옵션 사이즈 -> 옵션 규칙 순으로 덮어쓰고,
    값이 없는 key는 제거한 뒤 catalog_spec 순서로 정렬한다."""
    attributes = dict(base_attributes)
    first, second = option_pair(option)
    schema_keys = catalog_spec.attribute_names(category)

    # 색상 - 옵션에서 뽑고, 못 뽑으면 상품 공통값을 그대로 둔다.
    color_spec = option_spec.get("color_text")
    if color_spec:
        color = rules.normalize_color(pick_color_text(first, second, color_spec))
    else:
        color = rules.normalize_color(second) or rules.normalize_color(first)
    if color is not None:
        attributes["color"] = color

    # 침구 사이즈 - size를 쓰는 카테고리만(first, second option에 침대는 사이즈가 있음)
    if "size" in schema_keys:
        size = (
            rules.normalize_bed_size(second)
            or rules.normalize_bed_size(first)
        )
        if size is not None:
            attributes["size"] = size

    # 옵션 규칙 - 헤드 유무, 소재, 우드톤처럼 옵션에서 갈리는 값
    text = f"{first} {second}"
    for rule in option_spec.get("option_rules") or []:
        if rule.get("keyword") and rule["keyword"] in text:
            attributes.update(rule.get("set") or {})

    return {
        key: attributes[key]
        for key in schema_keys
        if attributes.get(key) is not None
    }


def sku_code(category: str, goods_id: int, attributes: dict) -> str:
    """`카테고리코드-속성해시8` 형식의 SKU 코드를 만든다."""
    prefix = catalog_spec.CATEGORY_CODE.get(category, "SKU")
    identity = json.dumps(attributes, ensure_ascii=False, sort_keys=True)
    digest = hashlib.md5(f"{goods_id}|{identity}".encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:8].upper()}"


def build_skus(
    product: dict,
    category: str,
    sub_category: str | None,
    product_name: str,
    key_features: list[str],
    base_attributes: dict[str, Any],
    option_spec: dict[str, Any],
) -> list[dict]:
    """상품 1건을 SKU row 목록으로 만든다.

    Args:
        product: 크롤링한 product.json 딕셔너리입니다.
        category: 고정 대분류입니다.
        sub_category: 고정 소분류입니다.
        product_name: 정리된 상품명입니다.
        key_features: 상품 공통 특징 문장 목록입니다.
        base_attributes: 상품 공통으로 확정된 속성입니다.
        option_spec: 옵션 규칙과 색상 규칙입니다.

    Returns:
        sku row 목록입니다. sku_id는 아직 None입니다.
    """
    goods_id = product.get("goods_id")
    options = product.get("options") or [
        {"first_option": "", "second_option": ""}
    ]

    rows: list[dict] = []
    seen: set[str] = set()

    for option in options:
        attributes = build_attributes(
            category, base_attributes, option, option_spec
        )
        identity = json.dumps(attributes, ensure_ascii=False, sort_keys=True)
        if identity in seen:
            continue
        seen.add(identity)

        rows.append({
            "sku_id": None,  # 전체 취합 후 채번
            "sku_code": sku_code(category, goods_id, attributes),
            "product_name": product_name,
            "category": category,
            "sub_category": sub_category,
            "key_features": key_features,
            "attributes": attributes,
        })

    return rows
