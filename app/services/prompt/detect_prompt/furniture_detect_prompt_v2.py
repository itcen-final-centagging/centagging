"""가구 객체 탐지 프롬프트 v2를 정의합니다."""

import json
from collections.abc import Mapping

PROMPT_VERSION = "v2"

FURNITURE_DETECTION_PROMPT_TEMPLATE = """
당신은 실내 이미지에서 독립된 가구 객체를 찾는 탐지 모델입니다.

## 목표와 입력

이미지 전체 또는 지정된 ROI에서 선택 가능한 가구를 물리적 객체당 하나씩
찾으세요. 다음 입력 계약을 사용합니다.

- 허용 카테고리: {allowed_categories}
- 좌표: 0~{coordinate_max} 범위의 정규화 정수
- 근거 언어: {evidence_language}
- ROI: {roi_instruction}
- 최소 가시 비율: 약 {min_visible_ratio_percent}%

## 필수 판정 순서

각 후보를 다음 순서로 한 번씩 판정하세요.

1. ROI가 있으면 보이는 범위로 만든 박스의 중심점이 ROI 안인지 확인합니다.
2. 다른 가구의 부품이 아닌 독립된 물리적 가구인지 확인합니다.
3. 허용 카테고리 하나를 구분할 수 있는 구조가 실제로 보이는지 확인합니다.
4. 예상 전체 외형 중 약 {min_visible_ratio_percent}% 이상이 보이는지 확인합니다.
   정확한 면적 계산이 아니라, 카테고리를 구분하는 주요 구조의 가시성을
   기준으로 판단합니다.
5. 1~4를 모두 만족하면 confidence와 관계없이 반환 대상으로 확정한 뒤,
   실제로 보이는 외곽에 밀착한 박스를 만듭니다.

confidence를 먼저 정한 뒤 객체를 제외하지 마세요. 구조를 추측해야 하거나
1~4 중 하나라도 만족하지 않으면 반환하지 마세요.

## 객체 분리와 제외

- 서로 다른 가구의 외곽선이나 고유 구조가 구분되면 박스가 겹쳐도 각각
  반환합니다. 여러 가구를 하나의 큰 박스로 합치지 마세요.
- 같은 물리적 객체를 가리키는 중복 후보는 실제 가시 외곽에 가장 밀착한
  박스 하나만 남깁니다.
- 독립 경계를 정할 수 없는 겹친 후보를 억지로 분리하거나 중복 반환하지
  마세요.
- 문, 서랍, 상판, 등받이 같은 구성 요소는 큰 가구와 독립된 가구가 아니면
  별도 객체로 반환하지 마세요.
- 그림자, 반사, 인쇄된 가구 이미지, 장난감, 식기, 러그, 장식물과 허용
  카테고리로 분류할 수 없는 물체는 제외합니다.

## 바운딩 박스

- `bbox_coord`에는 `xmin`, `ymin`, `xmax`, `ymax`만 둡니다.
- `0 <= xmin < xmax <= {coordinate_max}`와
  `0 <= ymin < ymax <= {coordinate_max}`를 만족해야 합니다.
- 실제로 보이는 가구의 최외곽만 감싸고, 숨은 부분·그림자·인접 객체·여백은
  포함하지 마세요.
- 중심점은 `((xmin+xmax)/2, (ymin+ymax)/2)`입니다.
- ROI는 포함 여부만 결정합니다. 중심점이 ROI 안이면 ROI 밖으로 이어진 실제
  가시 외곽까지 반환하고, ROI 경계로 박스를 자르지 마세요.

## confidence와 evidence

적격 객체를 확정한 다음 아래 기준으로 `confidence`를 부여하세요.

- 0.90~1.00: 독립 객체, 카테고리 구조와 경계가 모두 명확함
- 0.70~0.89: 카테고리는 명확하지만 일부 가림이나 경계 불명확성이 있음
- 0.50~0.69: 주요 구조로 카테고리는 구분되지만 가림이나 잘림이 큼

`confidence`는 가시 비율이나 박스 면적을 그대로 옮긴 값이 아닙니다.
`evidence`는 {evidence_language} 한 문장으로 작성하고, 위치와 실제로 보이는
카테고리 구분 구조만 적으세요. 가림이나 잘림이 있으면 이를 밝히고, 보이지
않는 색상·소재·구조는 추측하지 마세요.

## 응답 형식

{{
  "detections": [
    {{
      "category": "의자",
      "bbox_coord": {{
        "xmin": 99,
        "ymin": 251,
        "xmax": 631,
        "ymax": 977
      }},
      "evidence": "식탁 오른쪽에 좌판과 다리가 보이며 등받이 일부가 가려진 의자입니다.",
      "confidence": 0.82
    }}
  ]
}}

식별 가능한 가구가 없으면 다음과 같이 반환하세요.

{{"detections": []}}

반환 전에 허용 category, 중복, 좌표 범위와 순서, evidence 언어를 한 번
검증하세요. 각 객체에는 `category`, `bbox_coord`, `evidence`, `confidence`만
두고 검증 과정이나 JSON 밖의 설명은 출력하지 마세요.
""".strip()


def _build_roi_instruction(
    roi_bbox: Mapping[str, float] | None,
) -> str:
    """ROI 지정 여부에 맞는 탐지 범위 지시문을 생성합니다."""
    if roi_bbox is None:
        return "지정되지 않음. 이미지 전체를 탐지합니다."

    return (
        "정규화 좌표 기준 "
        f"xmin={roi_bbox['xmin']}, ymin={roi_bbox['ymin']}, "
        f"xmax={roi_bbox['xmax']}, ymax={roi_bbox['ymax']}입니다. "
        "객체 중심점의 포함 여부를 판단하는 데만 사용합니다."
    )


def build_furniture_detection_prompt(
    *,
    allowed_categories: list[str],
    coordinate_max: int = 1000,
    evidence_language: str = "한글",
    roi_bbox: Mapping[str, float] | None = None,
    min_visible_ratio_percent: int = 50,
) -> str:
    """탐지 요청에 사용할 가구 탐지 프롬프트 v2를 생성합니다."""
    if not 0 <= min_visible_ratio_percent <= 100:
        raise ValueError("최소 가시 비율은 0에서 100 사이여야 합니다.")

    return FURNITURE_DETECTION_PROMPT_TEMPLATE.format(
        allowed_categories=json.dumps(
            allowed_categories,
            ensure_ascii=False,
        ),
        coordinate_max=coordinate_max,
        evidence_language=evidence_language,
        roi_instruction=_build_roi_instruction(roi_bbox),
        min_visible_ratio_percent=min_visible_ratio_percent,
    )
