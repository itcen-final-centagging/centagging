"""원본 데이터와 규칙으로 상품 메타데이터 초안을 만든다.

오늘의집 원본에는 카테고리, 소재, 크기, 구성품, 옵션처럼 이미 상품에 명시된
정보가 많기 때문에, 이러한 정보까지 VLM으로 다시 추론할 필요가 없다.

따라서 메타데이터 생성 순서는 다음과 같다.

1. 원본에 명시된 값
   specifications / category_path / options
   -> 상품에 직접 적혀 있는 정보를 우선 사용한다.

2. 규칙으로 유도되는 값
   상품명·옵션 키워드 / text_rules
   -> 원본 텍스트에서 규칙으로 판단할 수 있는 값을 추출한다.

3. 그래도 남는 값
   VLM 보조 / vlm_assist.py
   -> 규칙으로 판단하지 못한 속성만 VLM으로 보완한다.
   -> 상품당 최대 1회 호출한다.

4. 최종 확정
   사람 검수 / verified_attrs.json
   -> 사람이 확정한 값은 최종 정답으로 사용한다.

각 속성은 `{"value": 값, "source": 출처, "confidence": 신뢰도}` 형태의
메타정보를 함께 가진다. confidence가 AUTO_ACCEPT 이상이면 자동 채택하고,
기준보다 낮으면 사람이 검수할 대상으로 분류한다. 단, 사람이 직접 확정한
값(source="human")은 항상 최우선으로 취급한다.
"""

from __future__ import annotations

from typing import Any

from app.core import catalog_spec
from scripts.catalog import text_rules as rules

# 이 값 이상이면 사람 확인 없이 채택한다.
AUTO_ACCEPT = 0.9

# VLM 값에 허용할 최대 confidence. 모델이 1.0을 줘도 자동 채택되지 않게 해서
# "VLM 결과는 초안"이라는 규칙을 수치로 강제한다.
VLM_CONFIDENCE_CAP = 0.85

# 원본 텍스트로는 판정할 수 없는 속성 (VLM 보조 또는 사람 판단 영역)
HUMAN_ONLY_ATTRS = {"target_customer", "target_age"}

# 소재 계열 속성
MATERIAL_ATTRS = {"material", "top_material", "frame_material"}

# 단 수 계열 속성
COUNT_ATTRS = {"drawer_count", "level_count", "shelf_count"}

# 소파·의자에서 `주요 소재`가 가리키는 것은 보통 겉감(표면 소재)이다.
SURFACE_MATERIALS = (
    "패브릭",
    "메쉬",
    "천연가죽",
    "인조가죽",
    "벨벳",
    "스웨이드",
    "라탄",
)

# 위의 표면 소재를 우선해서 판단해야 하는 대분류
SURFACE_FIRST_CATEGORIES = {"소파", "의자"}

# 오늘의집 specifications에서 값이 없는 것과 같은 표현
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

# 자재를 이 개수보다 많이 나열한 스펙은 대표 소재 판정이 흔들려 신뢰도를 낮춘다.
MATERIAL_CHUNK_LIMIT = 3

# 소분류 -> 속성값 직접 매핑
#
# 일부 상품은 원본의 sub_category 자체가 catalog_spec에서 사용하는 속성값을
# 결정할 수 있다. 예를 들어 sub_category가 "서랍장"이면 storage_type도
# "서랍장"이다. 이런 경우 상품명이나 VLM으로 추론하지 않고 원본 카테고리에서
# 바로 값을 가져온다.
#
# 구조: {"대분류": ("저장할 속성명", {"원본 소분류": "최종 속성값"})}
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
    "진열장·책장": ("storage_type", {"책장": "책장", "매거진랙": "매거진랙"}),
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


# 원본 읽기
def spec_value(product: dict, key: str) -> str | None:
    """원본 specifications 값을 읽되 안내 문구는 None으로 본다."""
    value = (product.get("specifications") or {}).get(key)
    if value is None:
        return None
    value = str(value).strip()
    return None if value in EMPTY_SPEC_VALUES else value


