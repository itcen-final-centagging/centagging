"""AI 작업 Worker의 단건 처리 흐름을 검증합니다."""

import pathlib
import tempfile
import typing
import unittest
import unittest.mock
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import config
from app.models.ai_job import AiJob, AiJobStatus, AiJobType
from app.models.scene_image import SceneImage
from app.repositories import ai_job_repository, scene_image_repository
from app.schemas.gemini_detection import (
    GeminiDetectionResult,
    GeminiRawDetection,
)
from app.schemas.tagging import DetectionResult, SceneImageInfo
from app.services import ai_job_worker_service, furniture_detection_service


class _FakeSession:  # pylint: disable=too-few-public-methods
    """Worker가 사용하는 rollback과 flush 호출을 기록합니다."""

    def __init__(self) -> None:
        self.rollback_count = 0
        self.flush_count = 0

    async def rollback(self) -> None:
        """실패 처리 전 트랜잭션 초기화를 기록합니다."""
        self.rollback_count += 1

    async def flush(self) -> None:
        """장면 상태가 작업 상태와 함께 저장될 준비를 기록합니다."""
        self.flush_count += 1


def _session(fake_session: _FakeSession) -> AsyncSession:
    """테스트 대역을 Repository 시그니처에 맞춰 반환합니다."""
    return typing.cast(AsyncSession, fake_session)


def _job(
    attempt_count: int = 1,
    max_attempts: int = 3,
    job_type: AiJobType = AiJobType.DETECT_SCENE,
) -> AiJob:
    """선점 완료된 AI 작업을 생성합니다."""
    return AiJob(
        job_id=uuid.UUID("6c1fc192-d2c7-4a13-ae8d-b778736f4cd0"),
        scene_image_id=42,
        job_type=job_type.value,
        status=AiJobStatus.RUNNING.value,
        input_payload={"image_url": "/uploads/scene-images/scene.png"},
        attempt_count=attempt_count,
        max_attempts=max_attempts,
    )


def _recommendation_objects() -> list[dict[str, object]]:
    """추천 Job이 전달받는 편집 객체 목록을 생성합니다."""
    return [
        {
            "object_idx": 4,
            "category": "chair",
            "bbox_coord": {
                "xmin": 200,
                "ymin": 100,
                "xmax": 800,
                "ymax": 700,
            },
        }
    ]


def _scene() -> SceneImage:
    """Worker가 분석할 장면 이미지 엔티티를 생성합니다."""
    return SceneImage(
        scene_image_id=42,
        user_id=7,
        image_url="/uploads/scene-images/scene.png",
        origin_name="scene.png",
        mime_type="image/png",
        file_size=5,
        width_px=512,
        height_px=512,
        analysis_status="pending",
        analysis_error=None,
        object_metadata=[],
    )


def _settings(storage_root: str) -> config.Settings:
    """Worker 파일 접근에 필요한 최소 설정을 생성합니다."""
    return config.Settings(
        gemini_api_key="test-key",
        gemini_vlm_model="test-model",
        gemini_embedding_model="test-embedding",
        mvp_login_id="mvp-user",
        mvp_login_password="password",
        image_storage_root=storage_root,
        sku_image_root="data/images",
        database=config.DatabaseSettings(
            name="centagging",
            username="centagging",
            password="password",
            host="db",
            port=5432,
        ),
    )


