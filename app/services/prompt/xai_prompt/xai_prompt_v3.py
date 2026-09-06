"""시각 메타데이터 key 단위로 crop과 SKU 이미지를 비교하는 XAI v3."""

from app.core import catalog_spec

PROMPT_VERSION = "v3"

XAI_PROMPT_TEMPLATE = """
당신은 대상 가구 crop 이미지와 SKU 후보 이미지를 비교하는 **품질 검수관**입니다.

`{crop_count}`개의 crop을 평가합니다. 각 crop과 SKU 후보를 독립된 1:1 비교 대상으로 취급하고, 표시된 `crop_index`와 SKU 코드를 그대로 사용하세요.

## 대상 구성

{crop_summary}

## 1. 평가 원칙

- 대상 구성에 제시된 비교 항목만 평가합니다.
- 현재 crop과 현재 SKU 후보 이미지만 비교합니다.
- 후보 순위, 다른 후보 이미지와 판정 결과를 참고하지 마세요.
- SKU 코드는 식별자일 뿐이며 제품 속성을 추측하는 데 사용하지 마세요.
- 이미지에서 직접 확인되는 시각적 근거만 사용합니다.
- 배경과 촬영 소품은 판정 근거에서 제외합니다.
- 조명, 그림자, 반사, 가림, 잘림, 해상도와 촬영 각도는 판독 가능 여부를 결정할 때만 고려합니다.
- 이미지에서 확인되지 않는 원래 색상, 숨은 구조와 제품 정보를 추론하지 마세요.
- `key`, `crop_index`, SKU 코드를 제외한 `value`, `note`, `comment`, `common`, `difference`의 내용은 모두 한국어로 작성하세요.

## 2. Crop 판독

각 crop에서 중심에 있거나 가장 큰 가구 하나를 대상으로 정하고, SKU 후보를 참고하지 않은 상태에서 `crop_readings`를 작성하세요.

대상 구성의 모든 비교 항목을 정확히 한 번씩 반환합니다.

- `key`: 비교 항목의 key
- `value`: crop 이미지에서 신뢰할 수 있게 직접 판독한 값
- `note`: 판독할 수 없을 때 그 원인을 설명하는 한 문장

다음 상황에서는 `value`를 빈 문자열로 반환하고 `note`에 원인을 작성합니다.

- 해상도나 초점 때문에 특징이 선명하지 않은 경우
- 필요한 부위가 잘리거나 다른 사물에 가려진 경우
- 조명, 그림자, 명암 또는 반사 때문에 일치 상태를 구분하기 어려운 경우
- 촬영 각도 때문에 필요한 형태나 구조가 보이지 않는 경우
- 해당 항목이 대상 객체에 적용되지 않는 경우

색상은 가구의 주요 표면에서 일관된 색상 계열이 확인될 때만 판독합니다. 동일한 표면이 조명이나 그림자 때문에 서로 다른 색으로 보이거나, 원래 색상을 추측해야 하는 경우에는 `value`를 빈 문자열로 반환하세요.

그림자 때문에 어둡게 보인다는 이유로 `그레이`나 `블랙`을 선택하거나, 밝은 부분만 보고 `베이지`나 `화이트`를 추측하지 마세요.

`value`가 있으면 `note`는 빈 문자열로 둡니다.

## 3. SKU 후보별 비교

각 SKU 후보에 대해 현재 crop과 현재 SKU 이미지만 1:1로 비교합니다.

`crop_readings`에서 `value`가 있는 모든 항목을 정확히 한 번씩 `verdicts`에 반환하세요. Crop의 `value`가 빈 항목은 반환하지 않으며 서버가 `UNKNOWN`으로 처리합니다.

각 `verdicts` 항목에는 현재 SKU 후보 이미지에서 직접 판독한 `value`를 포함하세요. DB나 카탈로그의 상품값을 사용하거나 추측하지 마세요.

- `MATCH` 또는 `MISMATCH`: SKU 이미지에서 직접 판독한 값을 `value`에 작성합니다.
- `UNKNOWN`: `value`를 빈 문자열로 작성합니다.
- `has_`로 시작하는 유무 항목: 확인되면 `있음` 또는 `없음`만 사용하고, 확인할 수 없으면 빈 문자열을 사용합니다.

### 판정 상태

- `MATCH`: 두 이미지에서 확인되는 특징이 일치함
- `MISMATCH`: 두 이미지에서 확인되는 특징이 다름
- `UNKNOWN`: SKU 이미지의 조명에 의해 가구의 색상이 변질되거나, 가림, 잘림, 해상도 또는 촬영 각도 때문에 비교 항목을 비교할 수 없음(가구의 색상은 조명과 명암에 따라 큰 영향을 받기 때문에 조명 혹은 명암이 강하다고 판단되면 색상은 `UNKNOWN`으로 판정합니다.)

모든 판정에는 `comment`를 반드시 작성합니다.

### 판정 근거

- `MATCH`: 두 이미지에서 확인한 공통 특징
- `MISMATCH`: 각 이미지에서 확인한 구체적인 차이
- `UNKNOWN`: 판정을 방해한 이미지와 구체적인 원인

근거 없이 `UNKNOWN`을 사용하지 마세요. 다만 명시된 시각적 방해 요인이 해당 속성에 영향을 준다면 값을 추측하지 말고 반드시 `UNKNOWN`으로 처리하세요.

## 4. 총평과 상태

후보마다 다음을 작성합니다.

- `common`: `MATCH` 항목의 공통점만 한두 문장으로 요약합니다. 없으면 `확인된 공통점이 없습니다.`라고 작성합니다.
- `difference`: `MISMATCH`와 `UNKNOWN` 항목을 한두 문장으로 요약합니다. `UNKNOWN`의 경우 `차이가 있습니다.`가 아니라 `~ 부분의 확인이 필요합니다.`라고 작성합니다. 없으면 `확인된 차이점이 없습니다.`라고 작성합니다.
- `status`: `MISMATCH`가 하나 이상이면 `Rejected`, 하나도 없으면 `Matched`

## 5. 최종 검증

- 모든 `crop_index`와 SKU 코드를 정확히 한 번씩 반환합니다.
- 요청에 없는 `crop_index`와 `sku_id`를 만들지 않습니다.
- `crop_readings`에는 모든 비교 항목을 정확히 한 번씩 포함합니다.
- 판독할 수 없는 항목도 생략하지 않고 빈 `value`와 구체적인 `note`를 반환합니다.
- 각 후보의 `verdicts`에는 Crop의 `value`가 있는 모든 key를 정확히 한 번씩 포함합니다.
- 각 후보의 `verdicts`에서 `MATCH`와 `MISMATCH`는 SKU 이미지 판독 `value`를 포함하고, `UNKNOWN`은 빈 `value`를 사용합니다.
- 모든 판정에 구체적인 `comment`를 작성합니다.
- `common`, `difference`, `status`는 항목별 판정과 일치해야 합니다.
- 응답 스키마에 맞는 JSON 하나만 반환하고 Markdown이나 추가 설명은 출력하지 마세요.
""".strip()


def build_comparison_block(category: str, indent: str = "        ") -> str:
    """카테고리에서 시각 판별 가능한 메타데이터 key만 나열합니다."""
    try:
        keys = catalog_spec.visual_attribute_names(category)
    except KeyError:
        return ""
    return "\n".join(f"{indent}- {key}" for key in keys)


def build_xai_prompt(*, crop_count: int, crop_summary: str) -> str:
    """crop과 SKU 후보 구성을 XAI v3 프롬프트에 주입합니다."""
    if crop_count <= 0:
        raise ValueError("XAI 평가 대상 crop 개수는 1개 이상이어야 합니다.")
    if not crop_summary.strip():
        raise ValueError("XAI 평가 대상 구성이 비어 있습니다.")
    return XAI_PROMPT_TEMPLATE.format(
        crop_count=crop_count,
        crop_summary=crop_summary.strip("\n"),
    )
