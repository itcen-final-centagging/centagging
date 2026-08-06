"""Centagging FastAPI 애플리케이션 진입점입니다. / FastAPI application entry point."""

import collections.abc
import contextlib

import fastapi

from app.api import auth, gemini
from app.core import database
from app.services import user_seed


@contextlib.asynccontextmanager
async def lifespan(_: fastapi.FastAPI) -> collections.abc.AsyncIterator[None]:
    """서버 시작 시 고정 사용자를 준비하고 종료 시 DB를 정리합니다."""
    try:
        await user_seed.initialize_user()
        yield
    finally:
        await database.database_engine.dispose()

app = fastapi.FastAPI(
    title="Centagging API",
    description="VLM 기반 가구 자동 태깅 및 SKU 매칭 API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(gemini.router)
app.include_router(auth.router)


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Return the service health status for local and container checks."""
    return {"status": "ok"}
