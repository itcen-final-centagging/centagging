"""고정 POC 사용자들을 데이터베이스에 준비합니다."""

import typing

import sqlalchemy

from app.core import database

_Role = typing.Literal["USER", "ADMIN", "SUPER_ADMIN"]


class _SeededUser(typing.TypedDict):
    """DB에 저장할 고정 POC 사용자 정보입니다."""

    login_id: str
    user_name: str
    password_hash: str
    session: str
    role: _Role


# 공개된 POC 검증값이며 운영 인증 정보로 사용하지 않습니다.
_SEEDED_USERS: tuple[_SeededUser, ...] = (
    {
        "login_id": "user",
        "user_name": "이재혁",
        "password_hash": (
            "03ac674216f3e15c761ee1a5e255f067"
            "953623c8b388b4459e13f978d7c846f4"
        ),
        "session": "centagging-poc-user-session",
        "role": "USER",
    },
    {
        "login_id": "admin",
        "user_name": "이충헌",
        "password_hash": (
            "03ac674216f3e15c761ee1a5e255f067"
            "953623c8b388b4459e13f978d7c846f4"
        ),
        "session": "centagging-poc-admin-session",
        "role": "ADMIN",
    },
    {
        "login_id": "super-admin",
        "user_name": "허민영",
        "password_hash": (
            "03ac674216f3e15c761ee1a5e255f067"
            "953623c8b388b4459e13f978d7c846f4"
        ),
        "session": "centagging-poc-super-admin-session",
        "role": "SUPER_ADMIN",
    },
)

_UPSERT_USER = sqlalchemy.text("""
    INSERT INTO app_user (
        login_id, user_name, password_hash, session, role, is_active
    )
    VALUES (:login_id, :user_name, :password_hash, :session, :role, TRUE)
    ON CONFLICT (login_id)
    DO UPDATE SET
        user_name = EXCLUDED.user_name,
        password_hash = EXCLUDED.password_hash,
        session = EXCLUDED.session,
        role = EXCLUDED.role,
        is_active = TRUE
    RETURNING user_id
    """)


async def initialize_users() -> list[int]:
    """세 역할의 고정 POC 계정을 생성하거나 고정값으로 갱신합니다.

    Returns:
        생성하거나 갱신한 사용자 ID 목록입니다.
    """
    user_ids: list[int] = []
    async with database.database_session_factory.begin() as session:
        for seeded_user in _SEEDED_USERS:
            user_id = typing.cast(
                int | None,
                await session.scalar(_UPSERT_USER, seeded_user),
            )
            if user_id is None:
                raise RuntimeError(
                    f"POC 사용자 ID를 확인할 수 없습니다: "
                    f"{seeded_user['login_id']}"
                )
            user_ids.append(user_id)
    return user_ids
