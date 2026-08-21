"""융합 임베딩용 메타데이터 텍스트 생성 테스트입니다."""

from app.services import fused_metadata


def test_build_metadata_text_uses_catalog_spec_order() -> None:
    """입력 딕셔너리 순서와 무관하게 카탈로그 속성 순서를 유지한다."""
    text = fused_metadata.build_metadata_text(
        category="의자",
        sub_category="학생·사무용의자",
        product_name="메쉬 사무용 의자",
        brand="다니카",
        price=47900,
        attributes={
            "has_armrest": "있음",
            "material": "메쉬",
            "color": "블랙",
            "chair_type": "학생·사무용의자",
            "has_wheels": "있음",
            "has_backrest": "있음",
        },
    )

    assert text == "\n".join(
        [
            "상품명: 메쉬 사무용 의자",
            "카테고리: 의자",
            "소분류: 학생·사무용의자",
            "브랜드: 다니카",
            "가격: 47900",
            "color: 블랙",
            "chair_type: 학생·사무용의자",
            "material: 메쉬",
            "has_wheels: 있음",
            "has_backrest: 있음",
            "has_armrest: 있음",
        ]
    )


def test_build_metadata_text_omits_missing_and_invalid_attributes() -> None:
    """객체 메타데이터에서는 누락값·허용값 밖 속성을 제외한다."""
    text = fused_metadata.build_metadata_text(
        category="의자",
        sub_category="허용하지 않는 소분류",
        attributes={
            "color": "블랙",
            "style": None,
            "material": "알 수 없는 소재",
            "has_wheels": "모름",
            "unexpected": "값",
        },
    )

    assert text == "\n".join(["카테고리: 의자", "color: 블랙"])


def test_build_metadata_text_returns_empty_for_unknown_category() -> None:
    """스펙에 없는 카테고리는 잘못된 텍스트 신호를 만들지 않는다."""
    text = fused_metadata.build_metadata_text(
        category="알 수 없는 카테고리",
        attributes={"color": "블랙"},
    )

    assert text == ""
