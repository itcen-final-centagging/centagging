"""비동기 SKU 추천 작업 접수 API 계약을 검증합니다."""

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
    """추천 작업 접수 API의 의존성 대역입니다."""


def _scene(analysis_status: str = "detected") -> SceneImage:
    """추천 요청에 사용할 장면 이미지를 생성합니다."""
    return SceneImage(
        scene_image_id=17,
        user_id=7,
        image_url="/uploads/scene-images/scene.png",
        origin_name="scene.png",
        mime_type="image/png",
        file_size=10,
        width_px=512,
        height_px=512,
        analysis_status=analysis_status,
        analysis_error=None,
        object_metadata=[],
    )


def _job() -> AiJob:
    """접수 성공 응답에 사용할 대기 작업을 생성합니다."""
    return AiJob(
        job_id=uuid.UUID("77435d80-36cf-4be8-b7c9-d5a357743f41"),
        scene_image_id=17,
        job_type=AiJobType.RECOMMEND_SKU.value,
        status=AiJobStatus.PENDING.value,
        input_payload={},
    )


class SkuRecommendationJobApiTest(unittest.TestCase):
    """SKU 추천 작업 접수의 HTTP 계약을 검증합니다."""

    def setUp(self) -> None:
        """추천 작업 라우터와 DB 의존성 대역을 구성합니다."""
        self.session = _FakeSession()
        self.app = fastapi.FastAPI()
        self.app.add_middleware(request_context.RequestIdMiddleware)
        exception_handlers.register_exception_handlers(self.app)
        self.app.include_router(tagging.router)
        self.client = starlette.testclient.TestClient(self.app)

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

    def test_enqueues_recommendation_job_for_detected_scene(self) -> None:
        """탐지 완료 장면은 202와 RECOMMEND_SKU 작업 UUID를 반환합니다."""
        with (
            unittest.mock.patch.object(
                scene_image_repository,
                "get_scene_image",
                new=unittest.mock.AsyncMock(return_value=_scene()),
            ) as get_scene,
            unittest.mock.patch.object(
                ai_job_repository,
                "create_job",
                new=unittest.mock.AsyncMock(return_value=_job()),
            ) as create_job,
        ):
            response = self.client.post("/tagging/scenes/17/recommendations")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(
            response.json()["data"],
            {
                "scene_image_id": 17,
                "job_id": "77435d80-36cf-4be8-b7c9-d5a357743f41",
                "status": "PENDING",
            },
        )
        get_scene.assert_awaited_once_with(self.session, 17)
        create_job.assert_awaited_once_with(
            self.session,
            17,
            AiJobType.RECOMMEND_SKU,
        )

    def test_rejects_recommendation_before_detection_completes(self) -> None:
        """탐지 중인 장면에는 빈 추천 작업을 만들지 않습니다."""
        with (
            unittest.mock.patch.object(
                scene_image_repository,
                "get_scene_image",
                new=unittest.mock.AsyncMock(return_value=_scene("pending")),
            ),
            unittest.mock.patch.object(
                ai_job_repository,
                "create_job",
                new=unittest.mock.AsyncMock(),
            ) as create_job,
        ):
            response = self.client.post("/tagging/scenes/17/recommendations")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["error"]["message"],
            "가구 탐지가 완료된 이미지에 대해서만 SKU 추천을 요청할 수 있습니다.",
        )
        create_job.assert_not_awaited()

    def test_returns_404_for_unknown_scene(self) -> None:
        """없는 장면 이미지는 추천 작업을 만들지 않고 404를 반환합니다."""
        with unittest.mock.patch.object(
            scene_image_repository,
            "get_scene_image",
            new=unittest.mock.AsyncMock(
                side_effect=scene_image_repository.SceneImageNotFoundError(17)
            ),
        ):
            response = self.client.post("/tagging/scenes/17/recommendations")

        self.assertEqual(response.status_code, 404)

    def test_returns_409_when_recommendation_job_is_already_active(
        self,
    ) -> None:
        """같은 장면에 진행 중인 추천 작업이 있으면 중복 접수를 거부합니다."""
        with (
            unittest.mock.patch.object(
                scene_image_repository,
                "get_scene_image",
                new=unittest.mock.AsyncMock(return_value=_scene()),
            ),
            unittest.mock.patch.object(
                ai_job_repository,
                "create_job",
                new=unittest.mock.AsyncMock(
                    side_effect=ai_job_repository.ActiveAiJobExistsError(17)
                ),
            ),
        ):
            response = self.client.post("/tagging/scenes/17/recommendations")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["error"]["message"],
            "이미 진행 중인 SKU 추천 작업이 있습니다.",
        )

    def test_legacy_sync_recommendation_endpoint_is_not_available(self) -> None:
        """추천 API는 동기 GET이 아닌 비동기 작업 접수만 제공합니다."""
        response = self.client.get("/tagging/scenes/17")

        self.assertEqual(response.status_code, 405)


if __name__ == "__main__":
    unittest.main()
