"""SKU 이미지 저장 경로와 공개 URL 변환 테스트입니다."""

import io
import pathlib
import tempfile
import unittest

from PIL import Image

from app.services import sku_image_storage


class SkuImageStorageTest(unittest.TestCase):
    """기존 DB 경로도 실제 이미지와 공개 URL로 해석하는지 검증합니다."""

    def test_resolves_legacy_windows_path(self) -> None:
        """Windows에서 저장된 경로를 현재 저장소 기준으로 변환합니다."""
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            image_path = root / "17" / "main.png"
            image_path.parent.mkdir()
            Image.new("RGB", (20, 10), color="white").save(image_path)
            storage = sku_image_storage.SkuImageStorage(root)

            image_bytes = storage.read_jpeg(r"data\images\17\main.png")

            self.assertIsNotNone(image_bytes)
            with Image.open(io.BytesIO(image_bytes)) as image:
                self.assertEqual(image.format, "JPEG")
                self.assertEqual(image.size, (20, 10))
            self.assertEqual(
                storage.public_url(r"data\images\17\main.png"),
                "/sku-images/17/main.png",
            )

    def test_creates_portable_key_relative_to_storage_root(self) -> None:
        """새 이미지 경로는 운영체제와 무관한 저장 키로 변환합니다."""
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            image_path = root / "17" / "main.png"
            storage = sku_image_storage.SkuImageStorage(root)

            self.assertEqual(storage.storage_key(image_path), "17/main.png")


if __name__ == "__main__":
    unittest.main()
