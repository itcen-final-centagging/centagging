"""AI 작업 생성·조회 Repository의 상태 저장 규격을 검증합니다."""

import datetime
import json
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


class _FakeResult:  # pylint: disable=too-few-public-methods
    """Raw SQL의 선택적 UUID 반환 결과를 표현합니다."""

    def __init__(
        self,
        job_id: uuid.UUID | None = None,
        job_ids: list[uuid.UUID] | None = None,
    ) -> None:
        self.job_id = job_id
        self.job_ids = list(job_ids or [])

    def scalar_one_or_none(self) -> uuid.UUID | None:
        """변경된 작업 UUID 또는 대기 작업 없음 상태를 반환합니다."""
        return self.job_id

    def all(self) -> list[tuple[uuid.UUID]]:
        """복구된 모든 작업 UUID 행을 반환합니다."""
        return [(job_id,) for job_id in self.job_ids]


class _FakeSession:  # pylint: disable=too-many-instance-attributes
    """AI 작업 저장과 조회 동작을 기록하는 세션 대역입니다."""

    def __init__(
        self,
        stored_job: AiJob | None = None,
        commit_error: sqlalchemy.exc.IntegrityError | None = None,
        execute_job_ids: list[uuid.UUID | None] | None = None,
        execute_job_batches: list[list[uuid.UUID]] | None = None,
    ) -> None:
        self.stored_job = stored_job
        self.commit_error = commit_error
        self.execute_job_ids = list(execute_job_ids or [])
        self.execute_job_batches = list(execute_job_batches or [])
        self.added_job: AiJob | None = None
        self.statements: list[object] = []
        self.parameters: list[dict[str, object]] = []
        self.committed = False
        self.commit_count = 0
        self.rolled_back = False

    def add(self, job: AiJob) -> None:
        """세션에 추가된 작업을 기록합니다."""
        self.added_job = job

    async def commit(self) -> None:
        """커밋하거나 설정된 무결성 오류를 발생시킵니다."""
        if self.commit_error is not None:
            raise self.commit_error
        self.committed = True
        self.commit_count += 1

    async def rollback(self) -> None:
        """롤백 호출 여부를 기록합니다."""
        self.rolled_back = True

    async def execute(
        self,
        statement: object,
        parameters: dict[str, object],
    ) -> _FakeResult:
        """실행된 상태 변경 SQL과 파라미터를 기록합니다."""
        self.statements.append(statement)
        self.parameters.append(parameters)
        if self.execute_job_batches:
            return _FakeResult(job_ids=self.execute_job_batches.pop(0))
        if not self.execute_job_ids:
            return _FakeResult(None)
        return _FakeResult(self.execute_job_ids.pop(0))

    async def get(
        self,
        model: type[AiJob],
        job_id: uuid.UUID,
        **_kwargs: object,
    ) -> AiJob | None:
        """저장된 작업의 UUID가 일치하면 반환합니다."""
        if model is not AiJob or self.stored_job is None:
            return None
        if self.stored_job.job_id != job_id:
            return None
        return self.stored_job


def _session(fake_session: _FakeSession) -> AsyncSession:
    """테스트 세션 대역을 Repository 타입으로 변환합니다."""
    return typing.cast(AsyncSession, fake_session)


def _job(
    job_id: uuid.UUID,
    status: AiJobStatus,
    attempt_count: int = 0,
    max_attempts: int = 3,
) -> AiJob:
    """상태 전환 테스트용 AI 작업을 생성합니다."""
    return AiJob(
        job_id=job_id,
        scene_image_id=17,
        job_type=AiJobType.DETECT_SCENE.value,
        status=status.value,
        attempt_count=attempt_count,
        max_attempts=max_attempts,
    )


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


class ClaimAiJobTest(unittest.IsolatedAsyncioTestCase):
    """대기 작업 원자적 선점 규칙을 검증합니다."""

    async def test_claims_oldest_pending_job_with_skip_locked(self) -> None:
        """대기 작업을 RUNNING으로 변경하고 Worker 정보를 기록합니다."""
        job_id = uuid.uuid4()
        stored_job = _job(job_id, AiJobStatus.RUNNING, attempt_count=1)
        fake_session = _FakeSession(
            stored_job=stored_job,
            execute_job_ids=[job_id],
        )

        claimed_job = await ai_job_repository.claim_next_job(
            _session(fake_session), " worker-1 "
        )

        self.assertIs(claimed_job, stored_job)
        claim_sql = str(fake_session.statements[0])
        self.assertIn("FOR UPDATE SKIP LOCKED", claim_sql)
        self.assertIn("attempt_count = job.attempt_count + 1", claim_sql)
        self.assertEqual(fake_session.parameters[0], {"worker_id": "worker-1"})
        self.assertEqual(fake_session.commit_count, 2)

    async def test_returns_none_when_no_pending_job_exists(self) -> None:
        """선점할 수 있는 대기 작업이 없으면 None을 반환합니다."""
        fake_session = _FakeSession(execute_job_ids=[None])

        claimed_job = await ai_job_repository.claim_next_job(
            _session(fake_session), "worker-1"
        )

        self.assertIsNone(claimed_job)
        self.assertEqual(fake_session.commit_count, 1)

    async def test_rejects_empty_worker_id_without_query(self) -> None:
        """빈 Worker 식별자는 DB 조회 전에 거부합니다."""
        fake_session = _FakeSession()

        with self.assertRaisesRegex(ValueError, "1 to 100"):
            await ai_job_repository.claim_next_job(_session(fake_session), "  ")

        self.assertEqual(fake_session.statements, [])


