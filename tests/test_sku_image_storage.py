"""SKU 이미지 저장 경로와 공개 URL 변환 테스트입니다."""

import io
import pathlib
import tempfile
import unittest

import fastapi
import fastapi.staticfiles
import starlette.testclient
from PIL import Image

from app.services import image_processing_service, sku_image_storage


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

    def test_reads_image_from_public_url(self) -> None:
        """공개 URL도 내부 저장 키로 되돌려 읽을 수 있습니다."""
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            image_path = root / "17" / "main.png"
            image_path.parent.mkdir()
            Image.new("RGB", (20, 10), color="white").save(image_path)
            storage = sku_image_storage.SkuImageStorage(root)

            image_bytes = storage.read_jpeg("/sku-images/17/main.png")

            self.assertIsNotNone(image_bytes)
            with Image.open(io.BytesIO(image_bytes)) as image:
                self.assertEqual(image.format, "JPEG")
                self.assertEqual(image.size, (20, 10))

    def test_preserves_uploaded_image_public_url(self) -> None:
        """업로드 API가 저장한 공개 URL은 다른 마운트 경로로 바꾸지 않습니다."""
        storage = sku_image_storage.SkuImageStorage("data/images")

        public_url = storage.public_url("/uploads/sku/SKU-17/main.png")

        self.assertEqual(public_url, "/uploads/sku/SKU-17/main.png")

    def test_reads_uploaded_image_from_upload_storage_root(self) -> None:
        """업로드 공개 URL은 업로드 저장 루트에서 읽습니다."""
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            sku_root = root / "catalog"
            upload_root = root / "uploads"
            image_path = upload_root / "sku" / "SKU-17" / "main.png"
            image_path.parent.mkdir(parents=True)
            Image.new("RGB", (20, 10), color="white").save(image_path)

            image_bytes = image_processing_service.read_sku_image_bytes(
                "/uploads/sku/SKU-17/main.png",
                str(sku_root),
                str(upload_root),
            )

            self.assertIsNotNone(image_bytes)
            with Image.open(io.BytesIO(image_bytes)) as image:
                self.assertEqual(image.format, "JPEG")
                self.assertEqual(image.size, (20, 10))

    def test_serves_image_from_generated_public_url(self) -> None:
        """생성된 공개 URL로 SKU 이미지에 접근할 수 있습니다."""
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            image_path = root / "17" / "main.png"
            image_path.parent.mkdir()
            Image.new("RGB", (20, 10), color="white").save(image_path)
            storage = sku_image_storage.SkuImageStorage(root)
            app = fastapi.FastAPI()
            app.mount(
                "/sku-images",
                fastapi.staticfiles.StaticFiles(directory=root),
            )
            client = starlette.testclient.TestClient(app)

            response = client.get(
                storage.public_url(r"data\images\17\main.png")
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["content-type"], "image/png")
            self.assertEqual(response.content, image_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
