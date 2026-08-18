"""원본 데이터 + 규칙으로 상품 메타데이터 초안을 생성한다.

처리 순서:

1. 원본 specifications / category_path / options
2. 상품명·옵션·설명 기반 규칙
3. 규칙으로 못 채운 값은 VLM 보조
4. 최종적으로도 확인할 수 없는 값은 None으로 남긴다.
5. 사람 검수는 별도의 CSV 검수 단계에서 수행한다.

각 속성은 {"value", "source", "confidence"} 형태로 관리한다.

사람 검수값은 이 모듈에서 처리하지 않는다.
최종 검수는 SKU 생성 후 CSV로 추출하여 None 값만 사람이 채우는 방식으로 수행한다.
"""

from __future__ import annotations

from typing import Any

from app.core import catalog_spec
from scripts.catalog import text_rules as rules


# VLM 결과의 confidence는 초안으로만 사용한다.
# VLM 결과가 자동 확정값으로 취급되지 않도록 상한을 둔다.
VLM_CONFIDENCE_CAP = 0.85


MATERIAL_ATTRS = {
    "material",
    "top_material",
    "frame_material",
}

COUNT_ATTRS = {
    "drawer_count",
    "level_count",
    "shelf_count",
}


SURFACE_MATERIALS = (
    "패브릭",
    "메쉬",
    "천연가죽",
    "인조가죽",
    "벨벳",
    "스웨이드",
    "라탄",
)

SURFACE_FIRST_CATEGORIES = {
    "소파",
    "의자",
}


EMPTY_SPEC_VALUES = {
    "",
    "-",
    "상세페이지 참조",
    "상세페이지참조",
    "상세페이지 참고",
    "상세기술서 참조",
    "상세기술서참조",
    "상품페이지 참조",
    "해당사항 없음",
    "해당없음",
    "별도표기",
    "상세설명 참조",
}


MATERIAL_CHUNK_LIMIT = 3


# 프로젝트 소분류를 속성값으로 직접 매핑할 수 있는 경우의 규칙.
SUBCATEGORY_ATTR_MAP: dict[str, tuple[str, dict[str, str]]] = {
    "의자": (
        "chair_type",
        {
            "인테리어의자": "인테리어의자",
            "스툴·벤치": "스툴·벤치",
            "빈백": "빈백",
            "안락의자": "안락의자",
            "흔들의자": "흔들의자",
            "학생·사무용의자": "학생·사무용의자",
            "게이밍의자": "게이밍의자",
            "바체어": "바체어",
            "발받침": "발받침",
        },
    ),
    "서랍·수납장": (
        "storage_type",
        {
            "서랍장": "서랍장",
            "수납장": "수납장",
            "캐비닛": "캐비닛",
            "주방수납장": "주방 수납장",
            "협탁": "협탁",
        },
    ),
    "진열장·책장": (
        "storage_type",
        {
            "책장": "책장",
            "매거진랙": "매거진랙",
        },
    ),
    "선반": (
        "shelf_type",
        {
            "벽선반": "벽선반",
            "스탠드선반": "스탠드선반",
            "앵글·조립식선반": "앵글·조립식선반",
        },
    ),
    "침대": (
        "product_type",
        {
            "침대프레임": "프레임만",
            "침대+메트리스": "프레임+매트리스",
        },
    ),
    "거실장·TV장": (
        "tv_stand_type",
        {
            "일반거실장": "일반형",
            "높은거실장·사이드보드": "높은형",
            "TV스탠드": "스탠드형",
        },
    ),
    "화장대·콘솔": (
        "vanity_type",
        {
            "일반화장대": "일반형",
            "수납화장대": "수납형",
            "좌식·미니화장대": "좌식형",
            "접이식화장대": "접이식",
            "콘솔": "콘솔형",
        },
    ),
}


def spec_value(product: dict, key: str) -> str | None:
    """specifications에서 실제 값만 반환한다."""
    value = (product.get("specifications") or {}).get(key)

    if value is None:
        return None

    value = str(value).strip()

    return None if value in EMPTY_SPEC_VALUES else value


