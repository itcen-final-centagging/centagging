"""AI 분석 작업 생성과 단건 조회를 담당하는 Repository입니다."""

import collections.abc
import uuid

import sqlalchemy
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_job import AiJob, AiJobStatus, AiJobType

_ACTIVE_JOB_CONSTRAINT = "uq_ai_job_active_scene_type"


class AiJobNotFoundError(RuntimeError):
    """요청한 AI 작업이 존재하지 않는 경우입니다."""


class ActiveAiJobExistsError(RuntimeError):
    """동일 장면과 유형의 활성 작업이 이미 존재하는 경우입니다."""


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
