"""가구 속성 추출 결과의 허용값 구성과 검증을 제공합니다."""

from app.core import catalog_spec
from app.schemas.furniture_attribute import FurnitureAttributeResult

HAS_ATTRIBUTE_VALUES = ["있음", "없음", "모름"]
VISUAL_COMMON_ATTRIBUTES = ("color", "style", "pattern")


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


def validate_attribute_result(
    expected_category: str, result: FurnitureAttributeResult
) -> FurnitureAttributeResult:
    """추출 결과가 카탈로그 속성 규격에 맞는지 검증합니다."""
    if result.category != expected_category:
        raise ValueError(
            "요청 카테고리와 추출 카테고리가 다릅니다: "
            f"{expected_category} != {result.category}"
        )

    schema = build_allowed_attribute_schema(expected_category)
    sub_category_options = schema["sub_category_options"]

    if not isinstance(sub_category_options, list):
        raise ValueError("소분류 허용 규격이 올바르지 않습니다.")

    sub_category = result.sub_category

    if sub_category is not None and sub_category not in sub_category_options:
        sub_category = None

    normalized_attributes = normalize_attributes(
        expected_category, result.attributes
    )

    return result.model_copy(
        update={
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
        allowed_values = allowed_attributes.get(attribute)

        if not isinstance(allowed_values, list):
            continue

        if value not in allowed_values:
            continue

        normalized_attributes[attribute] = value

    return normalized_attributes
