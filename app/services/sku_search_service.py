"""SKU 카탈로그의 텍스트 임베딩 기반 유사도 검색 기능을 제공합니다."""

import pgvector.sqlalchemy as pgvector_sa  # type: ignore[import-untyped]
import sqlalchemy
from sqlalchemy import orm
from sqlalchemy.ext import asyncio as sqlalchemy_async

from app.models.sku import SkuCatalog, SkuImage
from app.schemas import sku_search as sku_search_schema
from app.services.gemini_service import GeminiService, GeminiConfigurationError
from app.services.sku_image_storage import SkuImageStorage

EMBEDDING_DIMENSIONS = 3072
DEFAULT_RESULT_LIMIT = 5
_HALFVEC = pgvector_sa.HALFVEC(EMBEDDING_DIMENSIONS)


class SkuSearchQueryError(RuntimeError):
    """검색어 임베딩 또는 조회 중 발생한 오류입니다."""


def _to_public_url(
    sku_image_storage: SkuImageStorage, stored_path: str | None
) -> str | None:
    """DB 저장 경로가 있으면 공개 URL로 바꾸고, 없으면 None을 반환합니다."""
    if not stored_path:
        return None
    return sku_image_storage.public_url(stored_path)


async def search_skus(
    session: sqlalchemy_async.AsyncSession,
    gemini_service: GeminiService,
    sku_image_storage: SkuImageStorage,
    query: str,
    limit: int = DEFAULT_RESULT_LIMIT,
) -> sku_search_schema.SkuSearchData:
    """검색어와 의미적으로 유사한 SKU를 조회합니다.

    Args:
        session: 비동기 SQLAlchemy 세션입니다.
        gemini_service: 검색어 텍스트 임베딩에 사용하는 서비스입니다.
        sku_image_storage: 대표 이미지 경로를 공개 URL로 바꾸는 저장소입니다.
        query: 검색 프롬프트입니다.
        limit: 반환할 최대 SKU 개수입니다 (기본 5건).

    Returns:
        유사도 내림차순으로 정렬된 SKU 검색 결과입니다.

    Raises:
        GeminiConfigurationError: Gemini 설정 오류
        SkuSearchQueryError: 검색어 임베딩에 실패했거나 응답 차원이
            올바르지 않은 경우입니다.
    """
    try:
        embedding = gemini_service.embed_text(query)
    except GeminiConfigurationError:
        raise
    except Exception as error:
        raise SkuSearchQueryError("검색어 임베딩에 실패했습니다.") from error

    if len(embedding) != EMBEDDING_DIMENSIONS:
        raise SkuSearchQueryError(
            f"임베딩 벡터 차원은 {EMBEDDING_DIMENSIONS} 차원이어야 "
            f"합니다. 현재 {len(embedding)} 차원입니다."
        )

    query_vector = sqlalchemy.cast(list(embedding), _HALFVEC)
    distance = (
        sqlalchemy.cast(SkuCatalog.text_embedding, _HALFVEC)
        .cosine_distance(query_vector)
        .label("distance")
    )

    main_image = orm.aliased(SkuImage, name="main_image")
    stmt = (
        sqlalchemy.select(
            SkuCatalog.sku_code,
            SkuCatalog.product_name,
            SkuCatalog.category,
            SkuCatalog.sub_category,
            SkuCatalog.brand,
            SkuCatalog.price,
            main_image.image_url,
            (1 - distance).label("similarity"),
        )
        .where(SkuCatalog.text_embedding.is_not(None))
        .outerjoin(
            main_image,
            sqlalchemy.and_(
                main_image.sku_id == SkuCatalog.sku_id,
                main_image.image_type == "MAIN",
            ),
        )
        .order_by(distance)
        .limit(limit)
    )

    rows = (await session.execute(stmt)).mappings().all()

    items = [
        sku_search_schema.SkuSearchItem(
            sku_code=row["sku_code"],
            product_name=row["product_name"],
            category=row["category"],
            sub_category=row["sub_category"],
            image_url=_to_public_url(sku_image_storage, row["image_url"]),
            brand=row["brand"],
            price=row["price"],
            similarity_score=round(
                max(0.0, min(100.0, row["similarity"] * 100)), 1
            ),
        )
        for row in rows
    ]

    return sku_search_schema.SkuSearchData(skus=items)


async def get_sku_detail(
    session: sqlalchemy_async.AsyncSession,
    sku_image_storage: SkuImageStorage,
    sku_code: str,
) -> sku_search_schema.SkuDetailData | None:
    """SKU 코드로 카테고리별 속성을 포함한 상세 정보를 조회합니다.

    Args:
        session: 비동기 SQLAlchemy 세션입니다.
        sku_image_storage: 대표 이미지 경로를 공개 URL로 바꾸는 저장소입니다.
        sku_code: 조회할 SKU 코드입니다.

    Returns:
        SKU 상세 정보이며, 존재하지 않으면 None입니다.
    """
    main_image = orm.aliased(SkuImage, name="main_image")
    stmt = (
        sqlalchemy.select(
            SkuCatalog.sku_id,
            SkuCatalog.sku_code,
            SkuCatalog.product_name,
            SkuCatalog.brand,
            SkuCatalog.price,
            SkuCatalog.category,
            SkuCatalog.sub_category,
            SkuCatalog.attributes,
            main_image.image_url,
            main_image.sku_image_id,
        )
        .outerjoin(
            main_image,
            sqlalchemy.and_(
                main_image.sku_id == SkuCatalog.sku_id,
                main_image.image_type == "MAIN",
            ),
        )
        .where(SkuCatalog.sku_code == sku_code)
    )
    row = (await session.execute(stmt)).mappings().first()
    if row is None:
        return None

    return sku_search_schema.SkuDetailData(
        sku_id=row["sku_id"],
        sku_code=row["sku_code"],
        product_name=row["product_name"],
        brand=row["brand"],
        price=row["price"],
        category=row["category"],
        sub_category=row["sub_category"],
        attrs=row["attributes"] or {},
        image_url=_to_public_url(sku_image_storage, row["image_url"]),
        sku_image_id=row["sku_image_id"],
    )
