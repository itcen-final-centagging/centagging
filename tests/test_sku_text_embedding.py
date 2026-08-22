"""승인 누적 공간 분위기·스타일 태그를 반영한 텍스트 조립 테스트입니다."""

from app.services import sku_text_embedding


def test_dedupe_preserve_order_ignores_case_and_whitespace() -> None:
    """대소문자·앞뒤 공백만 다른 값은 처음 표기만 남긴다."""
    result = sku_text_embedding.dedupe_preserve_order(
        ["Cozy", " cozy ", "COZY", "Warm"]
    )

    assert result == ["Cozy", "Warm"]


def test_dedupe_preserve_order_skips_blank_and_non_string_values() -> None:
    """빈 문자열과 문자열이 아닌 값은 결과에서 제외한다."""
    result = sku_text_embedding.dedupe_preserve_order(
        ["", "   ", "포근함", None, 123]
    )

    assert result == ["포근함"]


def test_collect_active_moods_gathers_summaries_and_tags() -> None:
    """summary와 tags를 각각 모으고 형식이 다른 값은 건너뛴다."""
    summaries, tags = sku_text_embedding.collect_active_moods(
        [
            {"summary": "따뜻한 우드톤 거실", "tags": ["우드", "내추럴"]},
            {"summary": "", "tags": ["우드", "미니멀"]},
            {"tags": None},
            "잘못된 값",
            None,
        ]
    )

    assert summaries == ["따뜻한 우드톤 거실"]
    assert tags == ["우드", "내추럴", "우드", "미니멀"]


def test_append_mood_lines_adds_deduped_summary_and_tag_lines() -> None:
    """중복 제거된 공간 분위기·스타일 태그 줄을 기존 텍스트 뒤에 붙인다."""
    text = sku_text_embedding.append_mood_lines(
        "메쉬 사무용 의자\n카테고리: 의자",
        mood_summaries=["따뜻한 우드톤 거실", "따뜻한 우드톤 거실 "],
        style_tags=["우드", "내추럴", "우드"],
    )

    assert text == "\n".join(
        [
            "메쉬 사무용 의자",
            "카테고리: 의자",
            "공간 분위기: 따뜻한 우드톤 거실",
            "스타일 태그: 우드, 내추럴",
        ]
    )


def test_append_mood_lines_returns_base_text_when_nothing_accumulated() -> None:
    """누적된 분위기·태그가 없으면 기존 텍스트를 그대로 반환한다."""
    text = sku_text_embedding.append_mood_lines(
        "메쉬 사무용 의자", mood_summaries=[], style_tags=[]
    )

    assert text == "메쉬 사무용 의자"


def test_build_sku_base_text_matches_offline_batch_line_order() -> None:
    """상품명 -> 카테고리 -> 속성 -> 특징 순서로 조립한다."""
    text = sku_text_embedding.build_sku_base_text(
        product_name="메쉬 사무용 의자",
        category="의자",
        sub_category="학생·사무용의자",
        attributes={"has_wheels": "있음", "color": "블랙"},
        key_features=["높이 조절", "요추 지지"],
    )

    assert text == "\n".join(
        [
            "메쉬 사무용 의자",
            "카테고리: 의자 > 학생·사무용의자",
            "속성: has_wheels: 있음, color: 블랙",
            "특징: 높이 조절 요추 지지",
        ]
    )


def test_build_sku_base_text_omits_missing_optional_fields() -> None:
    """소분류·속성·특징이 없으면 해당 줄을 만들지 않는다."""
    text = sku_text_embedding.build_sku_base_text(
        product_name="원목 식탁", category="테이블"
    )

    assert text == "\n".join(["원목 식탁", "카테고리: 테이블"])


def test_build_sku_base_text_excludes_none_valued_attributes() -> None:
    """값이 None인 속성은 속성 줄에서 제외한다."""
    text = sku_text_embedding.build_sku_base_text(
        product_name="원목 식탁",
        category="테이블",
        attributes={"material": "원목", "color": None},
    )

    assert text == "\n".join(
        ["원목 식탁", "카테고리: 테이블", "속성: material: 원목"]
    )
