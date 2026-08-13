"""고정 POC 사용자 초기화 동작 테스트입니다."""

import unittest
import unittest.mock

from app.services import user_seed


class _FakeSession:
    """고정 사용자 upsert 요청을 기록하는 DB 대역입니다."""

    def __init__(self) -> None:
        self.stored_users: list[dict[str, object]] = []
        self.schema_ensured = False

    async def execute(self, _statement: object) -> None:
        self.schema_ensured = True

    async def scalar(
        self, _statement: object, parameters: dict[str, object]
    ) -> int:
        self.stored_users.append(parameters)
        return len(self.stored_users)


class _FakeBeginContext:
    """비동기 트랜잭션 컨텍스트 대역입니다."""

    def __init__(self, session: _FakeSession) -> None:
        self.session = session

    async def __aenter__(self) -> _FakeSession:
        return self.session

    async def __aexit__(
        self,
        _exc_type: object,
        _exc_value: object,
        _traceback: object,
    ) -> None:
        return None


class _FakeSessionFactory:
    """초기화 함수에 트랜잭션 대역을 제공하는 팩터리입니다."""

    def __init__(self) -> None:
        self.session = _FakeSession()

    def begin(self) -> _FakeBeginContext:
        return _FakeBeginContext(self.session)


class InitializeUserTest(unittest.IsolatedAsyncioTestCase):
    """세 역할의 고정 사용자가 초기화되는지 검증합니다."""

    async def test_stores_fixed_users_without_environment_settings(
        self,
    ) -> None:
        """환경 설정 없이 세 역할의 사용자와 세션을 저장합니다."""
        session_factory = _FakeSessionFactory()

        with unittest.mock.patch.object(
            user_seed.database,
            "database_session_factory",
            session_factory,
        ):
            user_ids = await user_seed.initialize_users()

        self.assertEqual(user_ids, [1, 2, 3])
        self.assertTrue(session_factory.session.schema_ensured)
        self.assertEqual(
            session_factory.session.stored_users,
            [
                {
                    "login_id": "user",
                    "user_name": "일반 사용자",
                    "session": "centagging-poc-user-session",
                    "role": "USER",
                },
                {
                    "login_id": "admin",
                    "user_name": "관리자",
                    "session": "centagging-poc-admin-session",
                    "role": "ADMIN",
                },
                {
                    "login_id": "super-admin",
                    "user_name": "최종 관리자",
                    "session": "centagging-poc-super-admin-session",
                    "role": "SUPER_ADMIN",
                },
            ],
        )

    def test_upsert_restores_fixed_role_and_session(self) -> None:
        """충돌 갱신 SQL이 고정 역할과 세션을 모두 복구합니다."""
        # PostgreSQL upsert 자체가 이 테스트에서 검증할 영속화 동작입니다.
        sql = str(user_seed._UPSERT_USER)  # pylint: disable=protected-access

        self.assertIn("session = EXCLUDED.session", sql)
        self.assertIn("role = EXCLUDED.role", sql)


if __name__ == "__main__":
    unittest.main()
