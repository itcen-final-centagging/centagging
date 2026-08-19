"""편집된 탐지 객체 저장 API의 계약을 검증합니다."""

import unittest
from unittest import mock

import fastapi
import starlette.testclient

from app.api import tagging
from app.core import exception_handlers, request_context
from app.repositories.scene_image_repository import SceneImageNotFoundError


class SceneObjectUpdateApiTest(unittest.TestCase):
    """바운딩 박스·카테고리 편집 저장 API를 검증합니다."""

    def setUp(self) -> None:
        self.app = fastapi.FastAPI()
        self.app.add_middleware(request_context.RequestIdMiddleware)
        exception_handlers.register_exception_handlers(self.app)
        self.app.include_router(tagging.router)
        self.client = starlette.testclient.TestClient(self.app)

    def test_persists_reindexed_objects(self) -> None:
        """프론트의 최종 객체 목록을 그대로 저장 레이어에 전달합니다."""
        with mock.patch(
            "app.api.tagging.scene_image_repository.update_scene_object_metadata",
            new_callable=mock.AsyncMock,
        ) as update_objects:
            response = self.client.post(
                "/tagging/scenes/7",
                json={
                    "objects": [
                        {
                            "category": "의자",
                            "bbox_coord": {
                                "xmin": 120,
                                "ymin": 100,
                                "xmax": 600,
                                "ymax": 900,
                            },
                        }
                    ]
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["data"],
            {
                "object_count": 1,
                "processing_status": "DETECTED",
            },
        )
        update_objects.assert_awaited_once()
        self.assertEqual(update_objects.await_args.args[1], 7)
        self.assertEqual(
            update_objects.await_args.args[2][0]["category"], "의자"
        )

    def test_rejects_an_invalid_bounding_box(self) -> None:
        """크롭할 수 없는 역방향 좌표는 공통 422 오류로 반환합니다."""
        response = self.client.post(
            "/tagging/scenes/7",
            json={
                "objects": [
                    {
                        "category": "의자",
                        "bbox_coord": {
                            "xmin": 900,
                            "ymin": 100,
                            "xmax": 200,
                            "ymax": 800,
                        },
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "VALIDATION_ERROR")

    def test_returns_404_for_an_unknown_scene(self) -> None:
        """존재하지 않는 장면 이미지는 404로 구분합니다."""
        with mock.patch(
            "app.api.tagging.scene_image_repository.update_scene_object_metadata",
            new_callable=mock.AsyncMock,
            side_effect=SceneImageNotFoundError(999),
        ):
            response = self.client.post(
                "/tagging/scenes/999",
                json={
                    "objects": [
                        {
                            "category": "의자",
                            "bbox_coord": {
                                "xmin": 100,
                                "ymin": 100,
                                "xmax": 300,
                                "ymax": 300,
                            },
                        }
                    ]
                },
            )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "RESOURCE_NOT_FOUND")
