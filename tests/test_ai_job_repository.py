"""AI 작업 생성·조회 Repository의 상태 저장 규격을 검증합니다."""

import typing
import unittest
import uuid

import sqlalchemy
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_job import AiJob, AiJobStatus, AiJobType
from app.repositories import ai_job_repository


class _ConstraintDiagnostic:  # pylint: disable=too-few-public-methods
    """PostgreSQL 오류의 제약조건 진단 정보를 표현합니다."""

    def __init__(self, constraint_name: str) -> None:
        self.constraint_name = constraint_name


class _DatabaseError(Exception):
    """제약조건 이름을 포함하는 PostgreSQL 오류 대역입니다."""

    def __init__(self, constraint_name: str) -> None:
        super().__init__(constraint_name)
        self.diag = _ConstraintDiagnostic(constraint_name)


class _FakeSession:
    """AI 작업 저장과 조회 동작을 기록하는 세션 대역입니다."""

    def __init__(
        self,
        stored_job: AiJob | None = None,
        commit_error: sqlalchemy.exc.IntegrityError | None = None,
    ) -> None:
        self.stored_job = stored_job
        self.commit_error = commit_error
        self.added_job: AiJob | None = None
        self.committed = False
        self.rolled_back = False

    def add(self, job: AiJob) -> None:
        """세션에 추가된 작업을 기록합니다."""
        self.added_job = job

    async def commit(self) -> None:
        """커밋하거나 설정된 무결성 오류를 발생시킵니다."""
        if self.commit_error is not None:
            raise self.commit_error
        self.committed = True

    async def rollback(self) -> None:
        """롤백 호출 여부를 기록합니다."""
        self.rolled_back = True

    async def get(self, model: type[AiJob], job_id: uuid.UUID) -> AiJob | None:
        """저장된 작업의 UUID가 일치하면 반환합니다."""
        if model is not AiJob or self.stored_job is None:
            return None
        if self.stored_job.job_id != job_id:
            return None
        return self.stored_job


def _session(fake_session: _FakeSession) -> AsyncSession:
    """테스트 세션 대역을 Repository 타입으로 변환합니다."""
    return typing.cast(AsyncSession, fake_session)


class CreateAiJobTest(unittest.IsolatedAsyncioTestCase):
    """AI 작업 생성 규칙을 검증합니다."""

    async def test_creates_pending_job_with_copied_payload(self) -> None:
        """대기 상태와 독립된 입력값으로 작업을 생성합니다."""
        fake_session = _FakeSession()
        payload = {"object_indexes": [0, 2]}

        job = await ai_job_repository.create_job(
            _session(fake_session),
            scene_image_id=17,
            job_type=AiJobType.RECOMMEND_SKU,
            input_payload=payload,
        )

        self.assertIs(fake_session.added_job, job)
        self.assertTrue(fake_session.committed)
        self.assertIsInstance(job.job_id, uuid.UUID)
        self.assertEqual(job.scene_image_id, 17)
        self.assertEqual(job.job_type, "RECOMMEND_SKU")
        self.assertEqual(job.status, AiJobStatus.PENDING.value)
        self.assertEqual(job.input_payload, payload)
        self.assertIsNot(job.input_payload, payload)
        self.assertEqual(job.max_attempts, 3)

    async def test_rejects_invalid_max_attempts_before_saving(self) -> None:
        """실행할 수 없는 최대 시도 횟수는 DB 저장 전에 거부합니다."""
        fake_session = _FakeSession()

        with self.assertRaisesRegex(ValueError, "at least 1"):
            await ai_job_repository.create_job(
                _session(fake_session),
                scene_image_id=17,
                job_type=AiJobType.DETECT_SCENE,
                max_attempts=0,
            )

        self.assertIsNone(fake_session.added_job)
        self.assertFalse(fake_session.committed)

    async def test_rolls_back_duplicate_active_job(self) -> None:
        """활성 작업 유니크 제약 위반을 도메인 오류로 변환합니다."""
        database_error = _DatabaseError("uq_ai_job_active_scene_type")
        integrity_error = sqlalchemy.exc.IntegrityError(
            "INSERT INTO ai_job",
            {},
            database_error,
        )
        fake_session = _FakeSession(commit_error=integrity_error)

        with self.assertRaises(ai_job_repository.ActiveAiJobExistsError):
            await ai_job_repository.create_job(
                _session(fake_session),
                scene_image_id=17,
                job_type=AiJobType.DETECT_SCENE,
            )

        self.assertTrue(fake_session.rolled_back)


class GetAiJobTest(unittest.IsolatedAsyncioTestCase):
    """AI 작업 단건 조회 규칙을 검증합니다."""

    async def test_returns_job_by_uuid(self) -> None:
        """저장된 작업 UUID가 일치하면 해당 작업을 반환합니다."""
        job_id = uuid.uuid4()
        stored_job = AiJob(
            job_id=job_id,
            scene_image_id=17,
            job_type=AiJobType.DETECT_SCENE.value,
        )
        fake_session = _FakeSession(stored_job=stored_job)

        job = await ai_job_repository.get_job(_session(fake_session), job_id)

        self.assertIs(job, stored_job)

    async def test_raises_not_found_for_unknown_uuid(self) -> None:
        """저장되지 않은 작업 UUID는 명시적인 오류를 반환합니다."""
        fake_session = _FakeSession()

        with self.assertRaises(ai_job_repository.AiJobNotFoundError):
            await ai_job_repository.get_job(
                _session(fake_session), uuid.uuid4()
            )


if __name__ == "__main__":
    unittest.main()
