"""라우터에서 공통으로 사용하는 FastAPI 의존성입니다."""

from fastapi import Depends
from sqlalchemy.ext import asyncio as sqlalchemy_async

from app.core import config, database
from app.services.gemini_service import GeminiService
from app.services.similar_sku_service import SimilarSkuService
from app.services.sku_match_service import SkuMatchService


def get_similar_sku_service(
    session: sqlalchemy_async.AsyncSession = Depends(
        database.get_database_session
    ),
) -> SimilarSkuService:
    """요청 범위 세션으로 유사 SKU 조회 서비스를 조립합니다.

    Args:
        session: 요청 범위의 비동기 SQLAlchemy 세션입니다.

    Returns:
        Gemini 임베딩 서비스와 설정이 주입된 SimilarSkuService입니다.
    """
    settings = config.get_settings()

    return SimilarSkuService(
        session=session,
        gemini_service=GeminiService(settings=settings),
        settings=settings,
    )


def get_sku_match_service(
    session: sqlalchemy_async.AsyncSession = Depends(
        database.get_database_session
    ),
) -> SkuMatchService:
    """요청 범위 세션으로 SKU 확정 서비스를 조립합니다.

    Args:
        session: 요청 범위의 비동기 SQLAlchemy 세션입니다.

    Returns:
        설정이 주입된 SkuMatchService입니다.
    """
    return SkuMatchService(
        session=session,
        settings=config.get_settings(),
    )