class CompleteAiJobTest(unittest.IsolatedAsyncioTestCase):
    """RUNNING 작업의 성공·실패 상태 전환을 검증합니다."""

    async def test_marks_running_job_succeeded_with_result(self) -> None:
        """성공 결과를 JSON으로 저장하고 작업을 종료합니다."""
        job_id = uuid.uuid4()
        stored_job = _job(job_id, AiJobStatus.SUCCEEDED, attempt_count=1)
        fake_session = _FakeSession(
            stored_job=stored_job,
            execute_job_ids=[job_id],
        )

        completed_job = await ai_job_repository.mark_job_succeeded(
            _session(fake_session),
            job_id,
            {"detections": [{"label": "sofa"}]},
        )

        self.assertIs(completed_job, stored_job)
        success_sql = str(fake_session.statements[0])
        self.assertIn("status = 'SUCCEEDED'", success_sql)
        self.assertIn("status = 'RUNNING'", success_sql)
        self.assertEqual(
            json.loads(
                typing.cast(str, fake_session.parameters[0]["result_payload"])
            ),
            {"detections": [{"label": "sofa"}]},
        )
        self.assertEqual(fake_session.commit_count, 2)

    async def test_failure_sql_requeues_until_max_attempts(self) -> None:
        """실패 횟수에 따라 PENDING 또는 FAILED로 전환하도록 요청합니다."""
        job_id = uuid.uuid4()
        stored_job = _job(job_id, AiJobStatus.PENDING, attempt_count=1)
        fake_session = _FakeSession(
            stored_job=stored_job,
            execute_job_ids=[job_id],
        )

        failed_job = await ai_job_repository.mark_job_failed(
            _session(fake_session),
            job_id,
            error_code="VERTEX_UNAVAILABLE",
            error_message="temporary failure",
        )

        self.assertIs(failed_job, stored_job)
        failure_sql = str(fake_session.statements[0])
        self.assertIn("attempt_count < max_attempts", failure_sql)
        self.assertIn("THEN 'PENDING'", failure_sql)
        self.assertIn("ELSE 'FAILED'", failure_sql)
        self.assertEqual(
            fake_session.parameters[0]["error_code"],
            "VERTEX_UNAVAILABLE",
        )

    async def test_rejects_transition_from_non_running_state(self) -> None:
        """RUNNING이 아닌 작업은 성공 상태로 변경하지 않습니다."""
        job_id = uuid.uuid4()
        stored_job = _job(job_id, AiJobStatus.SUCCEEDED, attempt_count=1)
        fake_session = _FakeSession(
            stored_job=stored_job,
            execute_job_ids=[None],
        )

        with self.assertRaises(ai_job_repository.AiJobStateConflictError):
            await ai_job_repository.mark_job_succeeded(
                _session(fake_session), job_id, {}
            )

        self.assertTrue(fake_session.rolled_back)

    async def test_raises_not_found_when_transition_target_is_missing(
        self,
    ) -> None:
        """상태 변경 대상 작업이 없으면 미존재 오류를 반환합니다."""
        job_id = uuid.uuid4()
        fake_session = _FakeSession(execute_job_ids=[None])

        with self.assertRaises(ai_job_repository.AiJobNotFoundError):
            await ai_job_repository.mark_job_failed(
                _session(fake_session),
                job_id,
                error_code="UNKNOWN",
                error_message="failed",
            )


class RecoverStaleAiJobTest(unittest.IsolatedAsyncioTestCase):
    """중단된 Worker의 RUNNING 작업 복구 규칙을 검증합니다."""

    async def test_recovers_expired_jobs_for_retry_or_final_failure(
        self,
    ) -> None:
        """임대 만료 작업을 실행 횟수에 따라 재대기 또는 종료합니다."""
        stale_before = datetime.datetime(
            2026,
            8,
            18,
            12,
            0,
            tzinfo=datetime.timezone.utc,
        )
        fake_session = _FakeSession(
            execute_job_batches=[[uuid.uuid4(), uuid.uuid4()]]
        )

        recovered_count = await ai_job_repository.recover_stale_jobs(
            _session(fake_session), stale_before
        )

        self.assertEqual(recovered_count, 2)
        recovery_sql = str(fake_session.statements[0])
        self.assertIn("status = 'RUNNING'", recovery_sql)
        self.assertIn("locked_at IS NULL", recovery_sql)
        self.assertIn("locked_at < :stale_before", recovery_sql)
        self.assertIn("THEN 'PENDING'", recovery_sql)
        self.assertIn("ELSE 'FAILED'", recovery_sql)
        self.assertIn("WORKER_LEASE_EXPIRED", recovery_sql)
        self.assertEqual(
            fake_session.parameters[0]["stale_before"], stale_before
        )
        self.assertEqual(fake_session.commit_count, 1)

    async def test_returns_zero_when_no_stale_job_exists(self) -> None:
        """복구 대상이 없어도 트랜잭션을 종료하고 0을 반환합니다."""
        fake_session = _FakeSession(execute_job_batches=[[]])

        recovered_count = await ai_job_repository.recover_stale_jobs(
            _session(fake_session),
            datetime.datetime.now(datetime.timezone.utc),
        )

        self.assertEqual(recovered_count, 0)
        self.assertEqual(fake_session.commit_count, 1)

    async def test_rejects_timezone_naive_cutoff_without_query(self) -> None:
        """시간대 없는 기준 시각은 DB 조회 전에 거부합니다."""
        fake_session = _FakeSession()

        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            await ai_job_repository.recover_stale_jobs(
                _session(fake_session),
                datetime.datetime(2026, 8, 18, 12, 0),
            )

        self.assertEqual(fake_session.statements, [])


if __name__ == "__main__":
    unittest.main()
