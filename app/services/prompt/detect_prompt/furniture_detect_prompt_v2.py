"""가구 객체 탐지 프롬프트 v2를 정의합니다."""

import json

PROMPT_VERSION = "v2"

FURNITURE_DETECTION_PROMPT_TEMPLATE = """
당신은 실내 이미지에서 독립된 가구 객체를 찾는 탐지 모델입니다.

## 목표와 입력

이미지 전체에서 선택 가능한 가구를 물리적 객체당 하나씩 찾으세요. 다음 입력
계약을 사용합니다.

- 허용 카테고리: {allowed_categories}
- 좌표: 0~{coordinate_max} 범위의 정규화 정수
- 근거 언어: {evidence_language}

## 필수 판정 순서

각 후보를 다음 순서로 한 번씩 판정하세요.

1. 다른 가구의 부품이 아닌 독립된 물리적 가구인지 확인합니다.
2. 허용 카테고리 하나를 구분할 수 있는 구조가 실제로 보이는지 확인합니다.
3. 1~2를 모두 만족하면 confidence와 관계없이 반환 대상으로 확정한 뒤,
   실제로 보이는 외곽에 밀착한 박스를 만듭니다.

confidence를 먼저 정한 뒤 객체를 제외하지 마세요. 구조를 추측해야 하거나
1~2 중 하나라도 만족하지 않으면 반환하지 마세요.

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

## 가림 객체 좌표

- 대상 객체의 `bbox_coord` 내부에서 탐지 대상이 아닌 전경 물체가 대상 가구의
  실제 구조를 물리적으로 가릴 때만 `occluder_bbox_coord`에 그 전경 물체의
  가시 외곽 좌표를 반환합니다.
- 가림 객체가 없으면 `occluder_bbox_coord`는 `null`로 반환합니다.
- 허용 카테고리로 별도 탐지되는 다른 가구는 대상 박스와 겹쳐 보여도 가림
  객체로 반환하지 않습니다.
- 두 탐지 박스의 좌표가 겹친다는 이유만으로 가림 객체라고 판단하지 않습니다.
- 대상 객체의 실제 구조가 가려졌는지 불분명하면 `occluder_bbox_coord`는
  `null`로 반환합니다.
- 대상 객체 자신의 부품, 그림자, 반사와 단순 배경은 가림 객체로 판단하지
  않습니다.
- 가시 면적 비율과 최종 포함 여부는 계산하지 마세요. 서버는 가림 객체 좌표가
  대상 박스 내부와 실제로 교차할 때만 교차 면적을 계산하여 판정합니다.

## 내부 탐지 confidence와 탐지 근거

적격 객체를 확정한 다음 아래 기준으로 `confidence`를 부여하세요. 응답의
`confidence` 키는 화면용 신뢰도가 아닌 내부 `detect_confidence`를 의미합니다.

- 0.90~1.00: 독립 객체, 카테고리 구조와 경계가 모두 명확함
- 0.70~0.89: 카테고리는 명확하지만 일부 가림이나 경계 불명확성이 있음
- 0.50~0.69: 주요 구조로 카테고리는 구분되지만 가림이나 잘림이 큼

`confidence`는 가시 비율이나 박스 면적을 그대로 옮긴 값이 아니며, 구조와
카테고리, 가림 및 경계의 명확성을 함께 반영합니다.

`evidence`는 속성 추출 이전에 쓰는 내부 탐지 근거입니다. {evidence_language}
한 문장으로 실제로 보이는 카테고리 구분 구조만 적고, 반드시
"...로 판단했습니다." 형식으로 끝내세요.

- 객체의 위치는 근거로 사용하지 마세요.
- 가려짐이나 잘림이 있으면 이를 밝히되, 색상·소재·스타일·소분류와 보이지
  않는 구조는 추측하거나 적지 마세요.
- 최종 사용자용 근거는 이후 속성 추출 결과로 별도 생성됩니다.

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
      "occluder_bbox_coord": {{
        "xmin": 410,
        "ymin": 690,
        "xmax": 631,
        "ymax": 977
      }},
      "evidence": "좌판과 등받이, 다리 구조가 명확하게 구분되어 의자로 판단했습니다.",
      "confidence": 0.82
    }}
  ]
}}

식별 가능한 가구가 없으면 다음과 같이 반환하세요.

{{"detections": []}}

반환 전에 허용 category, 중복, 좌표 범위와 순서, 내부 탐지 근거 언어를 한 번
검증하세요. 각 객체에는 `category`, `bbox_coord`, `occluder_bbox_coord`,
`evidence`, `confidence`만 두고 검증 과정이나 JSON 밖의 설명은 출력하지
마세요.
""".strip()


def build_furniture_detection_prompt(
    *,
    allowed_categories: list[str],
    coordinate_max: int = 1000,
    evidence_language: str = "한글",
) -> str:
    """탐지 요청에 사용할 가구 탐지 프롬프트 v2를 생성합니다."""
    return FURNITURE_DETECTION_PROMPT_TEMPLATE.format(
        allowed_categories=json.dumps(
            allowed_categories,
            ensure_ascii=False,
        ),
        coordinate_max=coordinate_max,
        evidence_language=evidence_language,
    )
