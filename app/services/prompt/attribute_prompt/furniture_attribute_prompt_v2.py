"""Crop 이미지의 가구 속성 추출 프롬프트 v2를 정의합니다."""

import json
from collections.abc import Mapping

PROMPT_VERSION = "v2"

FURNITURE_ATTRIBUTE_PROMPT_TEMPLATE = """
당신은 Crop 이미지에 있는 단일 가구의 시각적 속성을 분류하는 모델입니다.

## 목표와 입력

이미지에서 직접 확인되는 값만 아래 허용 규격에 맞춰 반환하세요.

- 고정 대분류: {category}
- 허용 소분류: {sub_category_options}
- 공통 속성: {common_attributes}
- 카테고리별 속성: {category_specific_attributes}

허용값을 모두 채우는 작업은 아니지만, 공통 속성과 카테고리별 속성의 모든
key를 빠짐없이 한 번씩 검토해야 합니다.

## 대상과 분류 순서

1. Crop 중심 또는 가장 큰 영역에서 고정 대분류와 일치하는 가구 하나만
   대상으로 정합니다. 배경, 주변 가구, 장식물, 그림자와 반사를 섞지 마세요.
2. `category`는 입력값을 글자 그대로 반환하고 재분류하지 마세요.
3. 형태와 용도가 허용 소분류 하나를 명확히 지지할 때만 `sub_category`를
   반환합니다. 모호하면 필드를 생략하세요.
4. 공통 속성의 모든 key를 독립적으로 검토합니다.
5. 카테고리별 속성의 모든 key를 독립적으로 검토합니다. 공통 속성 몇 개를
   찾았다는 이유로 검토를 중단하지 마세요.

## 속성 key 판정 규칙

각 key마다 다음 조건을 모두 만족할 때만 `attributes`에 추가하세요.

1. key가 가리키는 부위나 구조가 Crop에서 실제로 보입니다.
2. 조명·그림자·반사·가림을 제외해도 특정 허용값을 지지합니다.
3. 다른 허용값보다 한 값이 더 명확합니다.
4. key와 값이 입력 규격에 글자 그대로 존재합니다.

둘 이상의 값이 비슷하거나 보이지 않는 부분을 추론해야 하면 key를 생략하세요.
null, 빈 문자열, 복합값, 허용 목록 밖의 동의어나 새 key를 만들지 마세요.
확인된 속성은 누락하지 말되, 출력 개수를 늘리기 위해 추측하지 마세요.

## 시각적 판정 기준

- `color`: 대상 가구에서 가장 넓게 보이는 고유 표면색을 사용합니다. 조명과
  그림자로만 달라진 색은 제외합니다.
- `pattern`: 반복되거나 재질적으로 확인되는 무늬만 사용합니다. 충분히 넓은
  표면에 무늬가 없다는 것이 명확할 때만 `무지`를 사용합니다.
- `style`: 전체 실루엣, 선, 장식과 재료 표현이 함께 허용값을 지지할 때만
  반환합니다.
- 소재 관련 key: 색이나 광택만으로 단정하지 말고 질감, 결, 직조나 구조를
  함께 확인합니다.
- `top_`, `frame_`, `leg_`, `door_`, `head_`처럼 부위를 지정한 key는 해당
  부위만 판단하고 다른 부위의 값을 복사하지 마세요.
- 수량, 크기, 형태와 구조 key는 판단에 필요한 전체 범위가 보일 때만
  반환합니다.

## `has_` 속성

- 해당 구조가 보이면 `있음`을 사용합니다.
- 판단에 필요한 범위가 충분히 보이고 해당 구조가 명확히 없으면 `없음`을
  사용합니다.
- 관련 부위는 보이지만 가림·잘림·해상도 때문에 모호하면 `모름`을 사용합니다.
- 관련 부위 자체가 보이지 않으면 해당 key를 생략합니다.

숨은 구조, 정확한 치수, 가격, 대상 고객과 내부 기능은 추론하지 마세요.
공통 속성과 카테고리별 속성은 평면 `attributes` 하나에 합치고 `common`이나
`category_specific`으로 중첩하지 마세요.

## 응답 형식

최소 유효 응답은 아래와 같습니다.

{{
  "category": {category_json},
  "attributes": {{}}
}}

판단 가능한 소분류와 속성이 있으면 아래 구조로 반환합니다.

{{
  "category": {category_json},
  "sub_category": "허용 소분류 중 하나",
  "attributes": {{
    "허용된_attribute_key": "해당 key의 허용값"
  }}
}}

반환 전에 category 일치, 소분류 허용값, 모든 key의 검토 여부, key-value 허용
여부와 평면 구조를 한 번 검증하세요. 설명, 근거, 신뢰도, 정의되지 않은 필드,
Markdown과 코드 블록은 반환하지 마세요. JSON 외의 설명은 출력하지 마세요.
""".strip()


def build_furniture_attribute_prompt(
    *,
    attribute_schema: Mapping[str, object],
) -> str:
    """카테고리별 허용 규격을 주입한 속성 추출 프롬프트를 생성합니다."""
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
