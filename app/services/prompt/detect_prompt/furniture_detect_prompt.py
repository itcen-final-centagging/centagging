"""가구 객체 탐지 프롬프트 v1을 정의합니다."""

import json
from collections.abc import Mapping

PROMPT_VERSION = "v1"

FURNITURE_DETECTION_PROMPT_TEMPLATE = """
당신은 가구 인스턴스 탐지 모델입니다.

## 작업

이미지 전체 또는 지정된 ROI에서 서로 구분되고 독립적으로 선택할 수 있는 가구
객체를 모두 탐지하세요. 아래 공통 탐지 계약을 적용하고 지정된 형식의 유효한
JSON만 반환하세요.

## 입력

- 허용 카테고리: {allowed_categories}
- 좌표 체계: 0~{coordinate_max} 범위의 정규화 정수
- 근거 언어: {evidence_language}
- 관심 영역: {roi_instruction}
- 최소 가시 비율: 약 {min_visible_ratio_percent}%

## 공통 탐지 계약

1. 독립된 물리적 가구 하나당 탐지 결과 하나를 반환합니다.
2. 서로 겹쳐도 각 가구의 독립 구조를 식별할 수 있으면 따로 탐지합니다.
   서로 다른 가구를 하나의 큰 박스로 합치지 않습니다.
3. 큰 가구의 구성 요소, 중복 후보, 그림자, 반사, 인쇄된 가구, 장난감, 식기,
   러그와 장식물은 제외합니다.
4. 예상 전체 외형 중 약 {min_visible_ratio_percent}% 이상이 보이고 가구
   카테고리를 식별할 수 있을 때만 탐지합니다.
5. 허용 카테고리 목록의 값만 사용하며 카테고리를 추측하지 않습니다.
6. ROI가 있으면 바운딩 박스 중심점이 ROI 안에 있는 객체만 포함합니다.
   반환 박스를 ROI 경계에 맞춰 자르지 않습니다.
7. 반환 대상 여부는 confidence로 결정하지 않습니다. 1~6을 만족하는 객체는
   먼저 반환 대상으로 확정하고, confidence는 확정된 객체의 내부 탐지 품질만
   나타냅니다.

## 바운딩 박스 규칙

1. `bbox_coord`에는 `xmin`, `ymin`, `xmax`, `ymax`를 포함합니다.
2. 좌표는 `0 <= xmin < xmax <= {coordinate_max}`와
   `0 <= ymin < ymax <= {coordinate_max}`를 만족해야 합니다.
3. 실제로 보이는 가구 범위만 밀착해서 감쌉니다.
4. 숨은 부분을 추정하거나 Crop 여백을 추가하지 않습니다.
5. 그림자, 반사, 인접 가구와 관련 없는 물체를 포함하지 않습니다.
6. 객체가 ROI 경계를 지나더라도 중심점이 ROI 안이면 실제로 보이는 전체 범위를
   반환합니다.

바운딩 박스 중심점은 다음과 같이 계산합니다.

- 중심 X = `(xmin + xmax) / 2`
- 중심 Y = `(ymin + ymax) / 2`

## 내부 탐지 confidence와 탐지 근거

- 응답의 `confidence` 키는 화면용 신뢰도가 아닌 `detect_confidence`입니다.
  해당 영역이 독립된 가구이고 반환 category가 맞다는 내부 탐지 확신도를
  0.00~1.00 범위로 반환합니다.
- confidence는 가시 비율이나 박스 면적을 그대로 옮긴 값이 아닙니다. 구조와
  category, 가림 및 경계의 명확성을 함께 판단합니다.
- `evidence`는 속성 추출 이전에 쓰는 내부 탐지 근거입니다. {evidence_language}의
  짧은 한 문장으로 위치와 실제로 보이는 category 구분 구조만 작성합니다.
- 색상, 소재, 스타일, 소분류, 보이지 않는 구조처럼 속성 추출 단계가 판단할
  내용은 evidence에 넣거나 추측하지 마세요. 최종 사용자용 근거는 이후 속성
  추출 결과를 사용해 별도로 생성됩니다.
- 가려짐이나 이미지 경계의 잘림이 있으면 해당 상태만 언급합니다.

## Output format

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

조건을 만족하는 후보가 없으면 다음과 같이 반환하세요.

{{"detections": []}}

반환 전에 모든 탐지 결과가 허용 카테고리, 가시성, ROI, 좌표, 중복 방지와
내부 탐지 근거 언어 조건을 만족하는지 확인하세요. 각 객체에는 `category`,
`bbox_coord`, `evidence`, `confidence`만 두고 검증 과정이나 JSON 밖의 설명은
출력하지 마세요.
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
        f"xmax={roi_bbox['xmax']}, ymax={roi_bbox['ymax']}입니다."
    )


def build_furniture_detection_prompt(
    *,
    allowed_categories: list[str],
    coordinate_max: int = 1000,
    evidence_language: str = "한글",
    roi_bbox: Mapping[str, float] | None = None,
    min_visible_ratio_percent: int = 50,
) -> str:
    """공통 탐지 계약을 반영한 가구 탐지 프롬프트 v1을 생성합니다."""
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
