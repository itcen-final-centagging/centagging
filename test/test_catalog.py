"""catalog 규칙·빌더 회귀 테스트.

규칙 기반 코드는 키워드가 쌓일수록 다른 상품에서 오탐이 나기 쉽다.
    pytest test/test_catalog.py
"""

from __future__ import annotations

import pathlib
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.catalog import metadata_builder, sku_builder  # noqa: E402
from scripts.catalog import text_rules as rules  # noqa: E402
from scripts.catalog import validator  # noqa: E402


# --- 색상 -----------------------------------------------------------------

def test_색상_조합어는_우선순위표를_따른다():
    assert rules.normalize_color("로즈우드") == "브라운"
    assert rules.normalize_color("블랙오크(상판)") == "블랙"
    assert rules.normalize_color("파인그레이") == "그레이"


def test_색상_근거가_없으면_None():
    assert rules.normalize_color("단품") is None
    assert rules.normalize_color("") is None


# --- 소재 -----------------------------------------------------------------

def test_프레임_소재는_프레임_절이나_금속을_먼저_본다():
    spec = "18mm PB, 양면LPM마감, 1.5T ABS엣지, 스틸프레임 분체도장 마감"
    assert rules.normalize_material(
        spec, "테이블·식탁·책상", "frame_material",
        prefer=("철제/스틸",), focus_words=("프레임",),
    ) == "철제/스틸"
    assert rules.normalize_material(
        spec, "테이블·식탁·책상", "top_material",
    ) == "가공목(MDF 외)"


def test_의자_주요소재는_겉감을_먼저_본다():
    spec = "스틸, 메쉬천, 스펀지, PP, 우레탄 외"
    prefer, focus = metadata_builder.material_hint("의자", "material")
    assert rules.normalize_material(
        spec, "의자", "material", prefer=prefer, focus_words=focus,
    ) == "메쉬"


# --- 사이즈 / 열거형 -------------------------------------------------------

def test_침구사이즈는_긴_토큰을_먼저_본다():
    assert rules.normalize_bed_size("SS 무헤드형 프레임") == "슈퍼싱글(SS)"
    assert rules.normalize_bed_size("퀸 그레이") == "퀸(Q)"


def test_매트리스_타입은_상품명을_요약보다_우선한다():
    product = {
        "goods_id": 1,
        "name": "편안한 제주 25cm 본넬스프링 매트리스",
        "category_path": ["가구", "매트리스·토퍼", "매트리스"],
        "ai_attributes": {"핵심요약": "합성 라텍스로 탄탄한 지지"},
        "options": [{"first_option": "25cm 필로우탑_S", "is_main": True}],
    }
    draft = metadata_builder.build_draft(product, "매트리스", "매트리스")
    assert draft["mattress_type"]["value"] == "스프링"


# --- 확신도 / 채택 ---------------------------------------------------------

def test_사람_확정값은_규칙값을_이긴다():
    draft = {"color": {"value": "블랙", "source": "option", "confidence": 0.9}}
    merged = metadata_builder.apply_verified(draft, {"color": "화이트"})
    assert merged["color"] == {
        "value": "화이트", "source": "human", "confidence": 1.0,
    }


def test_VLM값은_자동채택되지_않는다():
    merged = metadata_builder.apply_vlm(
        {}, {"style": {"value": "모던", "confidence": 1.0}}
    )
    assert merged["style"]["confidence"] <= metadata_builder.VLM_CONFIDENCE_CAP
    accepted, review = metadata_builder.accept(merged, "소파")
    assert "style" not in accepted
    assert any(item["attribute"] == "style" for item in review)


# --- SKU 조립 --------------------------------------------------------------

def _product() -> dict:
    return {
        "goods_id": 999,
        "options": [
            {"first_option": "800 사이즈", "second_option": "화이트"},
            {"first_option": "1000 사이즈", "second_option": "화이트"},
            {"first_option": "800 사이즈", "second_option": "블랙"},
        ],
    }


def test_속성이_같은_옵션은_한_SKU로_합쳐진다():
    rows = sku_builder.build_skus(
        product=_product(), category="선반", sub_category="스탠드선반",
        product_name="테스트 선반", key_features=[],
        base_attributes={"shelf_type": "스탠드선반", "color": "화이트"},
        option_spec={},
    )
    assert len(rows) == 2  # 사이즈만 다른 옵션은 합쳐지고 색상은 나뉜다
    assert {row["attributes"]["color"] for row in rows} == {"화이트", "블랙"}


def test_같은_속성조합이면_sku_code가_항상_같다():
    first = sku_builder.sku_code("선반", 999, {"color": "화이트"})
    second = sku_builder.sku_code("선반", 999, {"color": "화이트"})
    assert first == second and first.startswith("SHLF-")


def test_값이_없는_속성은_key째로_빠진다():
    rows = sku_builder.build_skus(
        product={"goods_id": 1, "options": [{"first_option": "단품"}]},
        category="거울", sub_category="전신거울",
        product_name="테스트 거울", key_features=[],
        base_attributes={"shape": "아치형", "frame_material": None},
        option_spec={},
    )
    assert "frame_material" not in rows[0]["attributes"]


# --- 검증 -----------------------------------------------------------------

def test_검증은_허용값_밖과_null을_잡아낸다():
    row = {
        "sku_code": "MIR-TEST",
        "product_name": "테스트 거울",
        "category": "거울",
        "sub_category": "전신거울",
        "key_features": [],
        "attributes": {"shape": "육각형", "installation_type": None},
    }
    errors = validator.validate_row(row)
    assert any("허용값 외" in message for message in errors)
    assert any("null" in message for message in errors)
