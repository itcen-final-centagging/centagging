"""AI 작업 Worker 실행 루프의 폴링과 복구 흐름을 검증합니다."""

import asyncio
import datetime
import unittest
import unittest.mock

from app.core import config, database
from app.repositories import ai_job_repository
from app.services import ai_job_worker_service
from app.workers import ai_job_worker


class _SessionContext:  # pylint: disable=too-few-public-methods
    """async_sessionmaker가 반환하는 비동기 컨텍스트 대역입니다."""

    async def __aenter__(self) -> object:
        """Worker가 사용할 세션 대역을 반환합니다."""
        return object()

    async def __aexit__(
        self,
        _exception_type: object,
        _exception: object,
        _traceback: object,
    ) -> None:
        """별도 정리가 필요 없는 테스트 세션을 종료합니다."""


def _settings() -> config.Settings:
    """Worker 실행에 필요한 최소 설정을 생성합니다."""
    return config.Settings(
        gemini_api_key="test-key",
        gemini_vlm_model="test-model",
        gemini_embedding_model="test-embedding",
        mvp_login_id="mvp-user",
        mvp_login_password="password",
        image_storage_root="uploads",
        sku_image_root="data/images",
        database=config.DatabaseSettings(
            name="centagging",
            username="centagging",
            password="password",
            host="db",
            port=5432,
        ),
    )


class AiJobWorkerRunnerTest(unittest.IsolatedAsyncioTestCase):
    """Worker의 단건 처리와 폴링 지속 동작을 검증합니다."""

    def setUp(self) -> None:
        """세션 팩토리와 Worker 의존성을 테스트 대역으로 교체합니다."""
        self.context = _SessionContext()
        self.session_factory_patch = unittest.mock.patch.object(
            database,
            "database_session_factory",
            return_value=self.context,
        )
        self.recovery_patch = unittest.mock.patch.object(
            ai_job_repository,
            "recover_stale_jobs",
            new=unittest.mock.AsyncMock(return_value=0),
        )
        self.process_patch = unittest.mock.patch.object(
            ai_job_worker_service,
            "process_next_job",
            new=unittest.mock.AsyncMock(return_value=object()),
        )
        self.session_factory_mock = self.session_factory_patch.start()
        self.recovery_mock = self.recovery_patch.start()
        self.process_mock = self.process_patch.start()

    def tearDown(self) -> None:
        """테스트마다 적용한 의존성 패치를 제거합니다."""
        self.process_patch.stop()
        self.recovery_patch.stop()
        self.session_factory_patch.stop()

    async def test_process_once_recovers_stale_jobs_before_processing(
        self,
    ) -> None:
        """각 폴링 주기에서 임대 만료 작업을 먼저 복구합니다."""
        current_time = datetime.datetime(
            2026,
            8,
            18,
            12,
            tzinfo=datetime.timezone.utc,
        )

        processed = await ai_job_worker.process_once(
            _settings(),
            "worker-1",
            stale_lease_seconds=300,
            now=current_time,
        )

        self.assertTrue(processed)
        self.recovery_mock.assert_awaited_once()
        recovery_call = self.recovery_mock.await_args
        assert recovery_call is not None
        self.assertEqual(
            recovery_call.args[1],
            current_time - datetime.timedelta(seconds=300),
        )
        self.process_mock.assert_awaited_once()
        process_call = self.process_mock.await_args
        assert process_call is not None
        self.assertEqual(process_call.args[2], "worker-1")

    async def test_process_once_returns_false_when_queue_is_empty(self) -> None:
        """대기 작업이 없으면 다음 폴링 주기를 기다리도록 False를 반환합니다."""
        self.process_mock.return_value = None

        processed = await ai_job_worker.process_once(
            _settings(),
            "worker-1",
            stale_lease_seconds=300,
        )

        self.assertFalse(processed)

    async def test_run_worker_continues_after_processing_error(self) -> None:
        """한 번의 처리 오류가 Worker 프로세스 종료로 이어지지 않습니다."""
        with unittest.mock.patch.object(
            ai_job_worker,
            "process_once",
            new=unittest.mock.AsyncMock(side_effect=RuntimeError("db error")),
        ) as process_once_mock:
            with unittest.mock.patch.object(
                asyncio,
                "sleep",
                new=unittest.mock.AsyncMock(side_effect=asyncio.CancelledError),
            ) as sleep_mock:
                with unittest.mock.patch(
                    "app.workers.ai_job_worker._LOGGER"
                ) as logger_mock:
                    with self.assertRaises(asyncio.CancelledError):
                        await ai_job_worker.run_worker(
                            _settings(),
                            "worker-1",
                            poll_interval_seconds=2,
                        )

        process_once_mock.assert_awaited_once()
        sleep_mock.assert_awaited_once_with(2)
        logger_mock.exception.assert_called_once()

    def test_build_worker_id_uses_hostname_and_process_id(self) -> None:
        """기본 Worker ID는 컨테이너와 프로세스를 구분합니다."""
        with unittest.mock.patch.object(
            ai_job_worker.socket,
            "gethostname",
            return_value="centagging-worker",
        ):
            with unittest.mock.patch.object(
                ai_job_worker.os,
                "getpid",
                return_value=123,
            ):
                worker_id = ai_job_worker.build_worker_id()

        self.assertEqual(worker_id, "centagging-worker-123")

    def test_rejects_invalid_run_options(self) -> None:
        """빈 Worker ID와 0 이하 폴링·임대 값은 시작 전에 거부합니다."""
        # pylint: disable=protected-access
        with self.assertRaises(ValueError):
            ai_job_worker._validate_run_options("", 1, 300)
        with self.assertRaises(ValueError):
            ai_job_worker._validate_run_options("worker-1", 0, 300)
        with self.assertRaises(ValueError):
            ai_job_worker._validate_run_options("worker-1", 1, 0)
        # pylint: enable=protected-access


if __name__ == "__main__":
    unittest.main()
