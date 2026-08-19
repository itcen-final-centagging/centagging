"""AI 분석 작업 생성과 단건 조회를 담당하는 Repository입니다."""

import collections.abc
import datetime
import json
import uuid

import sqlalchemy
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import TextClause

from app.models.ai_job import AiJob, AiJobStatus, AiJobType

_ACTIVE_JOB_CONSTRAINT = "uq_ai_job_active_scene_type"
_CLAIM_NEXT_JOB = sqlalchemy.text("""
    WITH next_job AS (
        SELECT job_id
        FROM ai_job
        WHERE status = 'PENDING'
          AND attempt_count < max_attempts
        ORDER BY created_at, job_id
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    UPDATE ai_job AS job
    SET status = 'RUNNING',
        attempt_count = job.attempt_count + 1,
        worker_id = :worker_id,
        locked_at = now(),
        started_at = COALESCE(job.started_at, now()),
        finished_at = NULL,
        error_code = NULL,
        error_message = NULL,
        updated_at = now()
    FROM next_job
    WHERE job.job_id = next_job.job_id
    RETURNING job.job_id
""")
_MARK_JOB_SUCCEEDED = sqlalchemy.text("""
    UPDATE ai_job
    SET status = 'SUCCEEDED',
        result_payload = CAST(:result_payload AS jsonb),
        error_code = NULL,
        error_message = NULL,
        worker_id = NULL,
        locked_at = NULL,
        finished_at = now(),
        updated_at = now()
    WHERE job_id = :job_id
      AND status = 'RUNNING'
    RETURNING job_id
""")
_MARK_JOB_FAILED = sqlalchemy.text("""
    UPDATE ai_job
    SET status = CASE
            WHEN attempt_count < max_attempts THEN 'PENDING'
            ELSE 'FAILED'
        END,
        error_code = :error_code,
        error_message = :error_message,
        worker_id = NULL,
        locked_at = NULL,
        finished_at = CASE
            WHEN attempt_count < max_attempts THEN NULL
            ELSE now()
        END,
        updated_at = now()
    WHERE job_id = :job_id
      AND status = 'RUNNING'
    RETURNING job_id
""")
_RECOVER_STALE_JOBS = sqlalchemy.text("""
    UPDATE ai_job
    SET status = CASE
            WHEN attempt_count < max_attempts THEN 'PENDING'
            ELSE 'FAILED'
        END,
        error_code = 'WORKER_LEASE_EXPIRED',
        error_message = 'Worker lease expired before job completion.',
        worker_id = NULL,
        locked_at = NULL,
        finished_at = CASE
            WHEN attempt_count < max_attempts THEN NULL
            ELSE now()
        END,
        updated_at = now()
    WHERE status = 'RUNNING'
      AND (locked_at IS NULL OR locked_at < :stale_before)
    RETURNING job_id
""")


class AiJobNotFoundError(RuntimeError):
    """요청한 AI 작업이 존재하지 않는 경우입니다."""


class ActiveAiJobExistsError(RuntimeError):
    """동일 장면과 유형의 활성 작업이 이미 존재하는 경우입니다."""


class AiJobStateConflictError(RuntimeError):
    """현재 상태에서 요청한 작업 전이를 수행할 수 없는 경우입니다."""


def _constraint_name(error: sqlalchemy.exc.IntegrityError) -> str | None:
    """PostgreSQL 무결성 오류에서 제약조건 이름을 추출합니다."""
    diagnostic = getattr(error.orig, "diag", None)
    return getattr(diagnostic, "constraint_name", None)


