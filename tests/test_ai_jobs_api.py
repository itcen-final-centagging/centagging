"""AI 작업 상태·결과 조회 API 계약을 검증합니다."""

import collections.abc
import datetime
import unittest
import uuid

import fastapi
import starlette.testclient

from app.api import ai_jobs
from app.core import database, exception_handlers, request_context
from app.models.ai_job import AiJob, AiJobStatus, AiJobType


class _FakeSession:  # pylint: disable=too-few-public-methods
    """AI 작업 단건 조회 결과를 제공하는 DB 세션 대역입니다."""

    def __init__(self, job: AiJob | None) -> None:
        self.job = job

    async def get(
        self,
        model: type[AiJob],
        job_id: uuid.UUID,
    ) -> AiJob | None:
        """모델과 UUID가 일치하면 준비된 작업을 반환합니다."""
        if model is not AiJob or self.job is None:
            return None
        if self.job.job_id != job_id:
            return None
        return self.job


def _job(status: AiJobStatus) -> AiJob:
    """API 응답 검증에 사용할 AI 작업을 생성합니다."""
    now = datetime.datetime(
        2026,
        8,
        18,
        12,
        30,
        tzinfo=datetime.timezone.utc,
    )
    return AiJob(
        job_id=uuid.UUID("9d6e18de-e981-42fc-84e4-9a06e1f64e98"),
        scene_image_id=17,
        job_type=AiJobType.DETECT_SCENE.value,
        status=status.value,
        attempt_count=1,
        max_attempts=3,
        result_payload=(
            {"detections": [{"label": "sofa"}]}
            if status is AiJobStatus.SUCCEEDED
            else None
        ),
        error_code=(
            "VERTEX_UNAVAILABLE" if status is AiJobStatus.FAILED else None
        ),
        error_message=(
            "AI 분석에 실패했습니다." if status is AiJobStatus.FAILED else None
        ),
        created_at=now,
        started_at=now,
        finished_at=(
            now
            if status in (AiJobStatus.SUCCEEDED, AiJobStatus.FAILED)
            else None
        ),
        updated_at=now,
    )


class AiJobApiTest(unittest.TestCase):
    """프론트엔드 폴링용 작업 조회 HTTP 계약을 검증합니다."""

    def setUp(self) -> None:
        """AI 작업 라우터와 테스트 애플리케이션을 구성합니다."""
        self.app = fastapi.FastAPI()
        self.app.add_middleware(request_context.RequestIdMiddleware)
        exception_handlers.register_exception_handlers(self.app)
        self.app.include_router(ai_jobs.router)
        self.client = starlette.testclient.TestClient(self.app)

    def tearDown(self) -> None:
        """테스트별 의존성 재정의를 제거합니다."""
        self.app.dependency_overrides.clear()

    def _set_job(self, job: AiJob | None) -> None:
        """상태 조회 API가 사용할 작업을 설정합니다."""
        session = _FakeSession(job)

        async def override_database_session() -> (
            collections.abc.AsyncIterator[_FakeSession]
        ):
            yield session

        self.app.dependency_overrides[database.get_database_session] = (
            override_database_session
        )

    def test_returns_pending_job_without_internal_worker_fields(self) -> None:
        """대기 작업은 Worker 내부 정보 없이 공개 상태만 반환합니다."""
        job = _job(AiJobStatus.PENDING)
        self._set_job(job)

        response = self.client.get(f"/ai-jobs/{job.job_id}")

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["job_id"], str(job.job_id))
        self.assertEqual(data["scene_image_id"], 17)
        self.assertEqual(data["job_type"], "DETECT_SCENE")
        self.assertEqual(data["status"], "PENDING")
        self.assertIsNone(data["result_payload"])
        self.assertNotIn("worker_id", data)
        self.assertNotIn("locked_at", data)
        self.assertNotIn("input_payload", data)

    def test_returns_succeeded_result_payload(self) -> None:
        """완료 작업은 프론트엔드가 사용할 분석 결과를 반환합니다."""
        job = _job(AiJobStatus.SUCCEEDED)
        self._set_job(job)

        response = self.client.get(f"/ai-jobs/{job.job_id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["status"], "SUCCEEDED")
        self.assertEqual(
            response.json()["data"]["result_payload"],
            {"detections": [{"label": "sofa"}]},
        )

    def test_returns_failed_error_details(self) -> None:
        """최종 실패 작업은 오류 코드와 사용자 메시지를 반환합니다."""
        job = _job(AiJobStatus.FAILED)
        self._set_job(job)

        response = self.client.get(f"/ai-jobs/{job.job_id}")

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["status"], "FAILED")
        self.assertEqual(data["error_code"], "VERTEX_UNAVAILABLE")
        self.assertEqual(data["error_message"], "AI 분석에 실패했습니다.")

    def test_returns_not_found_for_unknown_job(self) -> None:
        """존재하지 않는 작업 UUID는 공통 404 오류를 반환합니다."""
        self._set_job(None)

        response = self.client.get(f"/ai-jobs/{uuid.uuid4()}")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["status"], "error")

    def test_rejects_invalid_job_uuid(self) -> None:
        """UUID 형식이 아닌 경로 값은 422로 거부합니다."""
        self._set_job(None)

        response = self.client.get("/ai-jobs/not-a-uuid")

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
