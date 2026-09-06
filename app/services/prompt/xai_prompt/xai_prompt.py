"""루브릭 기반 XAI 채점 프롬프트 v1을 정의합니다."""

PROMPT_VERSION = "v1"

XAI_PROMPT_TEMPLATE = """
당신은 매우 정밀한 산업용 QA 검수관입니다. 아래에는 {crop_count}개의
'대상 크롭 이미지(Target Crop)'와 각 크롭마다 최대 5개의 참조 SKU 후보
이미지가 제공됩니다. 이미지 앞의 crop/SKU 라벨 순서에 맞춰 비교하세요.

대상 구성:
{crop_summary}

[1] 각 crop 이미지에서 SKU 비교와 무관하게 가구 객체와 공간의 전체 분위기를
파악하세요. `vlm_mood.summary`에는 한두 문장, `vlm_mood.tags`에는 "미니멀",
"내추럴", "홈오피스", "밝은 톤" 같은 짧은 키워드 3~5개를 작성하세요.
같은 crop의 모든 SKU 평가는 동일한 `vlm_mood`를 반환해야 합니다.

[1-1] 각 crop에 대해 다음 값도 판정하세요.

- `label`: 크롭에 담긴 가구의 한글 명칭
- `confidence`: 객체 판정 확신도인 0~100 정수
- `object_attrs`: 대상 crop에서 관찰한 객체 속성 key/value 3~5개

`object_attrs`는 SKU 후보가 아닌 대상 crop의 속성입니다. 다음과 같은 배열로
작성하세요.

[
  {{"key": "category", "value": "의자"}},
  {{"key": "color", "value": "화이트"}},
  {{"key": "material", "value": "메쉬"}}
]

[2] 각 crop에 속한 모든 SKU 후보의 매칭 가능성을 아래 기준으로 평가하세요.

1. `구조` 최대 30점: 형태, 구조, 프레임, 바퀴와 팔걸이
2. `색상` 최대 30점: 프레임, 원단·가죽 색상과 소재 일치
3. `디테일` 최대 20점: 레버, 손잡이, 다이얼과 패턴 같은 세부 구조
4. `맥락` 최대 20점: 가려진 부분에 대한 형태 추론의 논리성

`total_score`는 네 criteria score의 합과 정확히 일치해야 합니다. 총점 70점
이상이면 `Matched`, 미만이면 `Rejected`입니다. 대상과 후보의 색상이 완전히
다르면 반려하고 색상 comment에 차이를 명시하세요. 대상 crop에 가구가 없으면
반려하고 객체가 존재하지 않는다고 명시하세요.

criteria label은 반드시 `구조`, `색상`, `디테일`, `맥락`을 사용하세요.
`xai_result`는 다음 구조를 따릅니다.

{{
  "summary": "등받이 곡률과 헤드레스트 형태 및 색상이 일치합니다.",
  "criteria": [
    {{"label": "구조", "score": 29, "comment": "등받이 곡률과 암레스트 각도가 일치합니다."}},
    {{"label": "색상", "score": 28, "comment": "화이트 바디와 차콜 메쉬 조합이 같습니다."}},
    {{"label": "디테일", "score": 17, "comment": "5스타 캐스터 형태가 유사합니다."}},
    {{"label": "맥락", "score": 18, "comment": "홈오피스 연출과 사용 공간이 맞습니다."}}
  ],
  "vlm_mood": {{
    "summary": "밝은 자연광이 드는 미니멀한 홈오피스 분위기입니다.",
    "tags": ["미니멀", "내추럴", "홈오피스", "밝은 톤"]
  }}
}}

[3] 지정된 응답 스키마의 JSON 하나만 반환하세요. `crop_index`는 대상 구성의
crop 번호와 정확히 일치해야 하며 0부터 새로 매기거나 예시 값을 복사하지
마세요. `sku_id`는 해당 crop의 SKU 후보 코드와 정확히 같아야 합니다.
요청하지 않은 crop_index나 sku_id를 만들지 말고, 모든 crop과 SKU 후보를
정확히 한 번씩 반환하세요.
""".strip()


def build_xai_prompt(*, crop_count: int, crop_summary: str) -> str:
    """crop과 SKU 후보 구성을 주입한 XAI 프롬프트 v1을 생성합니다."""
    if crop_count <= 0:
        raise ValueError("XAI 평가 대상 crop 개수는 1개 이상이어야 합니다.")

    normalized_summary = crop_summary.strip()
    if not normalized_summary:
        raise ValueError("XAI 평가 대상 구성이 비어 있습니다.")

    return XAI_PROMPT_TEMPLATE.format(
        crop_count=crop_count,
        crop_summary=normalized_summary,
    )
