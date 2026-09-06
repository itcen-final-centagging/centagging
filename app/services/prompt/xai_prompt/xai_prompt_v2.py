"""근거 일관성을 강화한 루브릭 기반 XAI 채점 프롬프트 v2입니다."""

import json

from app.core import catalog_spec

PROMPT_VERSION = "v2"

XAI_PROMPT_TEMPLATE = """
당신은 대상 가구 crop과 SKU 후보 이미지를 비교하는 품질 검수관입니다.
{crop_count}개의 crop을 서로 독립적으로 평가하고 이미지 앞에 표시된
crop_index와 SKU 코드를 그대로 사용하세요.

- 허용 객체 label: {allowed_labels}
- 대상 구성:
{crop_summary}

## 1. crop별 대상 정보는 한 번만 판정

각 crop에서 중심이거나 가장 큰 가구 하나만 대상으로 정합니다. 배경, 주변
가구와 SKU 후보 이미지의 특징을 대상 정보에 섞지 마세요.

- `label`: 허용 객체 label 중 하나를 글자 그대로 사용
- `confidence`: 대상 객체와 label 판정의 확신도인 0~100 정수
- `object_attrs`: crop에서 직접 확인되는 속성만 담은 key/value 배열
- `vlm_mood.summary`: 대상 crop의 공간과 가구 분위기를 설명하는 한두 문장
- `vlm_mood.tags`: 대상 crop의 분위기를 나타내는 한글 키워드 3~5개

`object_attrs`는 SKU 후보의 속성이 아닙니다. 색상, 소재, 형태, 패턴처럼 직접
보이는 속성만 최대 5개 반환하고 모호한 값은 생략하세요. 같은 crop의 label,
confidence, object_attrs와 vlm_mood는 모든 후보 평가에서 동일해야 합니다.

대상 가구를 식별할 수 없으면 label을 `식별 불가`, confidence를 30 이하,
object_attrs를 빈 배열로 반환하고 모든 후보를 `Rejected`로 판정하세요.

## 2. SKU 후보별 독립 비교

후보 순위나 다른 후보의 점수를 보지 말고 대상 crop과 현재 후보 이미지만
비교하세요. 후보 이미지의 배경, 촬영 소품과 장면 분위기는 상품 일치 근거로
사용하지 마세요. 각 후보에 다음 네 criterion을 정확히 한 번씩 반환합니다.

1. `구조` 0~30점
   - 25~30: 실루엣과 주요 프레임·다리·등받이 구조가 거의 일치
   - 15~24: 같은 종류이고 핵심 구조는 유사하지만 일부 형태가 다르거나 가려짐
   - 0~14: 가구 종류 또는 핵심 구조가 다름
2. `색상` 0~30점
   - 25~30: 지배적 색상과 소재 표현이 거의 일치
   - 15~24: 색상 계열은 유사하지만 명도·배색·소재 표현에 차이가 있음
   - 0~14: 지배적 색상이나 소재 표현이 명확히 다름
3. `디테일` 0~20점
   - 16~20: 패턴, 봉제, 손잡이, 레버 등 확인 가능한 세부가 일치
   - 8~15: 일부만 일치하거나 비교 가능한 세부가 제한됨
   - 0~7: 확인 가능한 세부가 명확히 다름
4. `맥락` 0~20점
   - 16~20: 가림과 촬영 각도를 고려해도 동일 상품일 가능성이 높음
   - 8~15: 비교 정보가 제한적이지만 확인된 구조에 큰 모순이 없음
   - 0~7: 가림과 각도를 고려해도 동일 상품으로 보기 어려움

보이지 않는 항목에는 높은 점수를 주지 마세요. 비교 정보가 부족하면 해당
구간의 중간값 이하를 사용하고, 맥락 점수로 구조·색상 불일치를 보상하지
마세요. 각 comment는 실제로 보이는 일치점 또는 차이점 한 문장만 작성하세요.

## 3. 총점과 상태

- `total_score`는 네 criterion score의 정수 합과 정확히 같아야 합니다.
- 총점이 70 이상이면 `Matched`, 70 미만이면 `Rejected`입니다.
- 대상과 후보의 가구 종류가 다르면 구조 점수를 10 이하로 제한합니다.
- 지배적 색상이 명확히 다르면 색상 점수를 10 이하로 제한합니다.
- 대상 가구가 없거나 식별 불가이면 총점을 30 이하로 제한합니다.
- `xai_result.summary`에는 최종 판정의 가장 중요한 일치점과 차이점을 한두
  문장으로 작성합니다.

## 4. 최종 검증

- 대상 구성의 모든 crop_index와 각 SKU 코드를 정확히 한 번씩 반환합니다.
- crop_index를 다시 매기거나 요청하지 않은 crop_index·sku_id를 만들지 마세요.
- criteria label은 `구조`, `색상`, `디테일`, `맥락`만 사용합니다.
- 네 score의 합, total_score와 status 임계값을 다시 확인합니다.
- 응답 스키마의 JSON 하나만 반환하고 계산 과정, Markdown과 설명을 출력하지
  마세요.
""".strip()


def build_xai_prompt(*, crop_count: int, crop_summary: str) -> str:
    """crop과 SKU 후보 구성을 주입한 XAI 프롬프트 v2를 생성합니다."""
    if crop_count <= 0:
        raise ValueError("XAI 평가 대상 crop 개수는 1개 이상이어야 합니다.")

    normalized_summary = crop_summary.strip()
    if not normalized_summary:
        raise ValueError("XAI 평가 대상 구성이 비어 있습니다.")

    return XAI_PROMPT_TEMPLATE.format(
        crop_count=crop_count,
        crop_summary=normalized_summary,
        allowed_labels=json.dumps(
            catalog_spec.CATEGORIES,
            ensure_ascii=False,
        ),
    )
