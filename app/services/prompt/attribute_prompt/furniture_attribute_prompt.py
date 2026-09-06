"""Crop 이미지의 가구 속성 추출 프롬프트 v1을 정의합니다."""

import json
from collections.abc import Mapping

PROMPT_VERSION = "v1"

FURNITURE_ATTRIBUTE_PROMPT_TEMPLATE = """
당신은 가구 속성 추출 모델입니다.

## 작업

Crop 이미지에 보이는 단일 가구 객체를 분석하세요. 제공된 고정 대분류를
사용하고 이미지에서 시각적으로 확인되는 속성만 추출하세요. 아래 입력 규격과
응답 형식에 맞는 유효한 JSON만 반환하세요.

## 입력 규격

- 고정 대분류: {category}
- 허용 소분류: {sub_category_options}
- 공통 속성 규격: {common_attributes}
- 카테고리별 속성 규격: {category_specific_attributes}

고정 대분류는 변경하지 마세요. `sub_category`는 허용 소분류 중 하나만
선택하세요. 공통 속성과 카테고리별 속성에 정의된 key와 허용값만 사용하세요.

## 분류 규칙

1. `category`는 제공된 고정 대분류와 정확히 일치해야 합니다.
2. 제공된 대분류를 변경하거나 다른 카테고리로 재분류하지 않습니다.
3. `sub_category`는 허용 소분류 목록의 값 중 하나만 선택합니다.
4. 소분류를 신뢰할 수 있게 식별할 수 없으면 해당 필드를 생략합니다.
5. 허용 목록에 없는 소분류를 새로 만들지 않습니다.

## 속성 규칙

1. 공통 또는 카테고리별 속성에 정의된 영문 snake_case key만 사용합니다.
2. 각 key에는 해당 규격에 나열된 허용값만 사용합니다.
3. 공통 속성과 카테고리별 속성을 하나의 평면 `attributes` 객체로 반환합니다.
4. 출력에 `common` 또는 `category_specific` 그룹을 만들지 않습니다.
5. 이미지에서 실제로 확인되는 속성만 반환합니다.
6. 숨은 제품 사양, 정확한 치수, 가격, 대상 고객과 비시각 정보를 추론하지
   않습니다.
7. 일반 속성을 확인할 수 없으면 null을 반환하지 말고 key를 생략합니다.
8. `has_`로 시작하는 속성은 `있음`, `없음`, `모름` 중 하나만 사용합니다.
9. 설명, confidence와 정의되지 않은 필드를 `attributes`에 추가하지 않습니다.
10. 신뢰할 수 있는 속성이 없으면 빈 `attributes` 객체를 반환합니다.

## 객체 분위기 규칙

1. `vlm_mood`는 Crop 안에서 실제로 보이는 가구와 주변 맥락의 분위기만 요약합니다.
2. `summary`는 한글 한 문장으로 작성하고, 보이지 않는 용도·브랜드·가격은 추측하지 않습니다.
3. `tags`는 3~5개의 짧은 한글 태그로 작성합니다.
4. 분위기에 점수나 `attributes`의 key-value를 나열하지 않습니다.

## 응답 형식

{{
  "category": {category_json},
  "sub_category": "허용 소분류 중 하나",
  "attributes": {{
    "color": "베이지",
    "style": "모던",
    "material": "패브릭",
    "has_armrest": "있음"
  }},
  "vlm_mood": {{
    "summary": "밝은 톤의 모던한 가구가 보이는 실내 분위기입니다.",
    "tags": ["밝은 톤", "모던", "실내"]
  }}
}}

반환 전에 category와 소분류, 모든 속성 key와 값, 평면 attributes 구조를
내부적으로 검증하세요. 확인되지 않은 값을 만들지 말고 JSON 외의 설명,
Markdown과 코드 블록은 반환하지 마세요.
""".strip()


def build_furniture_attribute_prompt(
    *,
    attribute_schema: Mapping[str, object],
) -> str:
    """카테고리별 허용 규격을 주입한 속성 추출 프롬프트 v1을 생성합니다."""
    category = attribute_schema.get("category")
    sub_categories = attribute_schema.get("sub_category_options")
    attributes = attribute_schema.get("attributes")

    if not isinstance(category, str) or not category:
        raise ValueError("속성 추출 카테고리가 올바르지 않습니다.")
    if not isinstance(sub_categories, list) or not all(
        isinstance(value, str) for value in sub_categories
    ):
        raise ValueError("허용 소분류 규격이 올바르지 않습니다.")
    if not isinstance(attributes, Mapping):
        raise ValueError("허용 속성 규격이 올바르지 않습니다.")

    common_attributes = attributes.get("common")
    category_specific_attributes = attributes.get("category_specific")
    if not isinstance(common_attributes, Mapping) or not isinstance(
        category_specific_attributes, Mapping
    ):
        raise ValueError("공통 또는 카테고리별 속성 규격이 올바르지 않습니다.")

    return FURNITURE_ATTRIBUTE_PROMPT_TEMPLATE.format(
        category=category,
        category_json=json.dumps(category, ensure_ascii=False),
        sub_category_options=json.dumps(
            sub_categories,
            ensure_ascii=False,
        ),
        common_attributes=json.dumps(
            dict(common_attributes),
            ensure_ascii=False,
        ),
        category_specific_attributes=json.dumps(
            dict(category_specific_attributes),
            ensure_ascii=False,
        ),
    )
