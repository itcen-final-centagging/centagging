from fastapi import Depends

from app.services.similar_sku_service import SimilarSkuService
from sqlalchemy.ext import asyncio as sqlalchemy_async

from app.core import config, database
from app.services.gemini_service import GeminiService

def get_similar_sku_service(
        session: sqlalchemy_async.AsyncSession = Depends(
            database.get_database_session
        )
):
    settings = config.get_settings()

    return SimilarSkuService(
        session=session,
        gemini_service=GeminiService(settings=settings),
        settings=settings,
    )