from fastapi import FastAPI

app = FastAPI(
    title="Centagging API",
    description="VLM 기반 가구 자동 태깅 및 SKU 매칭 API",
    version="0.1.0",
)


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Return the service health status for local and container checks."""
    return {"status": "ok"}
