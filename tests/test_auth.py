"""고정 세션 인증 API 테스트입니다."""

import collections.abc
import hashlib
import unittest

import fastapi
import starlette.testclient

from app.api import auth
from app.core import database


class _FakeMappings:
    """SQL 실행 결과의 매핑 행을 제공하는 대역입니다."""

    def __init__(self, user: dict[str, object] | None) -> None:
        self.user = user

    def one_or_none(self) -> dict[str, object] | None:
        return self.user


class _FakeResult:
    """SQLAlchemy 결과 객체 대역입니다."""

    def __init__(self, user: dict[str, object] | None) -> None:
        self.user = user

    def mappings(self) -> _FakeMappings:
        return _FakeMappings(self.user)


class _FakeSession:
    """고정 사용자 조회를 흉내 내는 비동기 DB 세션 대역입니다."""

    def __init__(self) -> None:
        self.users = (
            {
                "user_id": 7,
                "login_id": "user",
                "user_name": "일반 사용자",
                "role": "USER",
                "session": "centagging-poc-user-session",
                "password_hash": hashlib.sha256(b"1234").hexdigest(),
                "is_active": True,
            },
            {
                "user_id": 8,
                "login_id": "admin",
                "user_name": "관리자",
                "role": "ADMIN",
                "session": "centagging-poc-admin-session",
                "password_hash": hashlib.sha256(b"1234").hexdigest(),
                "is_active": True,
            },
            {
                "user_id": 9,
                "login_id": "super-admin",
                "user_name": "최종 관리자",
                "role": "SUPER_ADMIN",
                "session": "centagging-poc-super-admin-session",
                "password_hash": hashlib.sha256(b"1234").hexdigest(),
                "is_active": True,
            },
        )

    async def execute(
        self, _statement: object, parameters: dict[str, object]
    ) -> _FakeResult:
        for user in self.users:
            if (
                parameters.get("login_id") == user["login_id"]
                and parameters.get("password_hash") == user["password_hash"]
            ):
                return _FakeResult(user)
            if parameters.get("session") == user["session"]:
                return _FakeResult(user)
        return _FakeResult(None)


class AuthApiTest(unittest.TestCase):
    """로그인과 현재 사용자 조회의 고정 세션 동작을 검증합니다."""

    def setUp(self) -> None:
        """인증 라우터와 가짜 DB 세션을 준비합니다."""
        self.session = _FakeSession()
        self.app = fastapi.FastAPI()
        self.app.include_router(auth.router)

        async def override_database_session() -> (
            collections.abc.AsyncIterator[_FakeSession]
        ):
            yield self.session

        self.app.dependency_overrides[database.get_database_session] = (
            override_database_session
        )
        self.client = starlette.testclient.TestClient(self.app)

    def test_login_returns_fixed_session_and_role(self) -> None:
        """올바른 DB 고정 계정으로 로그인하면 세션과 역할을 반환합니다."""
        response = self.client.post(
            "/auth/login",
            json={"login_id": "user", "password": "1234"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "user_id": 7,
                "login_id": "user",
                "user_name": "일반 사용자",
                "role": "USER",
                "session": "centagging-poc-user-session",
            },
        )

    def test_login_returns_role_for_all_fixed_users(self) -> None:
        """세 역할의 고정 계정은 각각의 역할과 세션을 반환합니다."""
        test_cases = (
            ("user", "1234", "USER", "centagging-poc-user-session"),
            (
                "admin",
                "1234",
                "ADMIN",
                "centagging-poc-admin-session",
            ),
            (
                "super-admin",
                "1234",
                "SUPER_ADMIN",
                "centagging-poc-super-admin-session",
            ),
        )

        for login_id, password, role, session in test_cases:
            with self.subTest(login_id=login_id):
                response = self.client.post(
                    "/auth/login",
                    json={"login_id": login_id, "password": password},
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["role"], role)
                self.assertEqual(response.json()["session"], session)

    def test_login_rejects_wrong_password(self) -> None:
        """DB의 비밀번호 해시와 다른 비밀번호는 거부합니다."""
        response = self.client.post(
            "/auth/login",
            json={"login_id": "user", "password": "wrong-password"},
        )

        self.assertEqual(response.status_code, 401)

    def test_me_returns_user_for_matching_bearer_session(self) -> None:
        """DB 세션과 일치하는 Bearer 값으로 현재 사용자를 조회합니다."""
        response = self.client.get(
            "/auth/me",
            headers={"Authorization": "Bearer centagging-poc-user-session"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["login_id"], "user")
        self.assertEqual(
            response.json()["session"], "centagging-poc-user-session"
        )

    def test_me_rejects_missing_or_mismatched_session(self) -> None:
        """누락되거나 다른 Bearer 세션은 인증되지 않습니다."""
        missing_response = self.client.get("/auth/me")
        mismatched_response = self.client.get(
            "/auth/me",
            headers={"Authorization": "Bearer another-session"},
        )

        self.assertEqual(missing_response.status_code, 401)
        self.assertEqual(mismatched_response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
