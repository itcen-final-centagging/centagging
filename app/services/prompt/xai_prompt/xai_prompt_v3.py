"""카테고리 메타데이터 단위로 일치 여부를 판정하는 XAI 프롬프트 v3입니다.

v2까지는 구조·색상·디테일·맥락에 고정 배점을 두고 100점을 매겼습니다.
배점 자체에 근거가 없고 감점 사유가 추상적이어서, v3에서는 채점을 없애고
`catalog_spec`에 정의된 카테고리 메타데이터를 항목별로 비교합니다.

v2와 달라진 점:
- 점수표를 쓰지 않습니다. 일치도는 모델이 아니라 서버가 계산합니다.
- 비교 항목은 crop의 카테고리에서 시각적으로 판별 가능한 속성만 씁니다.
- crop 판독은 후보와 무관하므로 crop당 한 번만 요청합니다. 후보마다
  다시 묻지 않으므로 후보별로 다른 답이 나올 여지가 없습니다.
- 총평을 공통점과 차이점으로 나눠 받습니다.
- vlm_mood와 object_attrs는 요청하지 않습니다. 속성 추출 단계에서 이미
  같은 crop으로 뽑고 있어 중복입니다.
"""

import json

from app.core import catalog_spec

PROMPT_VERSION = "v3"

XAI_PROMPT_TEMPLATE = """
당신은 대상 가구 crop과 SKU 후보 이미지를 비교하는 품질 검수관입니다.
{crop_count}개의 crop을 서로 독립적으로 평가하고 이미지 앞에 표시된
crop_index와 SKU 코드를 그대로 사용하세요.

- 대상 구성:
{crop_summary}

## 1. crop 판독 (crop당 한 번)

각 crop에서 중심이거나 가장 큰 가구 하나만 대상으로 정합니다. 배경, 주변
가구와 SKU 후보 이미지의 특징을 대상 판독에 섞지 마세요.

해당 crop의 `비교 항목`을 정확히 한 번씩 `crop_readings`로 반환합니다.
항목을 추가하거나 빼지 마세요.

비교 항목이 현재 객체에 적용되지 않는다고 판단해도 절대 생략하지 마세요.
적용되지 않거나 이미지에서 확인할 수 없는 항목은 반드시 `value`를 빈
문자열로 두고, `note`에 `해당 객체에 적용되지 않는 속성입니다.` 또는
가림·해상도·조명·촬영 각도 등 실제로 확인하기 어려운 이유를 작성하세요.

- `key`: 비교 항목의 키를 글자 그대로 사용
- `value`: crop 이미지에서 직접 확인되는 값. 해당 항목의 허용값 중 하나를
  글자 그대로 사용합니다. 가림, 해상도, 조명, 촬영 각도 때문에 값을 특정할
  수 없으면 빈 문자열로 둡니다.
- `note`: `value`가 빈 문자열일 때만, 무엇 때문에 확인이 어려운지 한 문장

이 판독은 SKU 후보와 무관하게 crop 이미지만 보고 결정합니다. 후보 이미지를
참고하지 마세요. 보이지 않는 값을 추측해서 채우지 마세요.

## 2. SKU 후보별 비교

후보 순위나 다른 후보의 결과를 보지 말고, 대상 crop과 현재 후보 이미지만
비교하세요. 후보 이미지의 배경, 촬영 소품과 장면 분위기는 판정 근거로
사용하지 마세요.

각 후보에 대해, 1단계에서 `value`가 비어 있지 않은 항목만 `verdicts`로
반환합니다. `value`가 빈 항목은 반환하지 마세요. 서버가 판단 불가로
처리합니다.

- `key`: 비교 항목의 키를 글자 그대로 사용
- `verdict`
  - `MATCH`: 후보 이미지에서 확인되는 값이 crop 판독값과 같음
  - `MISMATCH`: 후보 이미지에서 확인되는 값이 crop 판독값과 다름
  - `UNKNOWN`: 후보 이미지에서 해당 항목을 확인할 수 없음
- `comment`: 그렇게 판정한 근거 한 문장. 실제로 보이는 것만 서술합니다.

각 후보의 카탈로그 값은 `대상 구성`에 함께 제시되어 있습니다. 참고는 하되,
카탈로그 값과 후보 이미지가 어긋나면 이미지에서 보이는 것을 기준으로
판정하고 `comment`에 그 차이를 적으세요.

## 3. 총평과 상태

후보마다 다음을 작성합니다.

- `common`: 두 객체의 공통점을 한두 문장으로 요약합니다. `MATCH`로 판정한
  항목의 내용만 사용합니다.
- `difference`: 차이점과 확인이 필요한 부분을 한두 문장으로 요약합니다.
  `MISMATCH`로 판정한 항목과 판독하지 못한 항목만 사용합니다. 해당하는
  항목이 없으면 `확인된 차이점이 없습니다.`로 작성합니다.
- `status`: `MISMATCH`가 하나도 없으면 `Matched`, 하나 이상이면 `Rejected`

점수나 백분율을 직접 계산하지 마세요. 일치도는 서버가 계산합니다.

## 4. 최종 검증

- 대상 구성의 모든 crop_index와 각 SKU 코드를 정확히 한 번씩 반환합니다.
- crop_index를 다시 매기거나 요청하지 않은 crop_index·sku_id를 만들지 마세요.
- `crop_readings`의 key 집합은 해당 crop의 `비교 항목` 목록과 정확히 같아야
  합니다.
- 적용되지 않거나 판독할 수 없는 항목도 생략하지 말고 빈 value와 note를
  반환합니다.
- `verdicts`의 key는 `crop_readings`에서 `value`가 비어 있지 않은 항목의
  부분집합이어야 합니다.
- `value`는 해당 항목의 허용값 또는 빈 문자열만 사용합니다.
- 응답 스키마의 JSON 하나만 반환하고 계산 과정, Markdown과 설명을 출력하지
  마세요.
""".strip()


