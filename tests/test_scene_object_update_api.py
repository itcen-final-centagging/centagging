"""Tests for the transient scene-object recommendation request."""

import unittest
from unittest import mock

import fastapi
import starlette.testclient

from app.api import tagging
from app.core import exception_handlers, request_context
from app.repositories.scene_image_repository import SceneImageNotFoundError
from app.schemas.tagging import DetectionResult, SceneImageInfo


class SceneObjectUpdateApiTest(unittest.TestCase):
    """Validate the existing POST route without persisting object metadata."""

    def setUp(self) -> None:
        self.app = fastapi.FastAPI()
        self.app.add_middleware(request_context.RequestIdMiddleware)
        exception_handlers.register_exception_handlers(self.app)
        self.app.include_router(tagging.router)
        self.client = starlette.testclient.TestClient(self.app)

        self.tagging_service = mock.Mock()
        self.tagging_service.get_sku_candidates = mock.AsyncMock(
            return_value=DetectionResult(
                processing_status="DETECTED",
                scene_image=SceneImageInfo(
                    scene_image_id=7,
                    image_url="/uploads/scene-images/scene.png",
                    origin_name="scene.png",
                    mime_type="image/png",
                    file_size=1024,
                    width_px=512,
                    height_px=512,
                ),
                objects=[],
            )
        )
        self.app.dependency_overrides[tagging.get_tagging_service] = (
            lambda: self.tagging_service
        )

    def test_returns_recommendations_without_persisting_objects(self) -> None:
        """Pass edited objects to the service and return its transient result."""
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
                "processing_status": "DETECTED",
                "scene_image": {
                    "scene_image_id": 7,
                    "image_url": "/uploads/scene-images/scene.png",
                    "origin_name": "scene.png",
                    "mime_type": "image/png",
                    "file_size": 1024,
                    "width_px": 512,
                    "height_px": 512,
                },
                "objects": [],
            },
        )
        self.tagging_service.get_sku_candidates.assert_awaited_once()
        self.assertEqual(
            self.tagging_service.get_sku_candidates.await_args.args[0],
            7,
        )
        request_objects = (
            self.tagging_service.get_sku_candidates.await_args.kwargs["objects"]
        )
        self.assertEqual(request_objects[0].category, "의자")
        self.assertEqual(request_objects[0].bbox_coord.xmin, 120)

    def test_rejects_an_invalid_bounding_box(self) -> None:
        """Reject an invalid bounding box through the common 422 response."""
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
        """Map a missing scene raised by the transient recommendation service."""
        self.tagging_service.get_sku_candidates.side_effect = (
            SceneImageNotFoundError(999)
        )
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
