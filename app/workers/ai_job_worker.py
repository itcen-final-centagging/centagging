"""Cloud SQL 작업 큐를 폴링해 AI 분석을 수행하는 실행 Worker입니다."""

import argparse
import asyncio
import datetime
import logging
import os
import socket

from app.core import config, database
from app.models.ai_job import AiJob
from app.models.product_image_submission_job import (
    ProductImageSubmissionJob,
)
from app.repositories import (
    ai_job_repository,
)
from app.repositories import (
    product_image_submission_job_repository as submission_job_repository,
)
from app.services import (
    ai_job_worker_service,
)
from app.services import (
    product_image_submission_job_worker_service as product_job_worker_service,
)

_LOGGER = logging.getLogger(__name__)
DEFAULT_POLL_INTERVAL_SECONDS = 1.0
DEFAULT_STALE_LEASE_SECONDS = 300.0


def build_worker_id() -> str:
    """컨테이너 재시작마다 구분 가능한 100자 이하 Worker ID를 생성합니다."""
    hostname = socket.gethostname().strip() or "unknown-host"
    return f"{hostname}-{os.getpid()}"[:100]


def _validate_run_options(
    worker_id: str,
    poll_interval_seconds: float,
    stale_lease_seconds: float,
) -> None:
    """무한 루프에 필요한 실행 옵션을 사전에 검증합니다."""
    if not worker_id.strip() or len(worker_id.strip()) > 100:
        raise ValueError("worker_id must contain 1 to 100 characters")
    if poll_interval_seconds <= 0:
        raise ValueError("poll_interval_seconds must be greater than 0")
    if stale_lease_seconds <= 0:
        raise ValueError("stale_lease_seconds must be greater than 0")


async def process_once(
    settings: config.Settings,
    worker_id: str,
    stale_lease_seconds: float,
    now: datetime.datetime | None = None,
) -> bool:
    """중단된 작업을 복구한 뒤 대기 작업 한 건을 처리합니다.

    Returns:
        작업을 한 건 선점해 처리했으면 ``True``이며, 대기 작업이 없으면
        ``False``입니다.
    """
    current_time = now or datetime.datetime.now(datetime.timezone.utc)
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise ValueError("now must be timezone-aware")

    stale_before = current_time - datetime.timedelta(
        seconds=stale_lease_seconds
    )
    async with database.database_session_factory() as session:
        await ai_job_repository.recover_stale_jobs(session, stale_before)
        await submission_job_repository.recover_stale_jobs(
            session, stale_before
        )
        job: AiJob | ProductImageSubmissionJob | None = (
            await ai_job_worker_service.process_next_job(
                session,
                settings,
                worker_id,
            )
        )
        if job is None:
            job = await product_job_worker_service.process_next_job(
                session,
                settings,
                worker_id,
            )
    return job is not None


async def run_worker(
    settings: config.Settings,
    worker_id: str,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    stale_lease_seconds: float = DEFAULT_STALE_LEASE_SECONDS,
) -> None:
    """작업 처리 실패에도 종료하지 않고 다음 폴링 주기를 계속 실행합니다."""
    _validate_run_options(
        worker_id,
        poll_interval_seconds,
        stale_lease_seconds,
    )

    while True:
        try:
            processed = await process_once(
                settings,
                worker_id,
                stale_lease_seconds,
            )
        except Exception:  # pylint: disable=broad-exception-caught
            _LOGGER.exception("AI 작업 처리 루프에서 오류가 발생했습니다.")
            processed = False

        await asyncio.sleep(0 if processed else poll_interval_seconds)


def parse_args() -> argparse.Namespace:
    """Worker 실행에 필요한 폴링·임대 옵션을 읽습니다."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--worker-id",
        default=None,
        help="고정 Worker 식별자입니다. 기본값은 호스트명과 PID입니다.",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        help="대기 작업이 없을 때 다음 조회까지 기다릴 시간입니다.",
    )
    parser.add_argument(
        "--stale-lease-seconds",
        type=float,
        default=DEFAULT_STALE_LEASE_SECONDS,
        help="이 시간보다 오래 RUNNING인 작업을 복구합니다.",
    )
    return parser.parse_args()


def main() -> None:
    """명령행 Worker 프로세스를 시작합니다."""
    logging.basicConfig(level=logging.INFO)
    args = parse_args()
    worker_id = args.worker_id or build_worker_id()
    _LOGGER.info("AI 작업 Worker를 시작합니다: %s", worker_id)
    asyncio.run(
        run_worker(
            config.get_settings(),
            worker_id,
            args.poll_interval_seconds,
            args.stale_lease_seconds,
        )
    )


if __name__ == "__main__":
    main()
