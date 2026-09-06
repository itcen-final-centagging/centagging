"""승인 누적 공간 분위기·스타일 태그를 반영한 SKU 텍스트 임베딩 조립입니다.

검수 최종 승인(app.services.approval_service._reindex_sku_text_embedding)과
오프라인 배치(scripts.embedding.build_embeddings)가 같은 조립 규칙을
쓰도록 이 모듈에 공유 로직을 둔다. sku_catalog에 별도 컬럼을 추가하지
않고, 매번 tagging_result.vlm_mood(승인된 건만)를 다시 모아 텍스트를
조립한다.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Mapping
from typing import Any


def dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    """공백·대소문자·유니코드 표현 차이를 무시하고 중복을 제거합니다.
    Args:
        values: 원본 문자열 목록입니다. 문자열이 아니거나 빈 값은
            건너뜁니다.

    Returns:
        중복이 제거된 문자열 목록으로, 등장 순서를 보존합니다.
    """
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        stripped = value.strip()
        if not stripped:
            continue
        normalized = unicodedata.normalize("NFKC", stripped).casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(stripped)
    return result


def collect_active_moods(
    vlm_moods: Iterable[Any],
) -> tuple[list[str], list[str]]:
    """승인된 vlm_mood JSON 목록에서 공간 분위기와 스타일 태그를 모읍니다.

    같은 SKU가 여러 연출 이미지에서 반복 승인된 경우를 처리하기 위한
    누적 집계이며, 중복 제거는 이 함수가 아니라 dedupe_preserve_order가
    담당한다.

    Args:
        vlm_moods: 승인된(approval.status = 'ACTIVE') tagging_result의
            vlm_mood 값 목록입니다. 각 값은 {"summary": str,
            "tags": list[str]} 형태를 기대하지만, 형식이 다르거나 비어
            있는 값이 섞여 있어도 무시하고 넘어갑니다.

    Returns:
        (공간 분위기 요약 목록, 스타일 태그 목록) 튜플입니다. 등장 순서를
        보존하되 아직 중복은 제거하지 않은 원본 목록입니다.
    """
    summaries: list[str] = []
    tags: list[str] = []
    for mood in vlm_moods:
        if not isinstance(mood, dict):
            continue
        summary = mood.get("summary")
        if isinstance(summary, str) and summary.strip():
            summaries.append(summary)
        for tag in mood.get("tags") or []:
            if isinstance(tag, str) and tag.strip():
                tags.append(tag)
    return summaries, tags


def prioritize_display_moods(
    real_vlm_moods: Iterable[Any],
    fallback_vlm_moods: Iterable[Any],
    *,
    min_tag_count: int = 5,
) -> tuple[list[str], list[str]]:
    """프론트에 보여줄 공간 분위기·스타일 태그를 실제 연출 이미지 우선으로 만듭니다.

    ``collect_active_moods``는 실제 연출 이미지에서 얻은 값과 데모 시드
    (``scripts.seed.seed_demo_vlm_moods``)로 지어낸 값을 구분 없이 그대로
    누적한다 — 텍스트 임베딩 조립(``append_mood_lines``가 쓰이는
    검색 관련도 목적)에는 이 편이 맞다. 하지만 화면에 그대로 보여줄
    때는 "가라"로 채운 태그보다 실제 VLM이 연출 이미지를 보고 뽑은
    태그를 우선해야 하므로, 이 함수가 그 우선순위 규칙을 담당한다.

    규칙:
        - 실제 연출 이미지 태그가 min_tag_count개 이상이면, 그것만
          보여주고 시드 태그는 버린다.
        - 실제 태그가 부족하면(0개 포함), 시드 태그로 min_tag_count에
          맞춰 뒤에 채운다(실제 태그가 항상 앞에 옵니다).
        - 실제 분위기 요약이 하나라도 있으면 그것만 쓰고, 전혀 없을
          때만 시드 요약으로 대체한다.

    Args:
        real_vlm_moods: 실제 연출 이미지에서 얻은(즉 데모 시드가 아닌)
            승인된 tagging_result.vlm_mood 값 목록입니다.
        fallback_vlm_moods: 데모 시드로 채운 vlm_mood 값 목록입니다.
            실제 태그가 min_tag_count에 못 미칠 때만 사용합니다.
        min_tag_count: 화면에 보장할 최소 스타일 태그 개수입니다.

    Returns:
        (공간 분위기 요약 목록, 스타일 태그 목록) 튜플이며, 둘 다 중복이
        제거되고 등장 순서를 보존합니다.
    """
    real_summaries, real_tags = collect_active_moods(real_vlm_moods)
    real_summaries = dedupe_preserve_order(real_summaries)
    real_tags = dedupe_preserve_order(real_tags)

    if not real_summaries and not real_tags:
        fallback_summaries, fallback_tags = collect_active_moods(
            fallback_vlm_moods
        )
        return (
            dedupe_preserve_order(fallback_summaries),
            dedupe_preserve_order(fallback_tags),
        )

    tags = real_tags
    if len(tags) < min_tag_count:
        _, fallback_tags = collect_active_moods(fallback_vlm_moods)
        tags = dedupe_preserve_order(tags + fallback_tags)

    return real_summaries, tags


def append_mood_lines(
    base_text: str,
    *,
    mood_summaries: Iterable[str] = (),
    style_tags: Iterable[str] = (),
) -> str:
    """상품 정보 텍스트 뒤에 누적된 공간 분위기·스타일 태그 줄을 붙입니다.

    base_text는 상품명·카테고리·속성·특징으로 조립된 기존 텍스트 임베딩
    입력이다(오프라인 배치는
    scripts.embedding.text_builder.build_embedding_text의 결과를, 승인
    트리거는 build_sku_base_text의 결과를 그대로 넘긴다). 이 함수는 그
    뒤에 공간 분위기·스타일 태그 줄만 추가해, 온라인(승인 트리거)과
    오프라인(배치) 두 경로가 같은 최종 임베딩 텍스트를 만들도록 한다.

    Args:
        base_text: 상품명·카테고리·속성·특징으로 조립된 텍스트입니다.
        mood_summaries: 승인된 공간 분위기 요약 목록입니다(중복 허용,
            내부에서 정규화 후 제거합니다).
        style_tags: 승인된 스타일 태그 목록입니다(중복 허용, 내부에서
            정규화 후 제거합니다).

    Returns:
        공간 분위기·스타일 태그 줄이 추가된 임베딩 입력 텍스트입니다.
        누적된 값이 없으면 base_text를 그대로 반환합니다.
    """
    lines = [base_text] if base_text else []

    deduped_summaries = dedupe_preserve_order(mood_summaries)
    if deduped_summaries:
        lines.append("공간 분위기: " + " ".join(deduped_summaries))

    deduped_tags = dedupe_preserve_order(style_tags)
    if deduped_tags:
        lines.append("스타일 태그: " + ", ".join(deduped_tags))

    return "\n".join(lines)


def build_sku_base_text(
    *,
    product_name: str,
    category: str | None,
    sub_category: str | None = None,
    attributes: Mapping[str, Any] | None = None,
    key_features: Iterable[str] | None = None,
) -> str:
    """상품명·카테고리·속성·특징으로 텍스트 임베딩 기본 문장을 조립합니다.

    scripts.embedding.text_builder.build_embedding_text와 같은 줄 구성
    순서(상품명 -> 카테고리 -> 속성 -> 특징)를 검수 승인 트리거에서도
    쓰기 위한 앱 계층 버전이다. 승인 시점에 이미 로드된 SkuCatalog ORM
    필드를 그대로 받는다. 값이 없는 카테고리(sub_category)·속성·특징
    줄은 만들지 않으며, 속성 값이 None인 항목은 제외한다.

    Args:
        product_name: 상품명입니다.
        category: 대분류입니다.
        sub_category: 소분류입니다. 없으면 카테고리 줄에 붙이지 않습니다.
        attributes: 상품 속성입니다. 값이 None인 항목은 제외합니다.
        key_features: 상품 핵심 특징 목록입니다.

    Returns:
        상품명 -> 카테고리 -> 속성 -> 특징 순으로 이어붙인 텍스트입니다.
    """
    lines = [product_name]

    category_line = f"카테고리: {category}" if category else "카테고리:"
    if sub_category:
        category_line += f" > {sub_category}"
    lines.append(category_line)

    filtered_attributes = {
        key: value
        for key, value in (attributes or {}).items()
        if value is not None
    }
    if filtered_attributes:
        attribute_text = ", ".join(
            f"{key}: {value}" for key, value in filtered_attributes.items()
        )
        lines.append(f"속성: {attribute_text}")

    features = [feature for feature in (key_features or []) if feature]
    if features:
        lines.append("특징: " + " ".join(features))

    return "\n".join(lines)
