"""SKU row 검증

`원본 -> 정규화 -> 검증 -> Ground Truth` 순서에서 마지막 관문이다.
원본에 적혀 있다는 이유만으로 값을 통과시키지 않고, 여기서 한 번 더
catalog_spec 기준으로 확인한다.

검증은 값을 고치지 않는다. 문제를 찾아 목록으로 돌려줄 뿐이다.
자동 보정을 하면 원인을 못 찾기 때문이다.
"""

from __future__ import annotations

import pathlib
import sys
from typing import Any

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core import catalog_spec


def validate_row(row: dict[str, Any]) -> list[str]:
    """SKU row 1건을 검사한다.
    catalog_spec에 정의된 값만 Ground Truth에 들어가도록 마지막으로 막는 것"""
    errors: list[str] = []
    category = row.get("category")

    if category not in catalog_spec.PRODUCT_ATTRIBUTE:
        return [f"정의되지 않은 대분류: {category!r}"]

    fixed_subs = catalog_spec.PRODUCT_CATEGORY[category]
    if row.get("sub_category") not in fixed_subs:
        errors.append(f"소분류 미정의: {row.get('sub_category')!r}")

    if not row.get("product_name"):
        errors.append("product_name이 비어 있음")

    if not isinstance(row.get("key_features"), list):
        errors.append("key_features 형식 오류")

    schema_keys = catalog_spec.attribute_names(category)

    for key, value in (row.get("attributes") or {}).items():
        # 현재 카테고리에서 사용할 수 있는 속성 목록 중 존재하지 않는 속성 검사
        if key not in schema_keys:
            errors.append(f"스키마 외 속성: {key}")
            continue
        # null 검사
        if value is None:
            errors.append(f"{key} 값이 null (null은 저장하지 않는다)")
            continue
        # 허용값 검사
        allowed = catalog_spec.allowed_values(category, key)
        if allowed and value not in allowed:
            errors.append(f"{key} 허용값 외: {value!r}")

    return errors


def validate_rows(rows: list[dict]) -> dict[str, Any]:
    """전체 SKU 목록을 검사하고 통계를 함께 돌려준다. """
    errors: dict[str, list[str]] = {}
    filled = 0
    expected = 0
    missing: dict[str, int] = {}
    seen: dict[str, int] = {}
    duplicates: list[str] = []

    for row in rows:
        row_errors = validate_row(row)
        if row_errors:
            errors[row["sku_code"]] = row_errors

        code = row["sku_code"]
        seen[code] = seen.get(code, 0) + 1
        if seen[code] == 2:
            duplicates.append(code)


        if row.get("category") in catalog_spec.PRODUCT_ATTRIBUTE:
            schema_keys = catalog_spec.attribute_names(row["category"])
            expected += len(schema_keys)
            filled += len(row["attributes"])
            for key in schema_keys:
                if key not in row["attributes"]:
                    missing[key] = missing.get(key, 0) + 1

    return {
        "errors": errors,
        "duplicate_codes": duplicates,
        "fill_rate": (filled / expected) if expected else 0.0,
        "filled": filled,
        "expected": expected,
        "missing": dict(
            sorted(missing.items(), key=lambda item: -item[1])
        ),
    }
