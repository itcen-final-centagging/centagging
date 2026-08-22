"""가구 속성 추출 결과의 허용값 구성과 검증을 제공합니다."""

import unicodedata

from app.core import catalog_spec
from app.schemas.furniture_attribute import FurnitureAttributeResult

HAS_ATTRIBUTE_VALUES = ["있음", "없음", "모름"]
VISUAL_COMMON_ATTRIBUTES = ("color", "style", "pattern")


def _normalize_text(value: str) -> str:
    """Gemini가 반환할 수 있는 유니코드 정규화 차이를 제거합니다."""
    return unicodedata.normalize("NFC", value.strip())


def build_allowed_attribute_schema(category: str) -> dict[str, object]:
    """Gemini에 전달할 카테고리별 속성 허용 규격을 생성합니다."""
    if category not in catalog_spec.PRODUCT_CATEGORY:
        raise ValueError(f"허용하지 않은 카테고리입니다. {category}")

    common_attributes = {
        attribute: catalog_spec.COMMON_ATTRIBUTE[attribute]
        for attribute in VISUAL_COMMON_ATTRIBUTES
    }

    category_attributes = {
        attribute: (
            HAS_ATTRIBUTE_VALUES if attribute.startswith("has_") else values
        )
        for attribute, values in catalog_spec.PRODUCT_ATTRIBUTE[
            category
        ].items()
    }

    return {
        "category": category,
        "sub_category_options": (catalog_spec.PRODUCT_CATEGORY[category]),
        "attributes": {
            "common": common_attributes,
            "category_specific": category_attributes,
        },
    }


def build_attribute_response_schema(
    category: str,
) -> dict[str, object]:
    """Gemini 속성 추출 응답에 사용할 고정 스키마를 구성합니다."""
    allowed_schema = build_allowed_attribute_schema(category)
    attribute_groups = allowed_schema["attributes"]
    if not isinstance(attribute_groups, dict):
        raise ValueError("속성 허용 규격이 올바르지 않습니다.")

    common_attributes = attribute_groups.get("common")
    category_attributes = attribute_groups.get("category_specific")
    if not isinstance(common_attributes, dict):
        raise ValueError("공통 속성 허용 규격이 올바르지 않습니다.")
    if not isinstance(category_attributes, dict):
        raise ValueError("카테고리 속성 허용 규격이 올바르지 않습니다.")
    allowed_attributes = {
        **common_attributes,
        **category_attributes,
    }

    attribute_properties = {
        attribute: {
            "type": "STRING",
            "enum": values,
        }
        for attribute, values in allowed_attributes.items()
    }

    return {
        "type": "OBJECT",
        "properties": {
            "category": {
                "type": "STRING",
                "enum": [category],
            },
            "sub_category": {
                "type": "STRING",
            },
            "attributes": {
                "type": "OBJECT",
                "properties": attribute_properties,
            },
            "vlm_mood": {
                "type": "OBJECT",
                "properties": {
                    "summary": {"type": "STRING"},
                    "tags": {
                        "type": "ARRAY",
                        "items": {"type": "STRING"},
                    },
                },
                "required": ["summary", "tags"],
            },
        },
        "required": ["category", "attributes", "vlm_mood"],
    }


def validate_attribute_result(
    expected_category: str, result: FurnitureAttributeResult
) -> FurnitureAttributeResult:
    """추출 결과가 카탈로그 속성 규격에 맞는지 검증합니다."""
    normalized_expected_category = _normalize_text(expected_category)
    normalized_result_category = _normalize_text(result.category)
    if normalized_result_category != normalized_expected_category:
        raise ValueError(
            "요청 카테고리와 추출 카테고리가 다릅니다: "
            f"{expected_category} != {result.category}"
        )

    schema = build_allowed_attribute_schema(expected_category)
    sub_category_options = schema["sub_category_options"]

    if not isinstance(sub_category_options, list):
        raise ValueError("소분류 허용 규격이 올바르지 않습니다.")

    normalized_sub_category_options = {
        _normalize_text(option): option for option in sub_category_options
    }
    normalized_sub_category = (
        _normalize_text(result.sub_category)
        if result.sub_category is not None
        else None
    )
    sub_category = (
        normalized_sub_category_options.get(normalized_sub_category)
        if normalized_sub_category is not None
        else None
    )

    normalized_attributes = normalize_attributes(
        expected_category, result.attributes
    )

    return result.model_copy(
        update={
            "category": expected_category,
            "sub_category": sub_category,
            "attributes": normalized_attributes,
        }
    )


def normalize_attributes(
    category: str, attributes: dict[str, str]
) -> dict[str, str]:
    """허용되지 않은 속성과 값을 제거하고 정규화합니다."""
    schema = build_allowed_attribute_schema(category)
    attribute_groups = schema["attributes"]

    if not isinstance(attribute_groups, dict):
        raise ValueError("속성 허용 규격이 올바르지 않습니다.")

    common_attributes = attribute_groups.get("common")
    catgegory_attributes = attribute_groups.get("category_specific")

    if not isinstance(common_attributes, dict):
        raise ValueError("공통 속성 규격이 올바르지 않습니다.")

    if not isinstance(catgegory_attributes, dict):
        raise ValueError("카테고리 속성 규격이 올바르지 않습니다.")

    allowed_attributes = {**common_attributes, **catgegory_attributes}

    normalized_attributes: dict[str, str] = {}

    for attribute, value in attributes.items():
        normalized_attribute = _normalize_text(attribute)
        normalized_value = _normalize_text(value)
        allowed_values = allowed_attributes.get(normalized_attribute)

        if not isinstance(allowed_values, list):
            continue

        normalized_allowed_values = {
            _normalize_text(str(allowed_value))
            for allowed_value in allowed_values
        }
        if normalized_value not in normalized_allowed_values:
            continue

        normalized_attributes[normalized_attribute] = normalized_value

    return normalized_attributes
