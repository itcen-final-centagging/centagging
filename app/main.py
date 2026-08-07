"""Centagging FastAPI 애플리케이션 진입점입니다. / FastAPI application entry point."""

import pathlib

import fastapi
from fastapi import staticfiles

from app.api import gemini, sku

_UPLOAD_DIR = pathlib.Path("uploads")
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = fastapi.FastAPI(
    title="Centagging API",
    description="VLM 기반 가구 자동 태깅 및 SKU 매칭 API",
    version="0.1.0",
)

app.include_router(gemini.router)
app.include_router(sku.router)
app.mount(
    "/uploads",
    staticfiles.StaticFiles(directory=str(_UPLOAD_DIR)),
    name="uploads",
)


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Return the service health status for local and container checks."""
    return {"status": "ok"}
