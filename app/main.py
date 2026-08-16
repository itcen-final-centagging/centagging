"""Centagging FastAPI 애플리케이션 진입점입니다. / FastAPI application entry point."""

import collections.abc
import contextlib

import fastapi
import starlette.staticfiles

from app.api import (
    approval,
    auth,
    history,
    product_image_submissions,
    scene_images,
    sku,
    sku_search,
    tagging,
)
from app.core import (
    config,
    database,
    exception_handlers,
    openapi,
    request_context,
)
from app.services import user_seed


@contextlib.asynccontextmanager
async def lifespan(_: fastapi.FastAPI) -> collections.abc.AsyncIterator[None]:
    """서버 시작 시 고정 사용자들을 준비하고 종료 시 DB를 정리합니다."""
    try:
        await user_seed.initialize_users()
        yield
    finally:
        await database.database_engine.dispose()


app = fastapi.FastAPI(
    title="Centagging API",
    description="VLM 기반 가구 자동 태깅 및 SKU 매칭 API",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(request_context.RequestIdMiddleware)
exception_handlers.register_exception_handlers(app)
openapi.configure_common_response_openapi(app)

app.include_router(auth.router)
app.include_router(scene_images.router)
app.include_router(tagging.router)
app.include_router(sku.router)
app.include_router(sku_search.router)
app.include_router(history.router)
app.include_router(approval.router)
app.include_router(product_image_submissions.router)

app.mount(
    "/sku-images",
    starlette.staticfiles.StaticFiles(
        directory=config.get_settings().sku_image_root, check_dir=False
    ),
    name="sku-images",
)

app.mount(
    "/uploads",
    starlette.staticfiles.StaticFiles(
        directory=config.get_settings().image_storage_root, check_dir=False
    ),
    name="uploads",
)


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Return the service health status for local and container checks."""
    return {"status": "ok"}
