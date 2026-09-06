"""크롭 이미지 가구 속성 추출 기능 테스트입니다."""

import json
import types
import unicodedata
import unittest.mock

import PIL.Image

from app.core import config
from app.schemas.furniture_attribute import FurnitureAttributeResult
from app.services import furniture_attribute_rules, gemini_service
from app.services.prompt.attribute_prompt.furniture_attribute_prompt import (
    build_furniture_attribute_prompt as build_furniture_attribute_prompt_v1,
)
from app.services.prompt.attribute_prompt.furniture_attribute_prompt_v2 import (
    build_furniture_attribute_prompt as build_furniture_attribute_prompt_v2,
)


def _test_settings(api_key: str = "test-key") -> config.Settings:
    """외부 네트워크를 사용하지 않는 테스트 설정을 생성합니다."""
    return config.Settings(
        gemini_api_key=api_key,
        gemini_vlm_model="gemini-test",
        gemini_embedding_model="embedding-test",
        mvp_login_id="",
        mvp_login_password="",
        image_storage_root="unused",
        sku_image_root="unused",
        database=config.DatabaseSettings(
            name="",
            username="",
            password="",
            host="",
            port=5432,
        ),
    )


def test_build_v1_furniture_attribute_prompt_injects_allowed_schema() -> None:
    """v1 한글 프롬프트에 카테고리별 허용 규격을 직접 주입합니다."""
    attribute_schema = furniture_attribute_rules.build_allowed_attribute_schema(
        "의자"
    )

    prompt = build_furniture_attribute_prompt_v1(
        attribute_schema=attribute_schema,
    )

    assert "- 고정 대분류: 의자" in prompt
    assert '"인테리어의자"' in prompt
    assert '"color"' in prompt
    assert '"material"' in prompt
    assert '"has_armrest"' in prompt
    assert '"category": "의자"' in prompt
    assert "JSON 외의 설명" in prompt


def test_build_v2_furniture_attribute_prompt_injects_allowed_schema() -> None:
    """v2 프롬프트에 카테고리별 허용 규격을 직접 주입합니다."""
    attribute_schema = furniture_attribute_rules.build_allowed_attribute_schema(
        "의자"
    )

    prompt = build_furniture_attribute_prompt_v2(
        attribute_schema=attribute_schema,
    )

    assert "- 고정 대분류: 의자" in prompt
    assert '"인테리어의자"' in prompt
    assert '"color"' in prompt
    assert '"material"' in prompt
    assert '"has_armrest"' in prompt
    assert '"category": "의자"' in prompt
    assert "JSON 외의 설명" in prompt


def test_build_allowed_schema_contains_only_visual_common_attributes() -> None:
    """Gemini 입력 규격에는 시각적으로 판단할 공통 속성만 포함합니다."""
    schema = furniture_attribute_rules.build_allowed_attribute_schema("의자")

    assert schema["category"] == "의자"
    assert schema["sub_category_options"] == [
        "인테리어의자",
        "스툴·벤치",
        "빈백",
        "안락의자",
        "흔들의자",
        "학생·사무용의자",
        "게이밍의자",
        "좌식의자·자세보정의자",
        "바체어",
        "발받침",
    ]
    attributes = schema["attributes"]
    assert isinstance(attributes, dict)
    assert set(attributes["common"]) == {"color", "style", "pattern"}
    assert "target_customer" not in attributes["common"]
    assert attributes["category_specific"]["has_armrest"] == [
        "있음",
        "없음",
        "모름",
    ]


def test_build_allowed_schema_rejects_unknown_category() -> None:
    """카탈로그에 없는 카테고리로는 속성 규격을 만들 수 없습니다."""
    try:
        furniture_attribute_rules.build_allowed_attribute_schema("가전")
    except ValueError as error:
        assert "허용하지 않은 카테고리" in str(error)
    else:
        raise AssertionError("알 수 없는 카테고리를 허용했습니다.")


def test_build_response_schema_uses_explicit_attribute_properties() -> None:
    schema = furniture_attribute_rules.build_attribute_response_schema("의자")

    assert schema["type"] == "OBJECT"
    assert set(schema["required"]) == {"category", "attributes"}

    properties = schema["properties"]
    assert "category" in properties
    assert properties["category"]["enum"] == ["의자"]
    assert "sub_category" in properties
    assert "attributes" in properties

    attributes_schema = properties["attributes"]
    assert attributes_schema["type"] == "OBJECT"
    assert "additionalProperties" not in attributes_schema
    assert "color" in attributes_schema["properties"]
    assert "style" in attributes_schema["properties"]
    assert "has_armrest" in attributes_schema["properties"]


