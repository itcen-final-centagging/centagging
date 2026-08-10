"""이미지 업로드 유효성 검증 서비스 테스트입니다."""

import io
import json
import pathlib
import tempfile
import unittest
import unittest.mock

import fastapi
import PIL.Image
import starlette.datastructures
import starlette.testclient

from app.api import scene_images
from app.core import config, database
from app.schemas.gemini_detection import (
    GeminiDetectionResult,
    GeminiRawDetection,
)
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


class _FakeInsertResult:
    """업로드 API 테스트용 INSERT 결과입니다."""

    def __init__(self, scene_image_id: int = 42) -> None:
        self.scene_image_id = scene_image_id

    def scalar_one(self) -> int:
        """저장된 이미지 ID를 반환합니다."""
        return self.scene_image_id


class _FakeUserLookupResult:
    """고정 사용자 조회 결과입니다."""

    def __init__(self, user_id: int | None = 7) -> None:
        self.user_id = user_id

    def scalar_one_or_none(self) -> int | None:
        """고정 로그인 ID로 조회한 사용자 ID를 반환합니다."""
        return self.user_id


class _FakeSession:
    """업로드 API 테스트용 비동기 DB 세션입니다."""

    def __init__(
        self,
        execute_error: Exception | None = None,
        commit_error: Exception | None = None,
        user_id: int | None = 7,
    ) -> None:
        self.execute_error = execute_error
        self.commit_error = commit_error
        self.user_id = user_id
        self.execute_parameters: dict[str, object] | None = None
        self.analysis_update_parameters: dict[str, object] | None = None
        self.user_lookup_parameters: dict[str, object] | None = None
        self.rollback_called = False

    async def execute(
        self, _statement: object, parameters: dict[str, object]
    ) -> _FakeInsertResult | _FakeUserLookupResult:
        """고정 사용자를 조회하거나 INSERT를 기록합니다."""
        if "SELECT user_id" in str(_statement):
            self.user_lookup_parameters = parameters
            return _FakeUserLookupResult(user_id=self.user_id)
        if "UPDATE scene_image" in str(_statement):
            self.analysis_update_parameters = parameters
            return _FakeInsertResult()
        self.execute_parameters = parameters
        if self.execute_error is not None:
            raise self.execute_error
        return _FakeInsertResult()

    async def commit(self) -> None:
        """commit을 수행하거나 설정된 커밋 오류를 발생시킵니다."""
        if self.commit_error is not None:
            raise self.commit_error

    async def rollback(self) -> None:
        """rollback 호출 여부를 기록합니다."""
        self.rollback_called = True


