"""보정 크롭 기반 속성 추출 테스트입니다."""

import asyncio
import io
import types
import unittest.mock

from PIL import Image

from app.schemas.furniture_attribute import FurnitureAttributeResult
from app.schemas.tagging import BoundingBox
from app.services import tagging_service
from app.services.image_processing_service import CroppedObject


def test_attribute_extraction_uses_preprocessed_crop_image() -> None:
    """속성 추출 요청에는 원본 크롭 대신 보정 이미지를 전달한다."""
    raw_image = Image.new("RGB", (2, 2), color=(10, 10, 10))
    corrected_image = Image.new("RGB", (2, 2), color=(200, 200, 200))
    crop = CroppedObject(
        crop_index=7,
        bbox=BoundingBox(xmin=0, ymin=0, xmax=1000, ymax=1000),
        image=raw_image,
        image_bytes=b"raw-crop",
    )
    gemini_service = unittest.mock.Mock()
    extracted = types.SimpleNamespace(
        sub_category="학생·사무용의자",
        attributes={"color": "블랙"},
    )
    gemini_service.extract_furniture_attributes.return_value = extracted
    service = tagging_service.TaggingService(
        session=unittest.mock.Mock(),
        settings=unittest.mock.Mock(),
        gemini_service=gemini_service,
        similar_sku_service=unittest.mock.Mock(),
        xai_scoring_service=unittest.mock.Mock(),
    )

    with unittest.mock.patch.object(
        tagging_service,
        "preprocess_for_embedding",
        return_value=types.SimpleNamespace(image=corrected_image),
    ):
        processed_images = asyncio.run(service._preprocess_crops([crop]))
        attributes_by_idx = asyncio.run(
            service._extract_attributes(
                [crop],
                {7: "의자"},
                processed_images,
            )
        )

    assert attributes_by_idx == {7: extracted}
    assert gemini_service.extract_furniture_attributes.call_args.args == (
        corrected_image,
        "의자",
    )


def test_fused_input_uses_corrected_image_and_extracted_attributes() -> None:
    """검색 임베딩은 보정 이미지와 VLM이 추출한 속성을 함께 사용한다."""
    raw_image = Image.new("RGB", (2, 2), color=(10, 10, 10))
    corrected_image = Image.new("RGB", (2, 2), color=(200, 200, 200))
    crop = CroppedObject(
        crop_index=7,
        bbox=BoundingBox(xmin=0, ymin=0, xmax=1000, ymax=1000),
        image=raw_image,
        image_bytes=b"raw-crop",
    )

    fused_input = tagging_service.TaggingService._build_fused_embedding_inputs(
        [crop],
        {7: "의자"},
        {
            7: FurnitureAttributeResult(
                category="의자",
                sub_category="학생·사무용의자",
                attributes={"color": "블랙", "has_wheels": "있음"},
            )
        },
        {7: corrected_image},
    )[7]

    assert fused_input.image is corrected_image
    assert fused_input.metadata_text == "\n".join(
        [
            "카테고리: 의자",
            "소분류: 학생·사무용의자",
            "color: 블랙",
            "has_wheels: 있음",
        ]
    )


def test_xai_input_uses_preprocessed_crop_bytes() -> None:
    """XAI 요청에는 원본 바이트 대신 보정 Crop의 JPEG 바이트를 전달한다."""
    raw_image = Image.new("RGB", (20, 20), color=(10, 10, 10))
    corrected_image = Image.new("RGB", (20, 20), color=(200, 200, 200))
    crop = CroppedObject(
        crop_index=7,
        bbox=BoundingBox(xmin=0, ymin=0, xmax=1000, ymax=1000),
        image=raw_image,
        image_bytes=b"raw-crop",
    )

    xai_crop = tagging_service.TaggingService._build_xai_crops(
        [crop],
        {7: corrected_image},
    )[0]

    assert xai_crop.crop_index == crop.crop_index
    assert xai_crop.bbox == crop.bbox
    assert xai_crop.image is corrected_image
    assert xai_crop.image_bytes != crop.image_bytes
    with Image.open(io.BytesIO(xai_crop.image_bytes)) as decoded:
        assert decoded.convert("RGB").getpixel((10, 10)) == (200, 200, 200)
