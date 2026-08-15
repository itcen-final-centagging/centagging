"""라우터에서 공통으로 사용하는 FastAPI 의존성입니다."""

from fastapi import Depends
from sqlalchemy.ext import asyncio as sqlalchemy_async

from app.core import config, database
from app.services.gemini_service import GeminiService
from app.services.similar_sku_service import SimilarSkuService
from app.services.sku_image_storage import SkuImageStorage
from app.services.sku_match_service import SkuMatchService
from app.services.tagging_service import TaggingService
from app.services.xai_scoring_service import XaiScoringService


def get_sku_image_storage() -> SkuImageStorage:
    """설정된 SKU 이미지 저장소를 반환합니다.

    Returns:
        SKU 이미지 저장 경로와 공개 URL 변환기입니다.
    """
    return SkuImageStorage(config.get_settings().sku_image_root)


def get_tagging_service(
    session: sqlalchemy_async.AsyncSession = Depends(
        database.get_database_session
    ),
) -> TaggingService:
    """요청 범위 세션으로 태깅 오케스트레이션 서비스를 조립합니다.

    Args:
        session: 요청 범위의 비동기 SQLAlchemy 세션입니다.

    Returns:
        유사 SKU 조회와 XAI 채점이 주입된 TaggingService입니다.
    """
    settings = config.get_settings()

    return TaggingService(
        session=session,
        settings=settings,
        similar_sku_service=SimilarSkuService(
            session=session,
            gemini_service=GeminiService(settings=settings),
            settings=settings,
        ),
        xai_scoring_service=XaiScoringService(settings=settings),
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