def main_option(product: dict) -> dict:
    """대표 옵션을 반환한다."""
    options: list[dict] = product.get("options") or []

    for option in options:
        if option.get("is_main"):
            return option

    return options[0] if options else {}


def option_text(option: dict) -> str:
    """옵션 텍스트를 합친다."""
    return " ".join(
        str(option.get(key) or "").strip()
        for key in ("first_option", "second_option")
        if option.get(key)
    )


def source_texts(product: dict) -> dict[str, str]:
    """속성 추출에 사용할 원문을 구성한다."""
    ai_text = " ".join(
        str(value)
        for value in (product.get("ai_attributes") or {}).values()
    )

    return {
        "name": rules.clean_product_name(product.get("name")),
        "summary": product.get("summary") or "",
        "ai": ai_text,
        "option": option_text(main_option(product)),
        "spec_material": spec_value(product, "주요 소재") or "",
        "spec_component": spec_value(product, "구성품") or "",
        "spec_color": spec_value(product, "색상") or "",
        "spec_size": spec_value(product, "크기") or "",
        "spec_title": spec_value(product, "품명") or "",
    }


def resolve_category(
    product: dict,
) -> tuple[str | None, str | None, list[str]]:
    """category_path를 프로젝트의 대분류/소분류로 변환한다."""
    warnings: list[str] = []
    path = product.get("category_path") or []

    category = next(
        (
            catalog_spec.CATEGORY_MAP[node]
            for node in path
            if node in catalog_spec.CATEGORY_MAP
        ),
        None,
    )

    if category is None:
        return None, None, [
            f"category_path {path} 매핑 실패"
        ]

    fixed_subs = catalog_spec.PRODUCT_CATEGORY.get(category, [])

    sub_category = next(
        (
            node
            for node in path[2:]
            if node in fixed_subs
        ),
        None,
    )

    if sub_category is None:
        sub_category = (
            path[2]
            if len(path) > 2
            else None
        )

        warnings.append(
            f"sub_category {sub_category!r}가 "
            f"PRODUCT_CATEGORY['{category}'] 목록에 없음"
        )

    return category, sub_category, warnings