class ProcessNextAiJobTest(  # pylint: disable=too-many-instance-attributes
    unittest.IsolatedAsyncioTestCase
):
    """대기 작업 없음·성공·재시도·최종 실패를 검증합니다."""

    def setUp(self) -> None:
        """격리된 이미지 저장소와 DB 세션 대역을 준비합니다."""
        self.storage_directory = (
            tempfile.TemporaryDirectory()
        )  # pylint: disable=consider-using-with
        image_path = (
            pathlib.Path(self.storage_directory.name)
            / "scene-images"
            / "scene.png"
        )
        image_path.parent.mkdir(parents=True)
        image_path.write_bytes(b"image")
        self.fake_session = _FakeSession()
        self.session = _session(self.fake_session)
        self.settings = _settings(self.storage_directory.name)
        self.job = _job()
        self.scene = _scene()
        self.recommendation_result = DetectionResult(
            processing_status="DETECTED",
            scene_image=SceneImageInfo(
                scene_image_id=42,
                image_url="/uploads/scene-images/scene.png",
                origin_name="scene.png",
                mime_type="image/png",
                file_size=5,
                width_px=512,
                height_px=512,
            ),
            objects=[],
        )
        self.tagging_service = unittest.mock.Mock()
        self.tagging_service.get_sku_candidates = unittest.mock.AsyncMock(
            return_value=self.recommendation_result
        )

        self.claim_patch = unittest.mock.patch.object(
            ai_job_repository,
            "claim_next_job",
            new=unittest.mock.AsyncMock(return_value=self.job),
        )
        self.scene_patch = unittest.mock.patch.object(
            scene_image_repository,
            "get_scene_image",
            new=unittest.mock.AsyncMock(return_value=self.scene),
        )
        self.success_patch = unittest.mock.patch.object(
            ai_job_repository,
            "mark_job_succeeded",
            new=unittest.mock.AsyncMock(return_value=self.job),
        )
        self.failure_patch = unittest.mock.patch.object(
            ai_job_repository,
            "mark_job_failed",
            new=unittest.mock.AsyncMock(return_value=self.job),
        )
        self.detection_patch = unittest.mock.patch.object(
            furniture_detection_service,
            "detect_furniture_from_bytes",
            return_value=GeminiDetectionResult(
                detections=[
                    GeminiRawDetection(
                        category="chair",
                        bbox_coord={
                            "xmin": 200,
                            "ymin": 100,
                            "xmax": 800,
                            "ymax": 700,
                        },
                        evidence="chair shape",
                        confidence=0.9,
                    )
                ],
                processing_time_ms=10,
            ),
        )
        self.tagging_service_patch = unittest.mock.patch.object(
            ai_job_worker_service,
            "_build_tagging_service",
            return_value=self.tagging_service,
        )
        self.claim_mock = self.claim_patch.start()
        self.scene_mock = self.scene_patch.start()
        self.success_mock = self.success_patch.start()
        self.failure_mock = self.failure_patch.start()
        self.detection_mock = self.detection_patch.start()
        self.tagging_service_mock = self.tagging_service_patch.start()

    def tearDown(self) -> None:
        """패치와 임시 이미지 저장소를 정리합니다."""
        self.detection_patch.stop()
        self.tagging_service_patch.stop()
        self.failure_patch.stop()
        self.success_patch.stop()
        self.scene_patch.stop()
        self.claim_patch.stop()
        self.storage_directory.cleanup()

    async def test_returns_none_when_pending_job_does_not_exist(self) -> None:
        """대기 작업이 없으면 외부 분석이나 상태 변경을 수행하지 않습니다."""
        self.claim_mock.return_value = None

        result = await ai_job_worker_service.process_next_job(
            self.session, self.settings, "worker-1"
        )

        self.assertIsNone(result)
        self.scene_mock.assert_not_awaited()
        self.success_mock.assert_not_awaited()
        self.failure_mock.assert_not_awaited()
        self.detection_mock.assert_not_called()

    async def test_detects_scene_and_marks_job_succeeded(self) -> None:
        """탐지 결과를 장면과 작업 결과에 저장하고 성공 처리합니다."""
        result = await ai_job_worker_service.process_next_job(
            self.session, self.settings, "worker-1"
        )

        self.assertIs(result, self.job)
        self.assertEqual(self.scene.analysis_status, "detected")
        self.assertIsNone(self.scene.analysis_error)
        self.assertEqual(self.scene.object_metadata, [])
        self.assertEqual(self.fake_session.flush_count, 1)
        self.assertEqual(self.fake_session.rollback_count, 0)
        self.success_mock.assert_awaited_once()
        success_call = self.success_mock.await_args
        assert success_call is not None
        result_payload = success_call.args[2]
        self.assertEqual(result_payload["scene_image_id"], 42)
        self.assertEqual(
            result_payload["objects"][0],
            {
                "object_idx": 0,
                "category": "chair",
                "sub_category": None,
                "bbox_coord": {
                    "xmin": 200,
                    "ymin": 100,
                    "xmax": 800,
                    "ymax": 700,
                },
                "evidence": "chair shape",
                "confidence": 0.9,
            },
        )
        self.failure_mock.assert_not_awaited()

    async def test_requeues_failed_detection_when_attempts_remain(self) -> None:
        """탐지 실패에 재시도가 남으면 장면을 pending으로 유지합니다."""
        self.detection_mock.side_effect = RuntimeError("temporary error")

        await ai_job_worker_service.process_next_job(
            self.session, self.settings, "worker-1"
        )

        self.assertEqual(self.fake_session.rollback_count, 1)
        self.assertEqual(self.fake_session.flush_count, 1)
        self.assertEqual(self.scene.analysis_status, "pending")
        self.assertIsNone(self.scene.analysis_error)
        self.failure_mock.assert_awaited_once_with(
            self.session,
            self.job.job_id,
            "DETECT_SCENE_FAILED",
            "가구 탐지에 실패했습니다.",
        )
        self.success_mock.assert_not_awaited()

    async def test_marks_scene_failed_on_last_attempt(self) -> None:
        """마지막 탐지 실패는 장면과 작업을 최종 실패 상태로 전환합니다."""
        self.job.attempt_count = self.job.max_attempts
        self.detection_mock.side_effect = RuntimeError("permanent error")

        await ai_job_worker_service.process_next_job(
            self.session, self.settings, "worker-1"
        )

        self.assertEqual(self.scene.analysis_status, "failed")
        self.assertEqual(
            self.scene.analysis_error,
            "가구 탐지에 실패했습니다.",
        )
        self.failure_mock.assert_awaited_once()

    async def test_recommends_sku_and_marks_job_succeeded(self) -> None:
        """SKU 추천은 결과를 작업에만 저장하고 장면 상태는 유지합니다."""
        self.job = _job(job_type=AiJobType.RECOMMEND_SKU)
        self.job.input_payload = {"objects": _recommendation_objects()}
        self.claim_mock.return_value = self.job
        self.success_mock.return_value = self.job

        result = await ai_job_worker_service.process_next_job(
            self.session, self.settings, "worker-1"
        )

        self.assertIs(result, self.job)
        self.tagging_service_mock.assert_called_once_with(
            self.session,
            self.settings,
        )
        self.tagging_service.get_sku_candidates.assert_awaited_once()
        recommendation_call = self.tagging_service.get_sku_candidates.await_args
        assert recommendation_call is not None
        self.assertEqual(recommendation_call.args, (42,))
        objects = recommendation_call.kwargs["objects"]
        self.assertEqual(objects[0].object_idx, 4)
        self.assertEqual(objects[0].category, "chair")
        self.scene_mock.assert_not_awaited()
        self.success_mock.assert_awaited_once_with(
            self.session,
            self.job.job_id,
            self.recommendation_result.model_dump(mode="json"),
        )
        self.failure_mock.assert_not_awaited()

    async def test_preserves_object_indexes_from_job_payload(self) -> None:
        """추천 Job payload의 객체 인덱스를 서비스 호출까지 유지합니다."""
        self.job = _job(job_type=AiJobType.RECOMMEND_SKU)
        self.job.input_payload = {
            "objects": [
                *_recommendation_objects(),
                {
                    "object_idx": 9,
                    "category": "table",
                    "bbox_coord": {
                        "xmin": 0,
                        "ymin": 0,
                        "xmax": 100,
                        "ymax": 100,
                    },
                },
            ]
        }
        self.claim_mock.return_value = self.job

        await ai_job_worker_service.process_next_job(
            self.session, self.settings, "worker-1"
        )

        recommendation_call = self.tagging_service.get_sku_candidates.await_args
        assert recommendation_call is not None
        self.assertEqual(
            [
                object.object_idx
                for object in recommendation_call.kwargs["objects"]
            ],
            [4, 9],
        )

    async def test_requeues_failed_sku_recommendation(self) -> None:
        """추천 실패는 장면 탐지 상태를 바꾸지 않고 작업만 재시도합니다."""
        self.job = _job(job_type=AiJobType.RECOMMEND_SKU)
        self.job.input_payload = {"objects": _recommendation_objects()}
        self.claim_mock.return_value = self.job
        self.failure_mock.return_value = self.job
        self.scene.analysis_status = "detected"
        self.tagging_service.get_sku_candidates.side_effect = RuntimeError(
            "temporary error"
        )

        await ai_job_worker_service.process_next_job(
            self.session, self.settings, "worker-1"
        )

        self.assertEqual(self.fake_session.rollback_count, 1)
        self.assertEqual(self.scene.analysis_status, "detected")
        self.scene_mock.assert_not_awaited()
        self.failure_mock.assert_awaited_once_with(
            self.session,
            self.job.job_id,
            "RECOMMEND_SKU_FAILED",
            "SKU 추천에 실패했습니다.",
        )
        self.success_mock.assert_not_awaited()

    async def test_requeues_recommendation_after_rollback_expires_job(
        self,
    ) -> None:
        """롤백 뒤에도 사전에 보관한 job_id로 추천 작업 실패를 기록합니다."""
        self.job = _job(job_type=AiJobType.RECOMMEND_SKU)
        self.job.input_payload = {"objects": _recommendation_objects()}
        self.claim_mock.return_value = self.job
        self.tagging_service.get_sku_candidates.side_effect = RuntimeError(
            "temporary error"
        )
        original_rollback = self.fake_session.rollback

        async def expire_job_after_rollback() -> None:
            await original_rollback()
            self.job.__dict__.pop("job_id")

        self.fake_session.rollback = expire_job_after_rollback

        await ai_job_worker_service.process_next_job(
            self.session, self.settings, "worker-1"
        )

        self.failure_mock.assert_awaited_once_with(
            self.session,
            uuid.UUID("6c1fc192-d2c7-4a13-ae8d-b778736f4cd0"),
            "RECOMMEND_SKU_FAILED",
            "SKU 추천에 실패했습니다.",
        )


if __name__ == "__main__":
    unittest.main()
