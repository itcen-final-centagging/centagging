"""
정답 SKU 메타데이터 추출 스크립트 테스트

테스트 대상:
    scripts/extract_answer_sku_metadata.py

테스트 범위:
    1. 이미지 5장 정상 로딩
    2. 이미지 누락 시 예외
    3. 프롬프트에 카테고리 정보 포함
    4. 프롬프트에 catalog_spec 허용값 포함
    5. 정상 메타데이터 검증
    6. 필수 속성 누락 검증
    7. 잘못된 속성값 검증
    8. Mock 기반 전체 파이프라인
"""

import json
import pytest
from PIL import Image
from scripts import extract_answer_sku_metadata as target


# 테스트용 유효 메타데이터 생성
def make_valid_attributes():
    """현재 catalog_spec 기준의 유효한 테스트 데이터를 생성한다."""
    attributes = {}

    for attribute in target.catalog_spec.attribute_names(
        target.CATEGORY
    ):
        allowed = target.catalog_spec.allowed_values(
            target.CATEGORY,
            attribute,
        )

        attributes[attribute] = allowed[0]

    return attributes


# 1. 이미지 로딩 테스트
def test_load_images_success(tmp_path, monkeypatch):
    """이미지 5장을 정상적으로 로드하는지 테스트한다."""
    image_dir = tmp_path / "answer_sku"
    image_dir.mkdir()

    # 테스트용 이미지 5장 생성
    for filename in target.IMAGE_FILENAMES:
        image = Image.new("RGB", (100, 100), "white")
        image.save(image_dir / filename)

    monkeypatch.setattr(
        target,
        "IMAGE_DIR",
        image_dir,
    )

    images = target.load_images()

    assert len(images) == 5

    for image in images:
        assert isinstance(image, Image.Image)
        assert image.mode == "RGB"


def test_load_images_file_not_found(tmp_path, monkeypatch):
    """이미지가 하나라도 없으면 FileNotFoundError가 발생하는지 테스트한다."""

    image_dir = tmp_path / "answer_sku"
    image_dir.mkdir()

    # 이미지 1장만 생성
    image = Image.new("RGB", (100, 100), "white")
    image.save(
        image_dir / target.IMAGE_FILENAMES[0]
    )

    monkeypatch.setattr(
        target,
        "IMAGE_DIR",
        image_dir,
    )

    with pytest.raises(FileNotFoundError):
        target.load_images()

# 2. 프롬프트 생성 테스트
def test_build_prompt_contains_category_information():
    """프롬프트에 대분류와 소분류가 포함되는지 테스트한다."""

    prompt = target.build_prompt()

    assert target.CATEGORY in prompt
    assert target.SUB_CATEGORY in prompt


def test_build_prompt_contains_allowed_values():
    """catalog_spec의 속성과 허용값이 프롬프트에 포함되는지 테스트한다."""

    prompt = target.build_prompt()

    attributes = target.catalog_spec.attribute_names(
        target.CATEGORY
    )

    for attribute in attributes:
        assert attribute in prompt

        values = target.catalog_spec.allowed_values(
            target.CATEGORY,
            attribute,
        )

        for value in values:
            assert value in prompt


# 3. 메타데이터 검증 테스트
def test_validate_attributes_success():
    """모든 속성이 존재하고 허용값이면 검증을 통과하는지 테스트한다."""

    attributes = make_valid_attributes()

    # 예외가 발생하지 않아야 한다.
    target.validate_attributes(attributes)


def test_validate_attributes_missing_attribute():
    """필수 속성이 누락되면 ValueError가 발생하는지 테스트한다."""
    attributes = make_valid_attributes()

    first_attribute = target.catalog_spec.attribute_names(
        target.CATEGORY
    )[0]

    del attributes[first_attribute]

    with pytest.raises(ValueError, match="누락"):
        target.validate_attributes(attributes)


def test_validate_attributes_invalid_value():
    """허용되지 않은 속성값이면 ValueError가 발생하는지 테스트한다."""

    attributes = make_valid_attributes()

    first_attribute = target.catalog_spec.attribute_names(
        target.CATEGORY
    )[0]

    attributes[first_attribute] = "허용되지않는값"

    with pytest.raises(
        ValueError,
        match="허용되지 않습니다",
    ):
        target.validate_attributes(attributes)


# 4. 전체 파이프라인 테스트
class FakeGeminiService:
    """실제 Gemini API를 호출하지 않는 테스트용 서비스."""
    def generate_vlm_json(
        self,
        images,
        prompt,
    ):
        return {
            "attributes": make_valid_attributes(),
            "vlm_reason": "테스트용 Gemini 응답",
        }


def test_metadata_pipeline_without_real_gemini(
    tmp_path,
    monkeypatch,
):
    """
    실제 Gemini API를 호출하지 않고 전체 메타데이터 파이프라인을 테스트한다.
    이미지 로드
        ↓
    프롬프트 생성
        ↓
    Mock Gemini 호출
        ↓
    메타데이터 검증
        ↓
    JSON 저장
    """

    # 테스트 이미지 생성
    image_dir = tmp_path / "answer_sku"
    image_dir.mkdir()

    for filename in target.IMAGE_FILENAMES:
        image = Image.new(
            "RGB",
            (100, 100),
            "white",
        )

        image.save(
            image_dir / filename
        )

    monkeypatch.setattr(
        target,
        "IMAGE_DIR",
        image_dir,
    )

    # 테스트 결과 저장 경로
    output_path = tmp_path / "answer_sku.json"

    monkeypatch.setattr(
        target,
        "OUTPUT_PATH",
        output_path,
    )

    # 1. 이미지 로드
    images = target.load_images()

    assert len(images) == 5


    # 2. 프롬프트 생성
    prompt = target.build_prompt()

    assert target.CATEGORY in prompt
    assert target.SUB_CATEGORY in prompt


    # 3. Mock Gemini 호출
    service = FakeGeminiService()

    result = target.ask_gemini(
        service=service,
        images=images,
        prompt=prompt,
    )

    assert "attributes" in result
    assert "vlm_reason" in result

    # 4. 메타데이터 검증
    target.validate_attributes(
        result["attributes"]
    )

    # 5. JSON 저장
    target.save_result(
        attributes=result["attributes"],
        vlm_reason=result.get("vlm_reason"),
    )

    # 6. 최종 결과 검증
    assert output_path.exists()

    saved_data = json.loads(
        output_path.read_text(
            encoding="utf-8"
        )
    )

    assert len(saved_data) == 1

    saved = saved_data[0]

    assert saved["sku_code"] == target.SKU_CODE
    assert saved["product_name"] == target.PRODUCT_NAME
    assert saved["brand"] == target.BRAND
    assert saved["category"] == target.CATEGORY
    assert saved["sub_category"] == target.SUB_CATEGORY

    assert saved["attributes"] == result["attributes"]
    assert saved["vlm_reason"] == "테스트용 Gemini 응답"