def main_option(product: dict) -> dict:
    """대표 옵션(is_main 우선)을 돌려준다.

    Args:
        product: 크롤링한 product.json 딕셔너리입니다.

    Returns:
        대표 옵션 딕셔너리입니다. 옵션이 없으면 빈 옵션입니다.
    """
    options: list[dict] = product.get("options") or []
    for option in options:
        if option.get("is_main"):
            return option
    return options[0] if options else {"first_option": "", "second_option": ""}


def option_text(option: dict) -> str:
    """옵션의 1차/2차 텍스트를 하나로 합친다.

    Args:
        option: product.json의 옵션 딕셔너리입니다.

    Returns:
        공백으로 이어 붙인 옵션 텍스트입니다.
    """
    first = str(option.get("first_option") or "").strip()
    second = str(option.get("second_option") or "").strip()
    return f"{first} {second}".strip()


def source_texts(product: dict) -> dict[str, str]:
    """속성 판정에 쓸 원문 텍스트 묶음을 만든다.

    Args:
        product: 크롤링한 product.json 딕셔너리입니다.

    Returns:
        출처 이름을 key로 하는 원문 텍스트 딕셔너리입니다.
    """
    ai_text = " ".join(
        str(value) for value in (product.get("ai_attributes") or {}).values()
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
    """category_path를 고정 대분류/소분류로 옮긴다.

    Args:
        product: 크롤링한 product.json 딕셔너리입니다.

    Returns:
        `(대분류, 소분류, 경고 목록)`입니다. 대분류를 찾지 못하면 대분류와
        소분류가 모두 None입니다.
    """
    warnings: list[str] = []
    # product.json의 카테고리 경로. 없으면 빈 리스트로 처리한다.
    path = product.get("category_path") or []

    category = None
    for node in path:
        # CATEGORY_MAP에 등록된 값이면 프로젝트의 대분류 이름으로 바꾼다.
        if node in catalog_spec.CATEGORY_MAP:
            category = catalog_spec.CATEGORY_MAP[node]
            break
    if category is None:
        return None, None, [f"category_path {path} 매핑 실패"]

    # 해당 대분류에서 허용하는 소분류 목록과 대조한다.
    fixed_subs = catalog_spec.PRODUCT_CATEGORY.get(category, [])
    sub_category = next((node for node in path[2:] if node in fixed_subs), None)
    if sub_category is None:
        # 일치하는 값이 없으면 원본 category_path의 세 번째 값을 그대로 쓰고
        # 정의 목록에 없다는 경고를 남긴다.
        sub_category = path[2] if len(path) > 2 else None
        warnings.append(
            f"sub_category {sub_category!r}가 "
            f"PRODUCT_CATEGORY['{category}'] 목록에 없음 — 원문 유지"
        )
    return category, sub_category, warnings


# 1~2단계: 원본 + 규칙으로 초안 만들기
def material_hint(
    category: str, attribute: str
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """소재 판정에 쓸 우선순위와 참고 단어를 정한다.

    `주요 소재`는 여러 자재를 한 줄에 나열하므로 속성에 맞는 자재를 골라야
    한다. 프레임 소재는 프레임을 설명한 절이나 금속 계열을, 소파·의자의
    주요 소재는 겉감을 먼저 본다.

    Args:
        category: 고정 대분류입니다.
        attribute: 소재 계열 속성 key입니다.

    Returns:
        `(우선 채택할 소재, 먼저 볼 절을 고르는 단어)`입니다.
    """
    # 프레임 소재는 프레임·다리를 설명한 절에서 금속 계열을 먼저 본다.
    if attribute == "frame_material":
        return ("철제/스틸",), ("프레임", "다리", "각재", "스탠드", "포스트")

    # 상판 소재는 특정 자재를 우선하지 않고 상판을 설명한 절만 먼저 본다.
    if attribute == "top_material":
        return (), ("상판", "탑")

    # 소파·의자는 프레임보다 실제 겉감(원단·커버·마감재)을 우선한다.
    if category in SURFACE_FIRST_CATEGORIES:
        return SURFACE_MATERIALS, ("마감재", "커버", "원단")

    return (), ()


def _put_if_absent(
    draft: dict[str, dict[str, Any]],
    key: str,
    value: Any,
    source: str,
    confidence: float,
) -> None:
    """먼저 잡힌(=더 확실한) 근거를 유지하면서 값을 넣는다.

    Args:
        draft: 채워 나가는 초안 딕셔너리입니다.
        key: 속성 key입니다.
        value: 넣을 값입니다. None이면 넣지 않습니다.
        source: 값의 출처 이름입니다.
        confidence: 이 근거에 줄 신뢰도입니다.
    """
    if value is None or key in draft:
        return
    draft[key] = {
        "value": value,
        "source": source,
        "confidence": confidence,
    }


def _ordered_sources(texts: dict[str, str]) -> list[tuple[str, str, float]]:
    """원본 텍스트를 신뢰도 높은 순서로 늘어놓는다.

    같은 속성이 여러 곳에서 발견되면 앞에 있는 출처를 우선한다. 예를 들어
    상품명 "본넬스프링 매트리스"와 요약 "합성 라텍스 소재"가 함께 있으면
    상품명 쪽을 먼저 채택한다.

    Args:
        texts: `source_texts`가 만든 원문 텍스트 묶음입니다.

    Returns:
        `(출처 이름, 검색할 텍스트, 기본 신뢰도)` 목록입니다.
    """
    # 우선순위:
    #   1. 상품명          -> 가장 직접적인 상품 정보
    #   2. 옵션            -> 실제 판매 옵션 정보
    #   3. 요약/AI 속성    -> 상품 설명에서 추출된 정보
    #   4. 스펙 원문       -> 상세 스펙에 적힌 정보
    #
    # 예:
    #   상품명: "본넬스프링 매트리스"
    #   요약:   "합성 라텍스 소재 사용"
    #
    # 둘 다 소재와 관련된 정보지만,
    # 상품명에 명시된 "본넬스프링"을 먼저 발견하면
    # 상품명의 정보를 우선해서 사용한다.
    return [
        # (출처 이름, 실제 검색할 텍스트, 기본 신뢰도)
        ("name", texts["name"], 0.7),
        # 옵션은 실제 판매 옵션에 해당하므로 상품명보다 조금 높은 신뢰도를 준다.
        ("option", texts["option"], 0.8),
        # summary와 ai_attributes를 하나의 검색 대상 텍스트로 합친다.
        ("ai_attributes", f"{texts['summary']} {texts['ai']}", 0.7),
        # 소재 및 구성 관련 스펙 원문을 하나로 합친다.
        (
            "specification",
            f"{texts['spec_material']} {texts['spec_component']}",
            0.8,
        ),
    ]


def _put_explicit_attrs(
    draft: dict[str, dict[str, Any]],
    texts: dict[str, str],
    category: str,
    sub_category: str | None,
) -> None:
    """원본에 그대로 적혀 있는 값(옵션·스펙·카테고리)을 먼저 채운다.

    Args:
        draft: 채워 나가는 초안 딕셔너리입니다.
        texts: `source_texts`가 만든 원문 텍스트 묶음입니다.
        category: 고정 대분류입니다.
        sub_category: 고정 소분류입니다.
    """
    _put_if_absent(
        draft, "color", rules.normalize_color(texts["option"]), "option", 0.9
    )
    _put_if_absent(
        draft,
        "color",
        rules.normalize_color(texts["spec_color"]),
        "specification",
        0.9,
    )

    if category not in SUBCATEGORY_ATTR_MAP or not sub_category:
        return

    attr_key, mapping = SUBCATEGORY_ATTR_MAP[category]
    # 상품명에 더 구체적인 표기가 있으면 그쪽을 쓴다.
    # (소분류 `일반거실장` + 상품명 `높은거실장` -> 높은형)
    _put_if_absent(
        draft,
        attr_key,
        rules.normalize_enum(
            attr_key,
            texts["name"],
            catalog_spec.allowed_values(category, attr_key),
        ),
        "name",
        0.9,
    )
    _put_if_absent(draft, attr_key, mapping.get(sub_category), "category", 0.95)


def _put_keyword_attrs(
    draft: dict[str, dict[str, Any]], texts: dict[str, str]
) -> None:
    """상품명·요약 키워드로만 판단하는 스타일·패턴을 채운다.

    Args:
        draft: 채워 나가는 초안 딕셔너리입니다.
        texts: `source_texts`가 만든 원문 텍스트 묶음입니다.
    """
    _put_if_absent(
        draft,
        "style",
        rules.normalize_style(f"{texts['name']} {texts['summary']}"),
        "name",
        0.7,
    )
    _put_if_absent(
        draft,
        "pattern",
        rules.normalize_pattern(f"{texts['name']} {texts['spec_material']}"),
        "name",
        0.7,
    )


def _put_schema_attr(
    draft: dict[str, dict[str, Any]],
    texts: dict[str, str],
    category: str,
    key: str,
) -> None:
    """스키마 속성 1개를 속성 성격에 맞는 규칙으로 채운다.

    Args:
        draft: 채워 나가는 초안 딕셔너리입니다.
        texts: `source_texts`가 만든 원문 텍스트 묶음입니다.
        category: 고정 대분류입니다.
        key: 채울 속성 key입니다.
    """
    allowed = catalog_spec.allowed_values(category, key)

    if key in MATERIAL_ATTRS:
        prefer, focus_words = material_hint(category, key)
        # 자재를 여러 개 나열한 스펙은 대표 소재 판정이 흔들린다.
        chunks = rules.material_chunks(texts["spec_material"])
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
            0.9 if len(chunks) <= MATERIAL_CHUNK_LIMIT else 0.75,
        )
    elif key == "size":
        _put_if_absent(
            draft, key, rules.normalize_bed_size(texts["option"]), "option", 0.9
        )
        _put_if_absent(
            draft, key, rules.normalize_bed_size(texts["name"]), "name", 0.7
        )
    elif key == "thickness":
        _put_if_absent(
            draft,
            key,
            rules.normalize_thickness(texts["option"]),
            "option",
            0.9,
        )
        _put_if_absent(
            draft, key, rules.normalize_thickness(texts["name"]), "name", 0.8
        )
    elif key in COUNT_ATTRS:
        _put_if_absent(
            draft,
            key,
            rules.normalize_level_count(texts["name"], allowed),
            "name",
            0.85,
        )
        _put_if_absent(
            draft,
            key,
            rules.normalize_level_count(texts["option"], allowed),
            "option",
            0.85,
        )
    elif key == "seating_capacity":
        _put_if_absent(
            draft,
            key,
            rules.normalize_seating_capacity(texts["name"], allowed),
            "name",
            0.8,
        )
    elif key == "length":
        dimensions = rules.parse_dimensions(texts["spec_size"]) or {}
        _put_if_absent(
            draft,
            key,
            rules.normalize_length(dimensions.get("width")),
            "derived",
            0.85,
        )
    elif allowed == [True, False]:
        # 불리언은 오판 가능성이 가장 커서 자동 채택 기준 아래로 둔다.
        for source, text, _confidence in _ordered_sources(texts):
            _put_if_absent(
                draft, key, rules.normalize_boolean(key, text), source, 0.6
            )
    else:
        for source, text, confidence in _ordered_sources(texts):
            _put_if_absent(
                draft,
                key,
                rules.normalize_enum(key, text, allowed),
                source,
                confidence,
            )


def build_draft(
    product: dict, category: str, sub_category: str | None
) -> dict[str, dict[str, Any]]:
    """원본과 규칙만으로 속성 초안을 만든다.

    VLM은 호출하지 않으며, 크롤링된 상품 정보에서 규칙 기반으로 추출할 수
    있는 속성만 먼저 채운다.

    Args:
        product: 크롤링한 product.json 딕셔너리입니다.
        category: 고정 대분류입니다.
        sub_category: 고정 소분류입니다.

    Returns:
        `{속성: {value, source, confidence}}` 초안입니다.
    """
    texts = source_texts(product)
    draft: dict[str, dict[str, Any]] = {}

    _put_explicit_attrs(draft, texts, category, sub_category)
    _put_keyword_attrs(draft, texts)

    for key in catalog_spec.attribute_names(category):
        if key in draft or key in HUMAN_ONLY_ATTRS:
            continue
        _put_schema_attr(draft, texts, category, key)

    return draft


# 3단계: VLM 보조값 병합
def apply_vlm(
    draft: dict[str, dict[str, Any]], vlm_attrs: dict[str, Any] | None
) -> dict[str, dict[str, Any]]:
    """규칙이 못 채운 속성에만 VLM 값을 채워 넣는다.

    이미 원본·규칙으로 잡힌 값은 덮어쓰지 않는다. 원본에 적힌 사실이
    이미지 추론보다 근거가 강하기 때문이다.

    Args:
        draft: 규칙 단계까지 만들어진 초안입니다.
        vlm_attrs: `{속성: {value, confidence, reason}}` 형태의 VLM 결과입니다.

    Returns:
        VLM 값이 병합된 초안입니다.
    """
    if not vlm_attrs:
        return draft

    # 원본 draft를 건드리지 않도록 복사본에 병합한다.
    merged = dict(draft)
    for key, payload in vlm_attrs.items():
        # 이미 원본 + 규칙 단계에서 값이 결정된 속성이면 건너뛴다.
        #
        # 핵심 규칙:
        # "원본/규칙 값 > VLM 추론값"
        #
        # 예:
        # draft = {"color": {"value": "화이트", ...}}
        # VLM   = {"color": {"value": "아이보리", ...}}
        # → 기존 "화이트"를 유지하고 VLM 값은 사용하지 않는다.
        if key in merged:
            continue

        # 정상적인 VLM 결과는 {"value": ..., "confidence": ..., "reason": ...}
        # 형태지만, {"material": "패브릭"}처럼 값만 오는 경우도 처리한다.
        value = payload.get("value") if isinstance(payload, dict) else payload
        if value is None:
            continue

        confidence = (
            payload.get("confidence", 0.5) if isinstance(payload, dict) else 0.5
        )
        merged[key] = {
            "value": value,
            "source": "vlm",
            # 모델이 1.0을 줘도 자동 채택 기준을 넘지 못하게 잘라 둔다.
            "confidence": min(float(confidence), VLM_CONFIDENCE_CAP),
            "reason": (
                payload.get("reason") if isinstance(payload, dict) else None
            ),
        }
    return merged


# 4단계: 사람 확정값 병합 / 채택 판정
def apply_verified(
    draft: dict[str, dict[str, Any]], verified: dict[str, Any] | None
) -> dict[str, dict[str, Any]]:
    """사람이 확정한 값을 최우선으로 덮어쓴다.

    Args:
        draft: 규칙·VLM 단계까지 만들어진 초안입니다.
        verified: verified_attrs.json의 해당 상품 `attrs`입니다.

    Returns:
        사람 확정값이 반영된 속성 딕셔너리입니다.
    """
    merged = dict(draft)
    for key, value in (verified or {}).items():
        # None은 "모르겠다"가 아니라 "이 속성은 쓰지 않는다"는 최종 판단이므로
        # 규칙·VLM이 채운 값도 함께 지운다.
        if value is None:
            merged.pop(key, None)
            continue
        # 규칙 기반 값이나 VLM 값보다 사람이 검수한 값이
        # 가장 신뢰도가 높기 때문에 무조건 우선한다.
        merged[key] = {"value": value, "source": "human", "confidence": 1.0}
    return merged


# 5단계: 최종 채택 / 검수 대상 분리
def accept(
    merged: dict[str, dict[str, Any]], category: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """신뢰도 기준으로 자동 채택값과 검수 대상을 나눈다.

    규칙·VLM·사람 확정값까지 병합된 결과에서 confidence가 충분히 높은 값은
    자동으로 채택하고, 낮거나 값이 없는 속성은 사람이 검수하도록 분리한다.

    Args:
        merged: 모든 단계가 병합된 속성 딕셔너리입니다.
        category: 고정 대분류입니다.

    Returns:
        `(채택된 {속성: 값}, 검수 대상 목록)`입니다.
    """
    accepted: dict[str, Any] = {}
    review: list[dict[str, Any]] = []

    for key in catalog_spec.attribute_names(category):
        field = merged.get(key)
        # 값 자체가 없으면 사람이 직접 확인해야 한다.
        if field is None:
            review.append({"attribute": key, "reason": "값 없음"})
            continue

        # confidence가 자동 채택 기준 이상이면
        # 사람의 추가 검수 없이 바로 채택한다.
        #
        # 예: AUTO_ACCEPT = 0.9 / confidence = 0.95 → 자동 채택
        if field["confidence"] >= AUTO_ACCEPT:
            accepted[key] = field["value"]
        else:
            # 값 자체는 존재하지만 확신할 수 없으므로
            # 사람이 직접 확인하도록 review에 넣는다.
            review.append(
                {
                    "attribute": key,
                    "value": field["value"],
                    # 이 값이 어디서 왔는지 (rule / vlm / human 등)
                    "source": field["source"],
                    "confidence": field["confidence"],
                    "reason": "confidence 기준 미달",
                }
            )
    return accepted, review


# key_features
def build_key_features(product: dict) -> list[str]:
    """검색·임베딩에 쓸 짧은 사실 문장 목록을 만든다.

    attributes가 "구조화된 정답값"이라면 key_features는 "텍스트 임베딩용
    설명"이다. 역할이 다르므로 원본에 실제로 있는 문장만 넣는다.

    Args:
        product: 크롤링한 product.json 딕셔너리입니다.

    Returns:
        중복을 제거한 문장 목록입니다.
    """
    features: list[str] = []

    # 1. AI 속성 정보에서 특징 문장을 가져온다.
    #
    # ai_attributes는 하나의 값 안에 여러 줄의 설명이
    # 들어있을 수 있기 때문에 줄바꿈 기준으로 나눈다.
    #
    # 예: {"features": "통기성이 우수한 메쉬 소재\n높이 조절 가능"}
    # → ["통기성이 우수한 메쉬 소재", "높이 조절 가능"]
    for value in (product.get("ai_attributes") or {}).values():
        features.extend(
            line.strip() for line in str(value).split("\n") if line.strip()
        )

    # 2. 주요 소재 정보를 추가한다.
    # 너무 긴 값은 key_features에 넣지 않는다.
    # key_features는 검색/임베딩에 사용할 짧은 문장을
    # 만드는 것이 목적이기 때문이다.
    material = spec_value(product, "주요 소재")
    if material and len(material) <= 60:
        # 소재 정보 안에 줄바꿈이 있다면 한 줄로 합친다.
        features.append(material.replace("\n", " "))

    # 3. 구성품 정보를 추가한다. 구성품도 긴 원문은 제외한다.
    component = spec_value(product, "구성품")
    if component and len(component) <= 60:
        # "구성품:"이라는 접두어를 붙여서
        # 임베딩할 때 이 정보가 무엇인지 명확하게 한다.
        features.append(f"구성품: {component}")

    # 4. 크기 정보를 구조화해서 추가한다.
    # 예: "800 x 500 x 750mm" → {"width": 800, "depth": 500, "height": 750}
    size = rules.parse_dimensions(spec_value(product, "크기"))
    # 파싱에 성공했다면 검색하기 좋은 일정한 문장 형태로 변환한다.
    if size:
        features.append(
            f"크기 W{size['width']} x D{size['depth']} x H{size['height']}mm"
        )

    # 5. 중복 문장을 제거한다.
    # dict는 같은 key를 중복해서 가질 수 없다는 특성을 이용한다.
    # dict를 사용하기 때문에 원래 문장의 순서도 유지된다.
    return list(dict.fromkeys(features))
