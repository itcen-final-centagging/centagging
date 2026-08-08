"""크롭 이미지 임베딩을 이용해 유사 SKU를 조회하는 서비스입니다."""

import collections.abc

import pgvector.sqlalchemy as pgvector_sa  # type: ignore[import-untyped]
import pydantic
import sqlalchemy
from sqlalchemy.ext import asyncio as sqlalchemy_async

EMBEDDING_DIMENSIONS = 3072
CANDIDATE_LIMIT = 30
DEFAULT_RESULT_LIMIT = 5


class SimilarSkuQueryError(RuntimeError):
    """유사 SKU 검색 중 발생한 오류입니다."""


class SimilarSku(pydantic.BaseModel):
    """유사도 검색으로 조회한 SKU 1건입니다."""

    sku_id: int
    sku_image_id: int
    sku_code: str
    product_name: str
    image_url: str
    similarity: float


_SIMILAR_SKU_QUERY = sqlalchemy.text("""
    WITH candidate AS (
        SELECT si.sku_id,
               si.sku_image_id,
               si.image_url,
               si.embedding::halfvec(3072)
                   <=> CAST(:embedding AS halfvec(3072)) AS distance
          FROM sku_image si
         WHERE si.embedding IS NOT NULL
         ORDER BY distance
         LIMIT :candidate_limit
    ),
    best_per_sku AS (
        SELECT DISTINCT ON (c.sku_id)
               c.sku_id, c.sku_image_id, c.image_url, c.distance
          FROM candidate c
         ORDER BY c.sku_id, c.distance
    )
    SELECT b.sku_id,
           b.sku_image_id,
           b.image_url,
           sc.sku_code,
           sc.product_name,
           1 - b.distance AS similarity
      FROM best_per_sku b
      JOIN sku_catalog sc ON sc.sku_id = b.sku_id
     ORDER BY b.distance
     LIMIT :result_limit
    """).bindparams(
    sqlalchemy.bindparam(
        "embedding",
        type_=pgvector_sa.Vector(EMBEDDING_DIMENSIONS),
    )
)

class SimilarSkuService:
    """크롭 이미지 임베딩으로 유사 SKU를 조회하는 서비스입니다."""

    def __init__(self, session: sqlalchemy_async.AsyncSession):
        """서비스가 사용할 비동기 DB 세션을 주입받습니다.

        Args:
            session: 요청 범위의 비동기 SQLAlchemy 세션입니다.
        """
        self.session = session

    async def find_similar_skus(
        self,
        embedding: collections.abc.Sequence[float],
        limit: int = DEFAULT_RESULT_LIMIT,
    ) -> list[SimilarSku]:
        """임베딩 벡터와 가장 유사한 SKU를 SKU 단위로 중복 없이 조회합니다.

        Args:
            embedding: 검색 기준이 되는 크롭 이미지 임베딩입니다.
            limit: 반환할 최대 SKU 개수입니다.

        Returns:
            유사도 내림차순으로 정렬된 SKU 목록입니다.

        Raises:
            SimilarSkuQueryError: 임베딩 차원이 스키마와 다른 경우입니다.
        """
        if len(embedding) != EMBEDDING_DIMENSIONS:
            raise SimilarSkuQueryError(
                f"임베딩 벡터 차원은 {EMBEDDING_DIMENSIONS} 차원이어야 합니다. "
                f"현재 {len(embedding)} 차원입니다."
            )

        result = await self.session.execute(
            _SIMILAR_SKU_QUERY,
            {
                "embedding": list(embedding),
                "candidate_limit": CANDIDATE_LIMIT,
                "result_limit": limit,
            },
        )
        rows = result.mappings().all()

        return [SimilarSku(**row) for row in rows]
