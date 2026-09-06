"""가구 속성 추출 결과의 허용값 구성과 검증을 제공합니다."""

import unicodedata

from app.core import catalog_spec
from app.schemas.furniture_attribute import FurnitureAttributeResult

HAS_ATTRIBUTE_VALUES = ["있음", "없음", "모름"]
VISUAL_COMMON_ATTRIBUTES = ("color", "style", "pattern")

CATEGORY_CLASSIFICATION_ATTRIBUTES = {
    ("침대", "bed_type"),
    ("매트리스", "mattress_type"),
    ("소파", "sofa_type"),
    ("서랍·수납장", "storage_type"),
    ("거실장·TV장", "tv_stand_type"),
    ("선반", "shelf_type"),
    ("진열장·책장", "storage_type"),
    ("의자", "chair_type"),
    ("행거·옷장", "wardrobe_type"),
    ("화장대·콘솔", "vanity_type"),
}

ATTRIBUTE_DISPLAY_LABELS = {
    "base_type": "구조",
    "bed_type": "침대 유형",
    "chair_type": "유형",
    "color": "색상",
    "door_type": "구조",
    "drawer_count": "서랍 구성",
    "features": "기능",
    "firmness": "쿠션감",
    "frame_material": "프레임 소재",
    "frame_type": "프레임 구조",
    "has_armrest": "팔걸이",
    "has_backrest": "등받이",
    "has_drawer": "서랍",
    "has_frame": "프레임",
    "has_headboard": "헤드보드",
    "has_headrest": "헤드레스트",
    "has_legs": "다리",
    "has_mirror": "거울",
    "has_storage": "수납공간",
    "has_stool": "스툴",
    "has_wheels": "바퀴",
    "head_type": "헤드 형태",
    "installation_type": "설치 방식",
    "layout_type": "배치",
    "leg_type": "다리 구조",
    "length": "길이",
    "level_count": "구성",
    "material": "소재",
    "mattress_type": "매트리스 유형",
    "mobility_type": "구조",
    "pattern": "패턴",
    "product_type": "제품 구성",
    "seating_capacity": "사용 규모",
    "shape": "형태",
    "shelf_count": "선반 구성",
    "shelf_type": "유형",
    "size": "규격",
    "sofa_type": "소파 유형",
    "storage_features": "수납 구성",
    "storage_type": "유형",
    "style": "스타일",
    "thickness": "두께",
    "top_material": "상판 소재",
    "tv_stand_type": "거실장 유형",
    "vanity_type": "화장대 유형",
    "wardrobe_type": "유형",
    "wood_tone": "색감",
}

ATTRIBUTE_VALUE_DISPLAY_LABELS = {
    "방수커버": "방수 커버",
    "게이밍의자": "게이밍 의자",
    "인테리어의자": "인테리어 의자",
    "원형베이스": "원형 베이스",
    "학생·사무용의자": "학생·사무용 의자",
    "유리도어": "유리 도어",
}

HAS_ATTRIBUTE_SUBJECTS = {
    "has_armrest": "팔걸이가",
    "has_backrest": "등받이가",
    "has_drawer": "서랍이",
    "has_frame": "프레임이",
    "has_headboard": "헤드보드가",
    "has_headrest": "헤드레스트가",
    "has_legs": "다리가",
    "has_mirror": "거울이",
    "has_storage": "수납공간이",
    "has_stool": "스툴이",
    "has_wheels": "바퀴가",
}

ATTRIBUTE_DESCRIPTOR_TEMPLATES = {
    "drawer_count": "{value} 서랍 구성",
    "installation_type": "{value} 설치 방식",
    "layout_type": "{value} 배치",
    "level_count": "{value} 구성",
    "shelf_count": "{value} 선반 구성",
    "thickness": "두께 {value}",
    "wood_tone": "{value}",
}

CATEGORY_ATTRIBUTE_DESCRIPTOR_TEMPLATES = {
    ("화장대·콘솔", "storage_type"): "{value} 수납 구조",
}

ATTRIBUTE_VALUE_DESCRIPTORS = {
    ("product_type", "프레임만"): "프레임 단독 구성",
    ("product_type", "프레임+매트리스"): "프레임·매트리스 구성",
    ("storage_features", "서랍 포함"): "서랍이 포함된 수납 구성",
    ("storage_features", "선반 포함"): "선반이 포함된 수납 구성",
    ("storage_features", "수납 없음"): "별도 수납이 없는 구조",
}


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


def build_evidence_descriptors(
    category: str,
    attributes: dict[str, str],
) -> list[str]:
    """카테고리별 객체 속성을 사용자용 근거 문구로 변환합니다."""
    schema = build_allowed_attribute_schema(category)
    attribute_groups = schema["attributes"]
    if not isinstance(attribute_groups, dict):
        return []

    category_attributes = attribute_groups.get("category_specific", {})
    if not isinstance(category_attributes, dict):
        return []

    visually_verifiable_attributes = set(
        catalog_spec.visual_attribute_names(category)
    )
    descriptors: list[str] = []
    for key in category_attributes:
        if (category, key) in CATEGORY_CLASSIFICATION_ATTRIBUTES:
            continue
        if key not in visually_verifiable_attributes:
            continue

        value = attributes.get(key)
        if not value or value == "모름":
            continue
        if key.startswith("has_") and value == "없음":
            continue

        descriptors.append(_format_evidence_descriptor(category, key, value))

    return descriptors


def _format_evidence_descriptor(category: str, key: str, value: str) -> str:
    """속성값과 이름이 중복되지 않는 자연스러운 근거 표현을 만듭니다."""
    label = ATTRIBUTE_DISPLAY_LABELS.get(key, key.replace("_", " "))
    display_value = ATTRIBUTE_VALUE_DISPLAY_LABELS.get(value, value)
    descriptor = f"{display_value} {label}"
    value_descriptor = ATTRIBUTE_VALUE_DESCRIPTORS.get((key, value))
    template = CATEGORY_ATTRIBUTE_DESCRIPTOR_TEMPLATES.get(
        (category, key)
    ) or ATTRIBUTE_DESCRIPTOR_TEMPLATES.get(key)

    if key.startswith("has_"):
        subject = HAS_ATTRIBUTE_SUBJECTS.get(key, f"{label}이")
        state = "있는" if value == "있음" else "없는"
        descriptor = f"{subject} {state} 구조"
    elif key == "leg_type":
        suffix = "구조" if value in {"4다리", "원형베이스"} else "다리 구조"
        descriptor = f"{display_value} {suffix}"
    elif value_descriptor is not None:
        descriptor = value_descriptor
    elif template is not None:
        descriptor = template.format(value=display_value)

    return descriptor
