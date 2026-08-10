"""SKU 카탈로그의 키워드 검색 기능을 제공합니다."""

import sqlalchemy
from sqlalchemy.ext import asyncio as sqlalchemy_async

from app.schemas import sku_search as sku_search_schema


_COUNT_SKUS = sqlalchemy.text("""
    SELECT COUNT(*)
    FROM sku_catalog
    WHERE sku_code ILIKE :keyword
       OR product_name ILIKE :keyword
    """)

_SEARCH_SKUS = sqlalchemy.text("""
    SELECT
        sku_code,
        product_name,
        category,
        sub_category
    FROM sku_catalog
    WHERE sku_code ILIKE :keyword
       OR product_name ILIKE :keyword
    ORDER BY lower(product_name) ASC, sku_code ASC
    LIMIT :size
    OFFSET :offset
    """)


async def search_skus(
    session: sqlalchemy_async.AsyncSession,
    keyword: str,
    page: int,
    size: int,
) -> sku_search_schema.SkuSearchData:
    """키워드와 부분 일치하는 SKU를 조회합니다.

    Args:
        session: 비동기 SQLAlchemy 세션입니다.
        keyword: SKU 코드 또는 상품명 검색어입니다.
        page: 0부터 시작하는 페이지 번호입니다.
        size: 페이지당 결과 개수입니다.

    Returns:
        전체 검색 개수와 현재 페이지의 SKU 목록입니다.
    """
    keyword_pattern = f"%{keyword}%"

    count_result = await session.execute(
        _COUNT_SKUS,
        {"keyword": keyword_pattern},
    )
    total_count = int(count_result.scalar_one())

    search_result = await session.execute(
        _SEARCH_SKUS,
        {
            "keyword": keyword_pattern,
            "size": size,
            "offset": page * size,
        },
    )

    items = [
        sku_search_schema.SkuSearchItem(**row)
        for row in search_result.mappings().all()
    ]

    return sku_search_schema.SkuSearchData(
        total_count=total_count,
        page=page,
        size=size,
        items=items,
    )