"""태깅 좌표 처리와 유사 SKU 추천 계약을 검증합니다."""

import pathlib
import tempfile
import typing
import unittest

import PIL.Image
import PIL.ImageDraw

from app.core import config
from app.schemas import tagging
from app.services import (
    gemini_service,
    image_processing_service,
    similar_sku_service,
)
from app.services.image_processing_service import CroppedObject


class GetCropImageTest(unittest.TestCase):
    """0~1000 정규화 좌표를 실제 이미지 좌표로 변환합니다."""

    def setUp(self) -> None:
        """사분면마다 다른 색으로 채운 테스트 이미지를 준비합니다."""
        self.image = PIL.Image.new("RGB", (1000, 1000))
        draw = PIL.ImageDraw.Draw(self.image)
        draw.rectangle((0, 0, 499, 499), fill=(255, 0, 0))
        draw.rectangle((500, 0, 999, 499), fill=(0, 255, 0))
        draw.rectangle((0, 500, 499, 999), fill=(0, 0, 255))
        draw.rectangle((500, 500, 999, 999), fill=(255, 255, 0))

    def test_crops_each_normalized_quadrant(self) -> None:
        """정규화 좌표의 x축과 y축을 뒤바꾸지 않고 크롭합니다."""
        cases = [
            (
                {"xmin": 0.0, "ymin": 0.0, "xmax": 500.0, "ymax": 500.0},
                (255, 0, 0),
            ),
            (
                {
                    "xmin": 500.0,
                    "ymin": 0.0,
                    "xmax": 1000.0,
                    "ymax": 500.0,
                },
                (0, 255, 0),
            ),
            (
                {
                    "xmin": 0.0,
                    "ymin": 500.0,
                    "xmax": 500.0,
                    "ymax": 1000.0,
                },
                (0, 0, 255),
            ),
            (
                {
                    "xmin": 500.0,
                    "ymin": 500.0,
                    "xmax": 1000.0,
                    "ymax": 1000.0,
                },
                (255, 255, 0),
            ),
        ]

        for bbox, expected_color in cases:
            with self.subTest(bbox=bbox):
                cropped = image_processing_service.get_crop_image(
                    self.image, bbox
                )
                self.assertEqual(cropped.size, (500, 500))
                self.assertEqual(
                    cropped.convert("RGB").getpixel((250, 250)),
                    expected_color,
                )

    def test_rejects_invalid_normalized_bbox(self) -> None:
        """범위를 벗어나거나 방향이 뒤집힌 bbox를 거부합니다."""
        invalid_boxes = [
            {"xmin": -1.0, "ymin": 0.0, "xmax": 100.0, "ymax": 100.0},
            {"xmin": 100.0, "ymin": 0.0, "xmax": 100.0, "ymax": 100.0},
            {"xmin": 0.0, "ymin": 100.0, "xmax": 100.0, "ymax": 100.0},
            {"xmin": 0.0, "ymin": 0.0, "xmax": 1001.0, "ymax": 100.0},
        ]

        for bbox in invalid_boxes:
            with self.subTest(bbox=bbox):
                with self.assertRaises(
                    image_processing_service.InvalidBoundingBoxError
                ):
                    image_processing_service.get_crop_image(self.image, bbox)

    def test_rejects_zero_pixel_crop_after_conversion(self) -> None:
        """유효한 정규화 범위라도 0픽셀로 변환되는 영역은 거부합니다."""
        tiny_image = PIL.Image.new("RGB", (10, 10))

        with self.assertRaises(
            image_processing_service.InvalidBoundingBoxError
        ):
            image_processing_service.get_crop_image(
                tiny_image,
                {"xmin": 0.0, "ymin": 0.0, "xmax": 1.0, "ymax": 1.0},
            )


