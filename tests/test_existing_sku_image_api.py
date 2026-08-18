"""기존 SKU 다중 이미지 등록 API 계약을 검증합니다."""

import io
import types
import unittest
import unittest.mock

import fastapi
import PIL.Image
import starlette.testclient

from app import dependencies
from app.api import sku
from app.core import database, exception_handlers, request_context


def _image_bytes() -> bytes:
    """multipart 요청에 넣을 유효한 PNG 바이트를 만듭니다."""
    buffer = io.BytesIO()
    PIL.Image.new("RGB", (32, 32), color="white").save(buffer, format="PNG")
    return buffer.getvalue()


class ExistingSkuImageApiTest(unittest.TestCase):
    """여러 제품 이미지를 기존 SKU에 연결하는 계약을 검증합니다."""

    def setUp(self) -> None:
        self.app = fastapi.FastAPI()
        self.app.add_middleware(request_context.RequestIdMiddleware)
        exception_handlers.register_exception_handlers(self.app)
        self.app.include_router(sku.router)
        self.session = object()

        async def override_database_session():
            yield self.session

        self.app.dependency_overrides[database.get_database_session] = (
            override_database_session
        )
        self.app.dependency_overrides[dependencies.require_super_admin] = (
            lambda: {
                "role": "SUPER_ADMIN",
                "user_id": 1,
                "user_name": "최종 관리자",
            }
        )
        self.client = starlette.testclient.TestClient(self.app)

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()

    def test_adds_multiple_images_to_existing_sku(self) -> None:
        """한 SKU에 여러 이미지를 같은 유형으로 한 번에 연결합니다."""
        existing_sku = types.SimpleNamespace(sku_id=17, sku_code="CHR-2041")
        created_images = [
            types.SimpleNamespace(
                sku_image_id=31,
                image_type="STYLING",
                image_url="/uploads/sku/CHR-2041/one.png",
            ),
            types.SimpleNamespace(
                sku_image_id=32,
                image_type="STYLING",
                image_url="/uploads/sku/CHR-2041/two.png",
            ),
        ]
        with (
            unittest.mock.patch.object(
                sku.sku_service,
                "find_sku_by_code",
                new=unittest.mock.AsyncMock(return_value=existing_sku),
            ) as find_sku,
            unittest.mock.patch.object(
                sku.sku_service,
                "save_uploaded_image",
                side_effect=[image.image_url for image in created_images],
            ),
            unittest.mock.patch.object(
                sku.sku_service,
                "add_sku_images",
                new=unittest.mock.AsyncMock(return_value=created_images),
            ) as add_images,
        ):
            response = self.client.post(
                "/sku/CHR-2041/images",
                data={"image_type": "STYLING"},
                files=[
                    ("images", ("one.png", _image_bytes(), "image/png")),
                    ("images", ("two.png", _image_bytes(), "image/png")),
                ],
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "success")
        self.assertEqual(
            response.json()["data"],
            {
                "sku_id": 17,
                "sku_code": "CHR-2041",
                "images": [
                    {
                        "sku_image_id": 31,
                        "image_url": "/uploads/sku/CHR-2041/one.png",
                        "image_type": "STYLING",
                    },
                    {
                        "sku_image_id": 32,
                        "image_url": "/uploads/sku/CHR-2041/two.png",
                        "image_type": "STYLING",
                    },
                ],
            },
        )
        find_sku.assert_awaited_once_with(self.session, "CHR-2041")
        add_images.assert_awaited_once_with(
            self.session,
            sku_id=17,
            image_urls=[
                "/uploads/sku/CHR-2041/one.png",
                "/uploads/sku/CHR-2041/two.png",
            ],
            image_type="STYLING",
        )

    def test_returns_not_found_when_sku_does_not_exist(self) -> None:
        """없는 SKU에는 이미지를 저장하지 않습니다."""
        with unittest.mock.patch.object(
            sku.sku_service,
            "find_sku_by_code",
            new=unittest.mock.AsyncMock(return_value=None),
        ):
            response = self.client.post(
                "/sku/MISSING/images",
                files={"images": ("one.png", _image_bytes(), "image/png")},
            )

        self.assertEqual(response.status_code, 404)

    def test_rejects_more_than_twenty_images(self) -> None:
        """큐를 보호하기 위해 한 번의 배치 파일 수를 제한합니다."""
        existing_sku = types.SimpleNamespace(sku_id=17, sku_code="CHR-2041")
        with unittest.mock.patch.object(
            sku.sku_service,
            "find_sku_by_code",
            new=unittest.mock.AsyncMock(return_value=existing_sku),
        ) as find_sku:
            response = self.client.post(
                "/sku/CHR-2041/images",
                files=[
                    ("images", (f"{index}.png", _image_bytes(), "image/png"))
                    for index in range(21)
                ],
            )

        self.assertEqual(response.status_code, 422)
        find_sku.assert_not_awaited()
