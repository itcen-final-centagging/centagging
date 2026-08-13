"""크롭 이미지 임베딩을 이용해 유사 SKU를 조회하는 서비스입니다."""

import collections.abc
import logging
import typing

import pgvector.sqlalchemy as pgvector_sa  # type: ignore[import-untyped]
import pydantic
import sqlalchemy
from sqlalchemy.ext import asyncio as sqlalchemy_async
from sqlalchemy import orm

from app.core import config
from app.schemas.tagging import (
    SceneImageInfo,
)
from app.services.gemini_service import GeminiService
from app.services.xai_scoring_service import XaiScoringService

from app.models.sku import SkuCatalog, SkuImage

EMBEDDING_DIMENSIONS = 3072
CANDIDATE_LIMIT = 30
DEFAULT_RESULT_LIMIT = 5
_HALFVEC = pgvector_sa.HALFVEC(EMBEDDING_DIMENSIONS)

class SceneImageNotFoundError(RuntimeError):
    """존재하지 않는 scene_image_id로 조회한 경우입니다."""


class SimilarSkuQueryError(RuntimeError):
    """유사 SKU 검색 중 발생한 오류입니다."""


class SimilarSku(pydantic.BaseModel):
    """유사도 검색으로 조회한 SKU 1건입니다."""

    sku_id: int
    sku_image_id: int
    sku_code: str
    product_name: str
    image_url: str
    image_type: typing.Literal["MAIN", "ANGLE"]
    category: str | None = None
    sub_category: str | None = None
    attributes: dict[str, typing.Any] = pydantic.Field(default_factory=dict)
    similarity: float


class SceneCropData(typing.TypedDict):
    """scene_image에서 조회한 원본 이미지 경로와 대상 좌표입니다."""

    scene_image: SceneImageInfo
    image_url: str
    indexed_coords: list[tuple[int, dict[str, float]]]

_LOGGER = logging.getLogger(__name__)

class SimilarSkuService:
    """크롭 이미지 임베딩으로 유사 SKU를 조회하는 서비스입니다."""

    def __init__(
        self,
        session: sqlalchemy_async.AsyncSession,
        gemini_service: GeminiService,
        settings: config.Settings,
        scoring_service: XaiScoringService,
    ) -> None:
        """서비스가 사용할 세션과 의존 객체를 주입받습니다.

        Args:
            session: 요청 범위의 비동기 SQLAlchemy 세션입니다.
            gemini_service: 크롭 이미지 임베딩을 수행하는 서비스입니다.
            settings: 이미지 저장소 경로가 담긴 애플리케이션 설정입니다.
        """
        self.session = session
        self.gemini_service = gemini_service
        self.settings = settings
        self.scoring_service = scoring_service

    async def find_similar_skus(
            self,
            embedding: collections.abc.Sequence[float],
            limit: int = DEFAULT_RESULT_LIMIT,
    ) -> list[SimilarSku]:
        if len(embedding) != EMBEDDING_DIMENSIONS:
            raise SimilarSkuQueryError(
                f"임베딩 벡터 차원은 {EMBEDDING_DIMENSIONS} 차원이어야 "
                f"합니다. 현재 {len(embedding)} 차원입니다."
            )

        query_vector = sqlalchemy.cast(list(embedding), _HALFVEC)
        distance = (
            sqlalchemy.cast(SkuImage.embedding, _HALFVEC)
            .cosine_distance(query_vector)
            .label("distance")
        )

        candidate = (
            sqlalchemy.select(SkuImage.sku_id, distance)
            .where(SkuImage.embedding.is_not(None))
            .order_by(distance)
            .limit(CANDIDATE_LIMIT)
            .cte("candidate")
        )

        main_image = orm.aliased(SkuImage, name="main_image")
        min_distance = sqlalchemy.func.min(candidate.c.distance)

        stmt = (
            sqlalchemy.select(
                SkuCatalog.sku_id,
                main_image.sku_image_id,
                main_image.image_url,
                main_image.image_type,
                SkuCatalog.sku_code,
                SkuCatalog.product_name,
                SkuCatalog.category,
                SkuCatalog.sub_category,
                SkuCatalog.attributes,
                (1 - min_distance).label("similarity"),
            )
            .select_from(candidate)
            .join(SkuCatalog, SkuCatalog.sku_id == candidate.c.sku_id)
            .join(
                main_image,
                sqlalchemy.and_(
                    main_image.sku_id == candidate.c.sku_id,
                    main_image.image_type == "MAIN",
                ),
            )
            .group_by(SkuCatalog.sku_id, main_image.sku_image_id)
            .order_by(min_distance)
            .limit(limit)
        )

        rows = (await self.session.execute(stmt)).mappings().all()

        return [SimilarSku.model_validate(dict(row)) for row in rows]