class CropSceneObjectsTest(unittest.TestCase):
    """object_metadata의 bbox_coord를 크롭 객체로 변환합니다."""

    def test_preserves_object_metadata_array_index(self) -> None:
        """배열 순서를 crop_index로 유지합니다."""
        with tempfile.TemporaryDirectory() as directory:
            image_path = pathlib.Path(directory) / "scene.png"
            PIL.Image.new("RGB", (100, 100)).save(image_path)

            crops = image_processing_service.crop_scene_objects(
                image_path,
                [
                    {
                        "object_idx": 0,
                        "bbox_coord": {
                            "xmin": 100.0,
                            "ymin": 200.0,
                            "xmax": 600.0,
                            "ymax": 700.0,
                        },
                        "category": "의자",
                    }
                ],
            )

        self.assertEqual(len(crops), 1)
        self.assertEqual(crops[0].crop_index, 0)
        self.assertEqual(crops[0].image.size, (50, 50))
        self.assertEqual(crops[0].bbox.xmin, 100.0)
        self.assertEqual(crops[0].bbox.ymin, 200.0)


class _FakeResult:
    """유사 SKU 조회 결과를 반환합니다."""

    def mappings(self) -> "_FakeResult":
        """매핑 결과 체인을 유지합니다."""
        return self

    def all(self) -> list[dict[str, object]]:
        """Windows형 이미지 경로가 저장된 SKU를 반환합니다."""
        return [
            {
                "sku_id": 622,
                "sku_image_id": 71,
                "sku_code": "CHR-0622",
                "product_name": "메쉬 사무용 의자",
                "image_url": r"data\images\622\main.png",
                "image_type": "MAIN",
                "category": "의자",
                "sub_category": "사무용의자",
                "attributes": {"color": "블랙"},
                "similarity": 0.91,
            }
        ]


class _FakeSession:
    """유사 SKU 검색용 비동기 DB 세션입니다."""

    async def execute(self, _statement: object) -> _FakeResult:
        """준비된 유사 SKU 결과를 반환합니다."""
        return _FakeResult()


class _FakeGeminiService:
    """고정된 이미지 임베딩을 반환합니다."""

    def embed_fused(
        self,
        _image: PIL.Image.Image,
        _metadata_text: str,
    ) -> list[float]:
        """검색 차원에 맞는 임베딩을 반환합니다."""
        return [0.1] * similar_sku_service.EMBEDDING_DIMENSIONS


class SimilarSkuRecommendationTest(unittest.IsolatedAsyncioTestCase):
    """추천 결과가 브라우저에서 접근 가능한 이미지 URL을 제공하는지 검증합니다."""

    async def test_returns_public_sku_image_url(self) -> None:
        """DB의 Windows형 경로를 공개 SKU 이미지 URL로 변환합니다."""
        settings = config.Settings(
            gemini_api_key="test-key",
            gemini_vlm_model="test-vlm",
            gemini_embedding_model="test-embedding",
            mvp_login_id="mvp-user",
            mvp_login_password="test-password",
            image_storage_root="uploads",
            sku_image_root="data/images",
            database=config.DatabaseSettings(
                name="test",
                username="test",
                password="test",
                host="localhost",
                port=5432,
            ),
        )
        service = similar_sku_service.SimilarSkuService(
            session=typing.cast(typing.Any, _FakeSession()),
            gemini_service=typing.cast(
                gemini_service.GeminiService,
                _FakeGeminiService(),
            ),
            settings=settings,
        )
        crop = CroppedObject(
            crop_index=0,
            bbox=tagging.BoundingBox(
                xmin=100,
                ymin=200,
                xmax=600,
                ymax=900,
            ),
            image=PIL.Image.new("RGB", (20, 20), color="white"),
            image_bytes=b"image",
        )

        objects = await service.build_detected_objects(
            [crop],
            {
                0: similar_sku_service.FusedEmbeddingInput(
                    image=crop.image,
                    category="chair",
                    metadata_text="카테고리: 의자",
                )
            },
        )

        self.assertEqual(
            objects[0].sku_candidates[0].matched_sku_image.image_url,
            "/sku-images/622/main.png",
        )


if __name__ == "__main__":
    unittest.main()