def material_hint(
    category: str,
    attribute: str,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """소재 속성별 우선 소재와 검색 영역을 반환한다."""
    if attribute == "frame_material":
        return (
            ("철제/스틸",),
            ("프레임", "다리", "각재", "스탠드", "포스트"),
        )

    if attribute == "top_material":
        return (
            (),
            ("상판", "탑"),
        )

    if category in SURFACE_FIRST_CATEGORIES:
        return (
            SURFACE_MATERIALS,
            ("마감재", "커버", "원단"),
        )

    return (), ()


def _put_if_absent(
    draft: dict[str, dict[str, Any]],
    key: str,
    value: Any,
    source: str,
    confidence: float,
) -> None:
    """값이 아직 없을 때만 추가한다."""
    if value is None:
        return

    if key in draft:
        return

    draft[key] = {
        "value": value,
        "source": source,
        "confidence": confidence,
    }


def _put_product_info_attrs(
    draft: dict[str, dict[str, Any]],
    product: dict,
) -> None:
    """상품 원본 필드에서 직접 기본 정보를 채운다."""
    _put_if_absent(
        draft,
        "brand",
        product.get("brand_name"),
        "product",
        1.0,
    )

    _put_if_absent(
        draft,
        "selling_price",
        product.get("selling_price"),
        "product",
        1.0,
    )


def _ordered_sources(
    texts: dict[str, str],
) -> list[tuple[str, str, float]]:
    """규칙 추출용 텍스트의 우선순위를 반환한다."""
    return [
        (
            "name",
            texts["name"],
            0.7,
        ),
        (
            "option",
            texts["option"],
            0.8,
        ),
        (
            "ai_attributes",
            f"{texts['summary']} {texts['ai']}",
            0.7,
        ),
        (
            "specification",
            f"{texts['spec_material']} "
            f"{texts['spec_component']}",
            0.8,
        ),
    ]


def _put_explicit_attrs(
    draft: dict[str, dict[str, Any]],
    texts: dict[str, str],
    category: str,
    sub_category: str | None,
) -> None:
    """원본에 직접 명시된 값을 채운다.

    color는 이미지/VLM으로 보완하지 않고,
    옵션 및 specification 원문에서만 추출한다.
    """
    # color는 규칙 기반으로만 처리한다.
    _put_if_absent(
        draft,
        "color",
        rules.normalize_color(texts["option"]),
        "option",
        0.9,
    )

    _put_if_absent(
        draft,
        "color",
        rules.normalize_color(texts["spec_color"]),
        "specification",
        0.9,
    )

    if not sub_category:
        return

    if category not in SUBCATEGORY_ATTR_MAP:
        return

    attr_key, mapping = SUBCATEGORY_ATTR_MAP[category]

    _put_if_absent(
        draft,
        attr_key,
        rules.normalize_enum(
            attr_key,
            texts["name"],
            catalog_spec.allowed_values(
                category,
                attr_key,
            ),
        ),
        "name",
        0.9,
    )

    _put_if_absent(
        draft,
        attr_key,
        mapping.get(sub_category),
        "category",
        0.95,
    )


def _put_keyword_attrs(
    draft: dict[str, dict[str, Any]],
    texts: dict[str, str],
) -> None:
    """상품명/요약 기반 속성을 채운다."""
    text = (
        f"{texts['name']} "
        f"{texts['summary']}"
    )

    _put_if_absent(
        draft,
        "style",
        rules.normalize_style(text),
        "name",
        0.7,
    )

    _put_if_absent(
        draft,
        "pattern",
        rules.normalize_pattern(
            f"{texts['name']} "
            f"{texts['spec_material']}"
        ),
        "name",
        0.7,
    )


def _put_schema_attr(
    draft: dict[str, dict[str, Any]],
    texts: dict[str, str],
    category: str,
    key: str,
) -> None:
    """속성 유형에 맞는 규칙으로 값을 채운다."""
    allowed = catalog_spec.allowed_values(
        category,
        key,
    )

    # 소재 계열
    if key in MATERIAL_ATTRS:
        prefer, focus_words = material_hint(
            category,
            key,
        )

        chunks = rules.material_chunks(
            texts["spec_material"]
        )

        _put_if_absent(
            draft,
            key,
            rules.normalize_material(
                texts["spec_material"],
                category,
                key,
                prefer=prefer,
                focus_words=focus_words,
            ),
            "specification",
            (
                0.9
                if len(chunks) <= MATERIAL_CHUNK_LIMIT
                else 0.75
            ),
        )

        return

    # 침구 사이즈
    if key == "size":
        _put_if_absent(
            draft,
            key,
            rules.normalize_bed_size(
                texts["option"]
            ),
            "option",
            0.9,
        )

        _put_if_absent(
            draft,
            key,
            rules.normalize_bed_size(
                texts["name"]
            ),
            "name",
            0.7,
        )

        return

    # 매트리스 두께
    if key == "thickness":
        _put_if_absent(
            draft,
            key,
            rules.normalize_thickness(
                texts["option"]
            ),
            "option",
            0.9,
        )

        _put_if_absent(
            draft,
            key,
            rules.normalize_thickness(
                texts["name"]
            ),
            "name",
            0.8,
        )

        return

    # 수량 계열
    if key in COUNT_ATTRS:
        for source, text in (
            ("name", texts["name"]),
            ("option", texts["option"]),
        ):
            _put_if_absent(
                draft,
                key,
                rules.normalize_level_count(
                    text,
                    allowed,
                ),
                source,
                0.85,
            )

        return

    # 좌석 수
    if key == "seating_capacity":
        _put_if_absent(
            draft,
            key,
            rules.normalize_seating_capacity(
                texts["name"],
                allowed,
            ),
            "name",
            0.8,
        )

        return

    # 거실장 길이
    if key == "length":
        dimensions = (
            rules.parse_dimensions(
                texts["spec_size"]
            )
            or {}
        )

        _put_if_absent(
            draft,
            key,
            rules.normalize_length(
                dimensions.get("width")
            ),
            "derived",
            0.85,
        )

        return

    # boolean 속성
    if key in rules.BOOLEAN_KEYWORDS:
        for source, text, _confidence in _ordered_sources(
            texts
        ):
            _put_if_absent(
                draft,
                key,
                rules.normalize_boolean(
                    key,
                    text,
                ),
                source,
                0.6,
            )

        return

    # 일반 enum 속성
    for source, text, confidence in _ordered_sources(
        texts
    ):
        _put_if_absent(
            draft,
            key,
            rules.normalize_enum(
                key,
                text,
                allowed,
            ),
            source,
            confidence,
        )


def build_draft(
    product: dict,
    category: str,
    sub_category: str | None,
) -> dict[str, dict[str, Any]]:
    """원본과 규칙으로 메타데이터 초안을 생성한다.

    이 단계에서는 VLM이나 사람 검수값을 사용하지 않는다.

    규칙으로 확인할 수 없는 속성은 draft에 들어가지 않는다.
    이후 VLM 보조 단계에서 미확정 속성만 추가한다.
    """
    texts = source_texts(product)

    draft: dict[str, dict[str, Any]] = {}

    # 상품 원본 정보
    _put_product_info_attrs(
        draft,
        product,
    )

    # 원본에 직접 명시된 값
    _put_explicit_attrs(
        draft,
        texts,
        category,
        sub_category,
    )

    # 상품명/요약 기반 값
    _put_keyword_attrs(
        draft,
        texts,
    )

    # 카탈로그 스키마 속성
    for key in catalog_spec.attribute_names(
        category
    ):
        if key not in draft:
            _put_schema_attr(
                draft,
                texts,
                category,
                key,
            )

    return draft


def apply_vlm(
    draft: dict[str, dict[str, Any]],
    vlm_attrs: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """규칙으로 채우지 못한 속성에만 VLM 값을 추가한다.

    이미 규칙으로 값이 존재하는 속성은 VLM 결과로 덮어쓰지 않는다.

    VLM에서 확인하지 못한 속성은 추가하지 않으며,
    최종 SKU 생성 단계에서 None으로 취급할 수 있다.
    """
    merged = dict(draft)

    for key, payload in (vlm_attrs or {}).items():
        # 규칙으로 이미 값이 있으면 VLM이 덮어쓰지 않는다.
        if key in merged:
            continue

        value = (
            payload.get("value")
            if isinstance(payload, dict)
            else payload
        )

        if value is None:
            continue

        confidence = (
            payload.get("confidence", 0.5)
            if isinstance(payload, dict)
            else 0.5
        )

        merged[key] = {
            "value": value,
            "source": "vlm",
            "confidence": min(
                float(confidence),
                VLM_CONFIDENCE_CAP,
            ),
            "reason": (
                payload.get("reason")
                if isinstance(payload, dict)
                else None
            ),
        }

    return merged


def build_key_features(
    product: dict,
) -> list[str]:
    """검색/임베딩에 사용할 짧은 특징 목록을 생성한다."""
    features: list[str] = []

    for value in (
        product.get("ai_attributes") or {}
    ).values():
        features.extend(
            line.strip()
            for line in str(value).split("\n")
            if line.strip()
        )

    material = spec_value(
        product,
        "주요 소재",
    )

    if material and len(material) <= 60:
        features.append(
            material.replace("\n", " ")
        )

    component = spec_value(
        product,
        "구성품",
    )

    if component and len(component) <= 60:
        features.append(
            f"구성품: {component}"
        )

    size = rules.parse_dimensions(
        spec_value(product, "크기")
    )

    if size:
        features.append(
            f"크기 "
            f"W{size['width']} x "
            f"D{size['depth']} x "
            f"H{size['height']}mm"
        )

    return list(dict.fromkeys(features))