"""Tests for the edited-object SKU recommendation job request."""

import collections.abc
import unittest
import unittest.mock
import uuid

import fastapi
import starlette.testclient

from app.api import tagging
from app.core import database, exception_handlers, request_context
from app.models.ai_job import AiJob, AiJobStatus, AiJobType
from app.models.scene_image import SceneImage
from app.repositories import ai_job_repository, scene_image_repository


class _FakeSession:  # pylint: disable=too-few-public-methods
    """추천 Job API에 주입할 세션 대역입니다."""


def _scene() -> SceneImage:
    """탐지 완료된 장면 이미지를 생성합니다."""
    return SceneImage(
        scene_image_id=7,
        user_id=1,
        image_url="/uploads/scene-images/scene.png",
        origin_name="scene.png",
        mime_type="image/png",
        file_size=1024,
        width_px=512,
        height_px=512,
        analysis_status="detected",
        analysis_error=None,
        object_metadata=[],
    )


def _job() -> AiJob:
    """대기 상태의 SKU 추천 Job을 생성합니다."""
    return AiJob(
        job_id=uuid.UUID("84b9eccf-8264-4f07-90a8-e1d4a2d2f704"),
        scene_image_id=7,
        job_type=AiJobType.RECOMMEND_SKU.value,
        status=AiJobStatus.PENDING.value,
        input_payload={},
    )


class SceneObjectUpdateApiTest(unittest.TestCase):
    """편집 객체를 DB 저장 없이 Job으로 넘기는 계약을 검증합니다."""

    def setUp(self) -> None:
        self.app = fastapi.FastAPI()
        self.app.add_middleware(request_context.RequestIdMiddleware)
        exception_handlers.register_exception_handlers(self.app)
        self.app.include_router(tagging.router)
        self.client = starlette.testclient.TestClient(self.app)

        self.session = _FakeSession()

        async def override_database_session() -> (
            collections.abc.AsyncIterator[_FakeSession]
        ):
            yield self.session

        self.app.dependency_overrides[database.get_database_session] = (
            override_database_session
        )

    def tearDown(self) -> None:
        """테스트별 의존성 재정의를 정리합니다."""
        self.app.dependency_overrides.clear()

    def test_enqueues_recommendation_without_persisting_objects(self) -> None:
        """편집 객체는 추천 Job payload로만 전달합니다."""
        request_body = {
            "objects": [
                {
                    "object_idx": 3,
                    "category": "의자",
                    "bbox_coord": {
                        "xmin": 120,
                        "ymin": 100,
                        "xmax": 600,
                        "ymax": 900,
                    },
                }
            ]
        }
        with (
            unittest.mock.patch.object(
                scene_image_repository,
                "get_scene_image",
                new=unittest.mock.AsyncMock(return_value=_scene()),
            ),
            unittest.mock.patch.object(
                ai_job_repository,
                "create_job",
                new=unittest.mock.AsyncMock(return_value=_job()),
            ) as create_job,
        ):
            response = self.client.post("/tagging/scenes/7", json=request_body)

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["data"]["scene_image_id"], 7)
        create_job.assert_awaited_once_with(
            self.session,
            7,
            AiJobType.RECOMMEND_SKU,
            input_payload={"objects": request_body["objects"]},
        )

    def test_rejects_an_invalid_bounding_box(self) -> None:
        """Reject an invalid bounding box through the common 422 response."""
        response = self.client.post(
            "/tagging/scenes/7",
            json={
                "objects": [
                    {
                        "object_idx": 0,
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
        """없는 장면 이미지는 추천 Job을 만들지 않고 404를 반환합니다."""
        with unittest.mock.patch.object(
            scene_image_repository,
            "get_scene_image",
            new=unittest.mock.AsyncMock(
                side_effect=scene_image_repository.SceneImageNotFoundError(999)
            ),
        ):
            response = self.client.post(
                "/tagging/scenes/999",
                json={
                    "objects": [
                        {
                            "object_idx": 0,
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