async def create_job(
    session: AsyncSession,
    scene_image_id: int,
    job_type: AiJobType,
    input_payload: collections.abc.Mapping[str, object] | None = None,
    max_attempts: int = 3,
) -> AiJob:
    """대기 상태의 AI 작업을 생성합니다.

    Args:
        session: 요청 범위의 비동기 SQLAlchemy 세션입니다.
        scene_image_id: 분석 대상 연출 이미지 ID입니다.
        job_type: Worker가 수행할 AI 작업 유형입니다.
        input_payload: 작업 실행에 필요한 추가 입력값입니다.
        max_attempts: 최초 실행을 포함한 최대 실행 횟수입니다.

    Returns:
        생성된 ``AiJob`` 엔티티입니다.

    Raises:
        ValueError: 최대 실행 횟수가 1보다 작은 경우입니다.
        ActiveAiJobExistsError: 동일 장면·유형의 활성 작업이 있는 경우입니다.
        sqlalchemy.exc.IntegrityError: 그 외 DB 무결성 오류가 발생한 경우입니다.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    job = AiJob(
        job_id=uuid.uuid4(),
        scene_image_id=scene_image_id,
        job_type=job_type.value,
        status=AiJobStatus.PENDING.value,
        input_payload=dict(input_payload or {}),
        max_attempts=max_attempts,
    )
    session.add(job)

    try:
        await session.commit()
    except sqlalchemy.exc.IntegrityError as error:
        await session.rollback()
        if _constraint_name(error) == _ACTIVE_JOB_CONSTRAINT:
            raise ActiveAiJobExistsError(
                scene_image_id, job_type.value
            ) from error
        raise

    return job


async def get_job(session: AsyncSession, job_id: uuid.UUID) -> AiJob:
    """UUID로 AI 작업 한 건을 조회합니다.

    Args:
        session: 요청 범위의 비동기 SQLAlchemy 세션입니다.
        job_id: 조회할 AI 작업 UUID입니다.

    Returns:
        조회된 ``AiJob`` 엔티티입니다.

    Raises:
        AiJobNotFoundError: 해당 UUID의 작업이 없는 경우입니다.
    """
    job = await session.get(AiJob, job_id)
    if job is None:
        raise AiJobNotFoundError(job_id)
    return job


async def _get_refreshed_job(session: AsyncSession, job_id: uuid.UUID) -> AiJob:
    """Raw SQL 상태 변경 이후 최신 AI 작업 상태를 조회합니다."""
    job = await session.get(AiJob, job_id, populate_existing=True)
    if job is None:
        raise AiJobNotFoundError(job_id)
    await session.commit()
    return job


async def claim_next_job(
    session: AsyncSession,
    worker_id: str,
) -> AiJob | None:
    """가장 오래 대기한 AI 작업을 중복 없이 선점합니다.

    ``FOR UPDATE SKIP LOCKED``를 사용하므로 여러 Worker가 동시에 호출해도
    동일한 작업을 선점하지 않습니다. 선점된 작업은 ``RUNNING``으로 바뀌고
    실행 시도 횟수가 1 증가합니다.

    Args:
        session: Worker 범위의 비동기 SQLAlchemy 세션입니다.
        worker_id: 작업을 선점하는 Worker 식별자입니다.

    Returns:
        선점한 작업이며 대기 작업이 없으면 ``None``입니다.

    Raises:
        ValueError: Worker 식별자가 비어 있거나 컬럼 길이를 초과한 경우입니다.
    """
    normalized_worker_id = worker_id.strip()
    if not normalized_worker_id or len(normalized_worker_id) > 100:
        raise ValueError("worker_id must contain 1 to 100 characters")

    result = await session.execute(
        _CLAIM_NEXT_JOB,
        {"worker_id": normalized_worker_id},
    )
    claimed_job_id = result.scalar_one_or_none()
    await session.commit()

    if claimed_job_id is None:
        return None
    return await _get_refreshed_job(session, uuid.UUID(str(claimed_job_id)))


async def _complete_running_job(
    session: AsyncSession,
    statement: TextClause,
    parameters: dict[str, object],
) -> AiJob:
    """RUNNING 작업에 상태 변경문을 적용하고 최신 엔티티를 반환합니다."""
    job_id = uuid.UUID(str(parameters["job_id"]))
    result = await session.execute(statement, parameters)
    transitioned_job_id = result.scalar_one_or_none()

    if transitioned_job_id is None:
        await session.rollback()
        current_job = await get_job(session, job_id)
        raise AiJobStateConflictError(job_id, current_job.status)

    await session.commit()
    return await _get_refreshed_job(session, job_id)


async def mark_job_succeeded(
    session: AsyncSession,
    job_id: uuid.UUID,
    result_payload: collections.abc.Mapping[str, object],
) -> AiJob:
    """RUNNING 작업을 성공 처리하고 결과를 저장합니다."""
    return await _complete_running_job(
        session,
        _MARK_JOB_SUCCEEDED,
        {
            "job_id": job_id,
            "result_payload": json.dumps(
                dict(result_payload), ensure_ascii=False
            ),
        },
    )


async def mark_job_failed(
    session: AsyncSession,
    job_id: uuid.UUID,
    error_code: str,
    error_message: str,
) -> AiJob:
    """RUNNING 작업 실패를 기록하고 재시도 또는 최종 실패 처리합니다.

    현재 실행 횟수가 최대 횟수보다 작으면 다시 ``PENDING``으로 전환하고,
    최대 횟수에 도달했으면 ``FAILED``로 종료합니다.
    """
    if not error_code or len(error_code) > 50:
        raise ValueError("error_code must contain 1 to 50 characters")

    return await _complete_running_job(
        session,
        _MARK_JOB_FAILED,
        {
            "job_id": job_id,
            "error_code": error_code,
            "error_message": error_message,
        },
    )


async def recover_stale_jobs(
    session: AsyncSession,
    stale_before: datetime.datetime,
) -> int:
    """Worker 임대 시간이 만료된 RUNNING 작업을 복구합니다.

    실행 횟수가 남은 작업은 다시 ``PENDING``으로 보내고, 최대 실행 횟수에
    도달한 작업은 ``FAILED``로 종료합니다. ``locked_at``이 없는 비정상
    RUNNING 작업도 복구 대상에 포함합니다.

    Args:
        session: Worker 범위의 비동기 SQLAlchemy 세션입니다.
        stale_before: 이 시각보다 먼저 선점된 작업을 복구하는 UTC 기준입니다.

    Returns:
        재대기 또는 최종 실패로 전환한 작업 수입니다.

    Raises:
        ValueError: 시간대 정보가 없는 기준 시각이 전달된 경우입니다.
    """
    if stale_before.tzinfo is None or stale_before.utcoffset() is None:
        raise ValueError("stale_before must be timezone-aware")

    result = await session.execute(
        _RECOVER_STALE_JOBS,
        {"stale_before": stale_before},
    )
    recovered_count = len(result.all())
    await session.commit()
    return recovered_count