def test_normalize_attributes_keeps_only_allowed_keys_and_values() -> None:
    """허용된 시각 속성만 최종 결과에 남깁니다."""
    normalized = furniture_attribute_rules.normalize_attributes(
        "의자",
        {
            "color": "베이지",
            "style": "잘못된 스타일",
            "target_customer": "싱글",
            "material": "패브릭",
            "has_armrest": "있음",
            "unsupported": "값",
        },
    )

    assert normalized == {
        "color": "베이지",
        "material": "패브릭",
        "has_armrest": "있음",
    }


def test_build_evidence_descriptors_uses_only_category_attributes() -> None:
    """근거에는 객체별 카테고리 속성만 사용합니다."""
    descriptors = furniture_attribute_rules.build_evidence_descriptors(
        "의자",
        {
            "color": "블랙",
            "style": "모던",
            "chair_type": "학생·사무용의자",
            "material": "메쉬",
            "has_wheels": "있음",
            "has_backrest": "모름",
        },
    )

    assert descriptors == [
        "메쉬 소재",
        "바퀴가 있는 구조",
    ]


def test_build_evidence_descriptors_uses_storage_attributes() -> None:
    """수납장 전용 구조 속성도 사용자용 근거에 포함합니다."""
    descriptors = furniture_attribute_rules.build_evidence_descriptors(
        "서랍·수납장",
        {
            "storage_type": "주방 수납장",
            "door_type": "여닫이형",
            "has_drawer": "있음",
            "pattern": "무지",
        },
    )

    assert descriptors[:3] == [
        "여닫이형 구조",
        "서랍이 있는 구조",
    ]


def test_build_evidence_descriptors_excludes_category_classification() -> None:
    """세부 유형처럼 카테고리를 재분류하는 값은 근거에서 제외합니다."""
    descriptors = furniture_attribute_rules.build_evidence_descriptors(
        "진열장·책장",
        {
            "storage_type": "장식장",
            "material": "원목",
            "door_type": "유리도어",
        },
    )

    assert descriptors == ["원목 소재", "유리 도어 구조"]


def test_build_evidence_descriptors_avoids_repeated_attribute_names() -> None:
    """값에 이미 포함된 단어를 속성 이름으로 반복하지 않습니다."""
    descriptors = furniture_attribute_rules.build_evidence_descriptors(
        "테이블·식탁·책상",
        {
            "leg_type": "4다리",
            "wood_tone": "밝은 우드톤",
            "seating_capacity": "4인",
        },
    )

    assert descriptors == ["4다리 구조", "밝은 우드톤"]


def test_build_evidence_descriptors_excludes_uncertain_visual_attributes() -> (
    None
):
    """이미지에서 직접 검증하기 어려운 속성은 근거에서 제외합니다."""
    descriptors = furniture_attribute_rules.build_evidence_descriptors(
        "매트리스",
        {
            "size": "퀸(Q)",
            "firmness": "미디엄",
            "thickness": "21~30cm",
            "features": "항균",
        },
    )

    assert descriptors == ["두께 21~30cm"]


def test_build_evidence_descriptors_excludes_unconfirmed_absence() -> None:
    """가림으로 오판할 수 있는 구조 부재 값은 근거에서 제외합니다."""
    descriptors = furniture_attribute_rules.build_evidence_descriptors(
        "의자",
        {
            "material": "원목",
            "has_wheels": "없음",
            "has_backrest": "있음",
            "has_armrest": "모름",
        },
    )

    assert descriptors == ["원목 소재", "등받이가 있는 구조"]


def test_build_evidence_descriptors_formats_category_phrases() -> None:
    """카테고리별 수량과 구조 속성을 자연스러운 표현으로 변환합니다."""
    bed_descriptors = furniture_attribute_rules.build_evidence_descriptors(
        "침대",
        {
            "bed_type": "수납침대",
            "thickness": "21~30cm",
            "product_type": "프레임+매트리스",
        },
    )
    vanity_descriptors = furniture_attribute_rules.build_evidence_descriptors(
        "화장대·콘솔",
        {
            "storage_type": "서랍형",
            "has_mirror": "있음",
        },
    )

    assert bed_descriptors == ["프레임·매트리스 구성"]
    assert vanity_descriptors == [
        "거울이 있는 구조",
        "서랍형 수납 구조",
    ]


