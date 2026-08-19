from __future__ import annotations

from typing import Any

# has_X 형태의 속성을 자연스러운 한국어 명사로 변환합니다.
_HAS_ATTR_NOUN: dict[str, str] = {
    "has_legs": "다리",
    "has_wheels": "바퀴",
    "has_drawer": "서랍",
    "has_armrest": "팔걸이",
    "has_backrest": "등받이",
    "has_storage": "수납공간",
    "has_headboard": "헤드보드",
    "has_frame": "프레임",
    "has_mirror": "거울",
    "has_stool": "스툴",
    "has_headrest": "헤드레스트",
}

# 일반 속성의 영어 key를 검색어와 유사한 한국어 표현으로 변환합니다.
_ATTR_LABEL: dict[str, str] = {
    "color": "색상",
    "style": "스타일",
    "pattern": "패턴",
    "material": "소재",
    "size": "사이즈",
    "wood_tone": "우드톤",
    "frame_material": "프레임 소재",
    "door_type": "도어 형태",
    "storage_type": "수납 형태",
    "mattress_type": "매트리스 종류",
    "firmness": "경도",
    "thickness": "두께",
    "features": "특징",
    "bed_type": "침대 종류",
    "frame_type": "하부 형태",
    "head_type": "헤드 형태",
    "base_type": "받침 형태",
    "product_type": "구성",
    "shape": "형태",
    "chair_type": "의자 종류",
    "drawer_count": "서랍",
    "sofa_type": "소파 종류",
    "shelf_type": "선반 종류",
    "shelf_count": "선반",
    "top_material": "상판 소재",
    "leg_type": "다리 형태",
    "seating_capacity": "인승",
    "tv_stand_type": "TV장 종류",
    "length": "길이",
    "level_count": "단수",
    "installation_type": "설치 방식",
    "wardrobe_type": "옷장 종류",
    "layout_type": "배치",
    "mobility_type": "이동 방식",
    "storage_features": "수납 특징",
    "vanity_type": "화장대 종류",
}


def _describe_attribute(key: str, value: Any) -> str:
    """속성을 임베딩에 적합한 자연스러운 한국어 구절로 변환합니다.

    일반 속성은 "color: 화이트" → "색상 화이트"처럼 변환하고,
    has_X 속성은 "has_mirror: 있음" → "거울 있음"처럼 변환합니다.
    매핑되지 않은 속성은 원래 값을 그대로 사용합니다.
    """
    noun = _HAS_ATTR_NOUN.get(key)
    if noun is not None:
        if value in ("있음", "없음"):
            return f"{noun} {value}"
        return f"{value} {noun}"

    label = _ATTR_LABEL.get(key)
    if label is None:
        return str(value)
    return f"{label} {value}"


def build_embedding_text(sku: dict[str, Any]) -> str:
    """SKU 1건을 임베딩에 사용할 텍스트로 변환합니다.

    상품명 → 카테고리 → 속성 → 대표 특징 순서로 구성합니다.
    """
    attributes = sku.get("attributes") or {}
    # 값이 없는 속성은 임베딩 텍스트에서 제외합니다.
    # 예: "wood_tone: None" → 제외
    clean_attributes = {
        key: value
        for key, value in attributes.items()
        if value is not None and str(value).strip() != ""
    }

    lines: list[str] = [sku["product_name"]]

    category_line = f"카테고리: {sku['category']}"
    if sku.get("sub_category"):
        category_line += f" > {sku['sub_category']}"
    lines.append(category_line)

    if clean_attributes:
        attr_text = ", ".join(
            _describe_attribute(key, value) for key, value in clean_attributes.items()
        )
        lines.append(f"속성: {attr_text}")

    key_features = sku.get("key_features") or []
    if key_features:
        lines.append("특징: " + " ".join(key_features))

    return "\n".join(lines)
