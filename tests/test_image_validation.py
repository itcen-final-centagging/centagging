"""이미지 업로드 유효성 검증 서비스 테스트입니다."""

import io
import unittest

import fastapi
import PIL.Image
import starlette.datastructures
import starlette.testclient

from app.api import scene_images
from app.services import image_validation


def _image_bytes(
    image_format: str,
    size: tuple[int, int] = (512, 512),
) -> bytes:
    """테스트용 단색 이미지를 바이트로 생성합니다."""
    buffer = io.BytesIO()
    PIL.Image.new("RGB", size).save(buffer, format=image_format)
    return buffer.getvalue()


def _upload(
    filename: str,
    content: bytes,
    mime_type: str,
) -> fastapi.UploadFile:
    """테스트용 UploadFile을 생성합니다."""
    return fastapi.UploadFile(
        filename=filename,
        file=io.BytesIO(content),
        headers=starlette.datastructures.Headers({"content-type": mime_type}),
    )


class ValidateImageTest(unittest.IsolatedAsyncioTestCase):
    """업로드 이미지 허용 조건을 검증합니다."""

    async def test_accepts_valid_jpeg(self) -> None:
        """실제 JPEG 파일을 허용합니다."""
        content = _image_bytes("JPEG")

        result = await image_validation.validate_image(
            _upload("scene.jpg", content, "image/jpeg")
        )

        self.assertEqual(result.metadata.mime_type, "image/jpeg")
        self.assertEqual(
            (result.metadata.width_px, result.metadata.height_px),
            (512, 512),
        )
        self.assertEqual(result.metadata.file_size, len(content))

    async def test_accepts_valid_png(self) -> None:
        """실제 PNG 파일을 허용합니다."""
        result = await image_validation.validate_image(
            _upload("scene.png", _image_bytes("PNG"), "image/png")
        )

        self.assertEqual(result.metadata.mime_type, "image/png")

    async def test_rejects_unsupported_declared_mime_type(self) -> None:
        """허용 목록에 없는 선언 MIME 타입을 거부합니다."""
        with self.assertRaises(image_validation.ImageValidationError) as caught:
            await image_validation.validate_image(
                _upload("scene.webp", b"data", "image/webp")
            )

        self.assertEqual(caught.exception.status_code, 415)

    async def test_rejects_invalid_image_bytes(self) -> None:
        """이미지로 디코딩할 수 없는 파일을 거부합니다."""
        with self.assertRaises(image_validation.ImageValidationError):
            await image_validation.validate_image(
                _upload("fake.jpg", b"not an image", "image/jpeg")
            )

    async def test_rejects_mime_type_mismatch(self) -> None:
        """실제 이미지 형식과 선언 MIME 타입이 다르면 거부합니다."""
        with self.assertRaises(image_validation.ImageValidationError) as caught:
            await image_validation.validate_image(
                _upload("fake.jpg", _image_bytes("PNG"), "image/jpeg")
            )

        self.assertEqual(caught.exception.status_code, 415)

    async def test_accepts_file_exactly_ten_megabytes(self) -> None:
        """정확히 10MB인 유효한 이미지 파일을 허용합니다."""
        content = _image_bytes("PNG")
        content += b"0" * (image_validation.MAX_FILE_SIZE - len(content))

        result = await image_validation.validate_image(
            _upload("maximum.png", content, "image/png")
        )

        self.assertEqual(
            result.metadata.file_size,
            image_validation.MAX_FILE_SIZE,
        )

    async def test_rejects_file_larger_than_ten_megabytes(self) -> None:
        """10MB를 초과하는 파일을 디코딩 전에 거부합니다."""
        oversized = b"0" * (image_validation.MAX_FILE_SIZE + 1)

        with self.assertRaises(image_validation.ImageValidationError) as caught:
            await image_validation.validate_image(
                _upload("large.jpg", oversized, "image/jpeg")
            )

        self.assertEqual(caught.exception.status_code, 413)


class UploadSceneImageApiTest(unittest.TestCase):
    """multipart 이미지 업로드 API 계약을 검증합니다."""

    @classmethod
    def setUpClass(cls) -> None:
        """DB 생명주기 없이 업로드 라우터만 포함한 앱을 생성합니다."""
        app = fastapi.FastAPI()
        app.include_router(scene_images.router)
        cls.client = starlette.testclient.TestClient(app)

    def test_returns_metadata_for_valid_multipart_upload(self) -> None:
        """유효한 multipart 업로드에 검증 결과를 반환합니다."""
        response = self.client.post(
            "/tagging",
            files={
                "file": (
                    "scene.png",
                    _image_bytes("PNG"),
                    "image/png",
                )
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "validated")
        self.assertEqual(response.json()["image"]["mime_type"], "image/png")

    def test_returns_validation_error_for_invalid_upload(self) -> None:
        """디코딩할 수 없는 multipart 업로드를 거부합니다."""
        response = self.client.post(
            "/tagging",
            files={"file": ("fake.jpg", b"not an image", "image/jpeg")},
        )

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