def test_validate_result_clears_invalid_sub_category() -> None:
    """허용되지 않은 소분류는 제거하고 유효한 속성은 유지합니다."""
    result = FurnitureAttributeResult(
        category="의자",
        sub_category="사무용 책상",
        attributes={"color": "블랙", "material": "메쉬"},
    )

    validated = furniture_attribute_rules.validate_attribute_result(
        "의자", result
    )

    assert validated.category == "의자"
    assert validated.sub_category is None
    assert validated.attributes == {"color": "블랙", "material": "메쉬"}


def test_validate_result_rejects_changed_category() -> None:
    """탐지 단계 카테고리와 속성 추출 카테고리가 다르면 거부합니다."""
    result = FurnitureAttributeResult(category="소파")

    try:
        furniture_attribute_rules.validate_attribute_result("의자", result)
    except ValueError as error:
        assert "요청 카테고리와 추출 카테고리가 다릅니다" in str(error)
    else:
        raise AssertionError("변경된 카테고리를 허용했습니다.")


def test_validate_result_normalizes_unicode_category_and_values() -> None:
    """Gemini가 NFD 한글을 반환해도 카탈로그 표기로 정규화합니다."""
    result = FurnitureAttributeResult(
        category=unicodedata.normalize("NFD", "의자"),
        sub_category=unicodedata.normalize("NFD", "인테리어의자"),
        attributes={
            "color": unicodedata.normalize("NFD", "블랙"),
            "has_backrest": unicodedata.normalize("NFD", "있음"),
        },
    )

    validated = furniture_attribute_rules.validate_attribute_result(
        "의자", result
    )

    assert validated.category == "의자"
    assert validated.sub_category == "인테리어의자"
    assert validated.attributes == {"color": "블랙", "has_backrest": "있음"}


def test_extract_furniture_attributes_normalizes_gemini_response() -> None:
    """Gemini 결과를 규격에 맞게 정규화하여 반환합니다."""
    client = unittest.mock.Mock()
    client.models.generate_content.return_value = types.SimpleNamespace(
        text=json.dumps(
            {
                "category": "의자",
                "sub_category": "인테리어의자",
                "attributes": {
                    "color": "베이지",
                    "material": "패브릭",
                    "target_customer": "싱글",
                    "unsupported": "값",
                },
            },
            ensure_ascii=False,
        )
    )
    image = PIL.Image.new("RGB", (20, 20))
    settings = _test_settings()
    service = gemini_service.GeminiService(settings)

    with unittest.mock.patch.object(
        gemini_service.genai_client,
        "create_client",
        return_value=client,
    ) as client_factory:
        result = service.extract_furniture_attributes(image, "의자")

    assert result == FurnitureAttributeResult(
        category="의자",
        sub_category="인테리어의자",
        attributes={"color": "베이지", "material": "패브릭"},
    )
    client_factory.assert_called_once_with(settings)
    call = client.models.generate_content.call_args
    assert call.kwargs["model"] == "gemini-test"
    assert call.kwargs["contents"][0] is image
    response_schema = call.kwargs["config"].response_schema
    assert response_schema["type"] == "OBJECT"
    assert (
        "additionalProperties"
        not in response_schema["properties"]["attributes"]
    )
    assert len(call.kwargs["contents"]) == 2
    prompt = call.kwargs["contents"][1]
    assert "- 고정 대분류: 의자" in prompt
    assert '"material"' in prompt
    assert '"has_armrest"' in prompt


def test_extract_furniture_attributes_rejects_category_change() -> None:
    """Gemini가 대분류를 변경하면 응답 검증 오류로 변환합니다."""
    client = unittest.mock.Mock()
    client.models.generate_content.return_value = types.SimpleNamespace(
        text=json.dumps(
            {"category": "소파", "sub_category": None, "attributes": {}},
            ensure_ascii=False,
        )
    )
    service = gemini_service.GeminiService(_test_settings())

    with unittest.mock.patch.object(
        gemini_service.genai_client,
        "create_client",
        return_value=client,
    ):
        try:
            service.extract_furniture_attributes(
                PIL.Image.new("RGB", (20, 20)), "의자"
            )
        except gemini_service.GeminiResponseInvalidError:
            pass
        else:
            raise AssertionError("변경된 카테고리 응답을 허용했습니다.")


def test_extract_furniture_attributes_requires_api_key() -> None:
    """API 키가 없으면 외부 호출 전에 설정 오류를 발생시킵니다."""
    service = gemini_service.GeminiService(_test_settings(api_key=""))

    try:
        service.extract_furniture_attributes(
            PIL.Image.new("RGB", (20, 20)), "의자"
        )
    except gemini_service.GeminiConfigurationError:
        pass
    else:
        raise AssertionError("API 키 없이 속성 추출을 허용했습니다.")
