from fastapi import Depends

from app.services.similar_sku_service import SimilarSkuService
from sqlalchemy.ext import asyncio as sqlalchemy_async

from app.core.database import get_database_session

def get_similar_sku_service(
        session: sqlalchemy_async.AsyncSession = Depends(
            get_database_session
        )
):
    return SimilarSkuService(session)