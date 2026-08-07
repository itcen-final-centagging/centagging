"""고정 MVP 사용자를 데이터베이스에 준비합니다."""

import typing

import sqlalchemy

from app.core import config, database

_UPSERT_USER = sqlalchemy.text("""
    INSERT INTO app_user (login_id, user_name, password_hash, is_active)
    VALUES (:login_id, :user_name, NULL, TRUE)
    ON CONFLICT (login_id)
    DO UPDATE SET user_name = EXCLUDED.user_name, is_active = TRUE
    RETURNING user_id
    """)


async def initialize_user() -> int:
    """환경변수의 고정 계정을 app_user에 생성하거나 갱신합니다."""
    settings = config.get_settings()
    if not settings.mvp_login_id or not settings.mvp_login_password:
        raise RuntimeError(
            "MVP_LOGIN_ID와 MVP_LOGIN_PASSWORD를 설정해야 합니다."
        )
    async with database.database_session_factory.begin() as session:
        user_id = typing.cast(
            int | None,
            await session.scalar(
                _UPSERT_USER,
                {"login_id": settings.mvp_login_id, "user_name": "MVP User"},
            ),
        )
    if user_id is None:
        raise RuntimeError("MVP 사용자 ID를 확인할 수 없습니다.")
    return user_id