class UploadSceneImageApiTest(unittest.TestCase):
    """multipart 이미지 업로드 API 계약을 검증합니다."""

    def setUp(self) -> None:
        """격리된 저장소와 테스트용 DB 세션을 준비합니다."""
        self.storage_directory = tempfile.TemporaryDirectory()
        self.session = _FakeSession()
        self.app = fastapi.FastAPI()
        self.app.include_router(scene_images.router)

        async def override_database_session():
            yield self.session

        self.app.dependency_overrides[database.get_database_session] = (
            override_database_session
        )
        settings = config.Settings(
            gemini_api_key="",
            gemini_vlm_model="",
            gemini_embedding_model="",
            mvp_login_id="mvp-user",
            mvp_login_password="",
            image_storage_root=self.storage_directory.name,
            database=config.DatabaseSettings(
                name="",
                username="",
                password="",
                host="",
                port=5432,
            ),
        )
        self.settings_patch = unittest.mock.patch.object(
            config, "get_settings", return_value=settings
        )
        self.settings_patch.start()
        detection_result = GeminiDetectionResult(
            detections=[
                GeminiRawDetection(
                    label="chair",
                    box_2d=[100, 200, 700, 800],
                    evidence="chair shape",
                    confidence=0.9,
                )
            ],
            processing_time_ms=10,
        )
        self.detection_patch = unittest.mock.patch.object(
            scene_images.furniture_detection_service,
            "detect_furniture_from_bytes",
            return_value=detection_result,
        )
        self.detection_patch.start()
        self.client = starlette.testclient.TestClient(self.app)

    def tearDown(self) -> None:
        """테스트용 저장소와 설정 패치를 정리합니다."""
        self.detection_patch.stop()
        self.settings_patch.stop()
        self.storage_directory.cleanup()

    def _post_valid_image(self) -> object:
        """유효한 이미지만 업로드합니다."""
        return self.client.post(
            "/tagging",
            files={
                "file": (
                    "scene.png",
                    _image_bytes("PNG"),
                    "image/png",
                )
            },
        )

    def test_returns_metadata_for_valid_multipart_upload(self) -> None:
        """유효한 multipart 업로드에 검증 결과를 반환합니다."""
        response = self._post_valid_image()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "validated")
        self.assertEqual(response.json()["image"]["mime_type"], "image/png")
        self.assertEqual(response.json()["scene_image_id"], 42)
        assert self.session.execute_parameters is not None
        self.assertEqual(
            self.session.user_lookup_parameters,
            {"login_id": "mvp-user"},
        )
        self.assertEqual(self.session.execute_parameters["user_id"], 7)
        self.assertEqual(
            self.session.execute_parameters["origin_name"], "scene.png"
        )
        self.assertEqual(
            self.session.execute_parameters["mime_type"], "image/png"
        )
        self.assertEqual(self.session.execute_parameters["width_px"], 512)
        self.assertEqual(self.session.execute_parameters["height_px"], 512)
        image_url = str(self.session.execute_parameters["image_url"])
        self.assertTrue(image_url.startswith("/uploads/scene-images/"))
        stored_file = pathlib.Path(
            self.storage_directory.name
        ) / image_url.removeprefix("/uploads/")
        self.assertTrue(stored_file.is_file())
        self.assertEqual(
            self.session.execute_parameters["analysis_status"], "pending"
        )
        self.assertIsNone(self.session.execute_parameters["analysis_error"])
        assert self.session.analysis_update_parameters is not None
        self.assertEqual(
            json.loads(
                str(self.session.analysis_update_parameters["bbox_coord"])
            ),
            [
                {
                    "xmin": 200,
                    "ymin": 100,
                    "xmax": 800,
                    "ymax": 700,
                }
            ],
        )

    def test_returns_validation_error_for_invalid_upload(self) -> None:
        """디코딩할 수 없는 multipart 업로드를 거부합니다."""
        response = self.client.post(
            "/tagging",
            files={"file": ("fake.jpg", b"not an image", "image/jpeg")},
        )

        self.assertEqual(response.status_code, 422)
        self.assertIsNone(self.session.execute_parameters)
        self.assertEqual(
            list(pathlib.Path(self.storage_directory.name).rglob("*")), []
        )

    def test_rejects_missing_fixed_user_before_saving_file(self) -> None:
        """서버의 고정 사용자를 찾을 수 없으면 파일을 저장하지 않습니다."""
        self.session = _FakeSession(user_id=None)

        response = self._post_valid_image()

        self.assertEqual(response.status_code, 500)
        self.assertIsNone(self.session.execute_parameters)
        self.assertEqual(
            list(pathlib.Path(self.storage_directory.name).rglob("*")), []
        )

    def test_returns_500_without_db_registration_when_file_save_fails(
        self,
    ) -> None:
        """파일 저장 실패 시 DB 등록을 시도하지 않습니다."""
        with unittest.mock.patch.object(
            scene_images, "_save_image", side_effect=OSError("disk full")
        ):
            response = self._post_valid_image()

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json()["detail"], scene_images.UPLOAD_ERROR_MESSAGE
        )
        self.assertIsNone(self.session.execute_parameters)

    def test_removes_file_when_db_registration_fails(self) -> None:
        """DB 등록 실패 시 이미 저장한 파일을 삭제합니다."""
        self.session = _FakeSession(
            execute_error=RuntimeError("db unavailable")
        )

        response = self._post_valid_image()

        self.assertEqual(response.status_code, 500)
        self.assertTrue(self.session.rollback_called)
        self.assertEqual(
            [
                path
                for path in pathlib.Path(self.storage_directory.name).rglob("*")
                if path.is_file()
            ],
            [],
        )

    def test_removes_file_when_db_commit_fails(self) -> None:
        """DB commit 실패 시 이미 저장한 파일을 삭제합니다."""
        self.session = _FakeSession(commit_error=RuntimeError("commit failed"))

        response = self._post_valid_image()

        self.assertEqual(response.status_code, 500)
        self.assertTrue(self.session.rollback_called)
        self.assertEqual(
            [
                path
                for path in pathlib.Path(self.storage_directory.name).rglob("*")
                if path.is_file()
            ],
            [],
        )


if __name__ == "__main__":
    unittest.main()
