"""Centagging FastAPI 애플리케이션 진입점입니다. / FastAPI application entry point."""

import fastapi

from app.api import gemini, furniture_detection

app = fastapi.FastAPI(
    title="Centagging API",
    description="VLM 기반 가구 자동 태깅 및 SKU 매칭 API",
    version="0.1.0",
)

app.include_router(gemini.router)
app.include_router(furniture_detection.router)


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Return the service health status for local and container checks."""
    return {"status": "ok"}