def build_comparison_block(category: str, indent: str = "        ") -> str:
    """카테고리의 시각 비교 대상 속성과 허용값을 프롬프트 블록으로 만든다.

    Args:
        category: crop의 대분류입니다.
        indent: 블록 각 줄 앞에 붙일 들여쓰기입니다.

    Returns:
        `- key: [허용값, ...]` 형태의 줄을 이어 붙인 문자열입니다.
        정의되지 않은 대분류이면 빈 문자열입니다.
    """
    try:
        keys = catalog_spec.visual_attribute_names(category)
    except KeyError:
        return ""

    return "\n".join(
        f"{indent}- {key}: "
        f"{json.dumps(catalog_spec.allowed_values(category, key) or [], ensure_ascii=False)}"
        for key in keys
    )


def build_xai_prompt(*, crop_count: int, crop_summary: str) -> str:
    """crop과 SKU 후보 구성을 주입한 XAI 프롬프트 v3를 생성합니다.

    Args:
        crop_count: 이번 요청에서 평가할 crop 개수입니다.
        crop_summary: crop별 카테고리·비교 항목·SKU 후보를 정리한 블록입니다.

    Returns:
        모델에 그대로 보낼 프롬프트 문자열입니다.

    Raises:
        ValueError: 평가 대상이 비어 있는 경우입니다.
    """
    if crop_count <= 0:
        raise ValueError("XAI 평가 대상 crop 개수는 1개 이상이어야 합니다.")

    if not crop_summary.strip():
        raise ValueError("XAI 평가 대상 구성이 비어 있습니다.")

    return XAI_PROMPT_TEMPLATE.format(
        crop_count=crop_count,
        # 앞뒤 빈 줄만 걷어냅니다. 들여쓰기를 지우면 crop 블록의 첫 줄만
        # 왼쪽으로 붙어 목록이 어긋나 보입니다.
        crop_summary=crop_summary.strip("\n"),
    )
