"""크롭 이미지 가구 속성 추출 기능 테스트입니다."""

import json
import types
import unittest.mock

import PIL.Image

from app.core import config
from app.schemas.furniture_attribute import FurnitureAttributeResult
from app.services import furniture_attribute_rules, gemini_service


def _test_settings(api_key: str = "test-key") -> config.Settings:
    """외부 네트워크를 사용하지 않는 테스트 설정을 생성합니다."""
    return config.Settings(
        gemini_api_key=api_key,
        gemini_vlm_model="gemini-test",
        gemini_embedding_model="embedding-test",
        mvp_login_id="",
        mvp_login_password="",
        image_storage_root="unused",
        database=config.DatabaseSettings(
            name="",
            username="",
            password="",
            host="",
            port=5432,
        ),
    )


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
    service = gemini_service.GeminiService(_test_settings())

    with unittest.mock.patch.object(
        gemini_service.genai,
        "Client",
        return_value=client,
    ) as client_factory:
        result = service.extract_furniture_attributes(image, "의자")

    assert result == FurnitureAttributeResult(
        category="의자",
        sub_category="인테리어의자",
        attributes={"color": "베이지", "material": "패브릭"},
    )
    client_factory.assert_called_once_with(api_key="test-key")
    call = client.models.generate_content.call_args
    assert call.kwargs["model"] == "gemini-test"
    assert call.kwargs["contents"][0] is image
    context = json.loads(call.kwargs["contents"][2])
    assert context["category"] == "의자"
    assert context["attributes"]["category_specific"]["material"]


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
        gemini_service.genai,
        "Client",
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
