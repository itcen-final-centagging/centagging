"""태깅 흐름에서 공통으로 사용하는 이미지 크롭 계약을 검증합니다."""

import pathlib
import tempfile
import unittest

import PIL.Image
import PIL.ImageDraw

from app.services import image_processing_service


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
                        "object_index": 0,
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


if __name__ == "__main__":
    unittest.main()
