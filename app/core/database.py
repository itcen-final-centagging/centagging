"""비동기 PostgreSQL 엔진과 세션을 관리합니다."""

import collections.abc
from sqlalchemy.engine import url as sqlalchemy_url
from sqlalchemy.ext import asyncio as sqlalchemy_async

from app.core import config


def _create_database_url(
    settings: config.DatabaseSettings,
) -> sqlalchemy_url.URL:
    """비밀번호를 노출하지 않는 PostgreSQL 연결 URL을 생성합니다.

    Args:
        settings: PostgreSQL 연결 정보가 담긴 데이터베이스 설정입니다.

    Returns:
        Psycopg 3 비동기 드라이버를 사용하는 SQLAlchemy URL입니다.
    """
    return sqlalchemy_url.URL.create(
        drivername="postgresql+psycopg",
        username=settings.username,
        password=settings.password,
        host=settings.host,
        port=settings.port,
        database=settings.name,
    )


def _create_database_engine(
    settings: config.DatabaseSettings,
) -> sqlalchemy_async.AsyncEngine:
    """애플리케이션에서 공유할 비동기 PostgreSQL 엔진을 생성합니다.

    Args:
        settings: PostgreSQL 연결 정보가 담긴 데이터베이스 설정입니다.

    Returns:
        연결 상태 확인 기능이 활성화된 비동기 SQLAlchemy 엔진입니다.
    """
    return sqlalchemy_async.create_async_engine(
        _create_database_url(settings),
        pool_pre_ping=True,
    )


database_engine = _create_database_engine(config.get_settings().database)
database_session_factory = sqlalchemy_async.async_sessionmaker(
    bind=database_engine,
    expire_on_commit=False,
)


async def get_database_session() -> (
    collections.abc.AsyncIterator[sqlalchemy_async.AsyncSession]
):
    """요청에서 사용할 DB 세션을 제공하고 요청 처리 후 닫습니다.

    Yields:
        요청 범위에서 사용하는 비동기 SQLAlchemy 세션입니다.
    """
    async with database_session_factory() as session:
        yield session

