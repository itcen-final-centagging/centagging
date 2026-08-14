"""크롭 이미지 임베딩을 이용해 유사 SKU를 조회하는 서비스입니다."""

import asyncio
import collections.abc
import logging
import typing

import pgvector.sqlalchemy as pgvector_sa  # type: ignore[import-untyped]
import pydantic
import sqlalchemy
from sqlalchemy import orm
from sqlalchemy.ext import asyncio as sqlalchemy_async

from app.core import config
from app.models.sku import SkuCatalog, SkuImage
from app.schemas.tagging import (
    DetectedObject,
    MatchedSkuImage,
    SkuCandidate,
    XaiResult,
)
from app.services.gemini_service import GeminiService
from app.services.image_processing_service import CroppedObject
from app.services.sku_image_storage import SkuImageStorage

EMBEDDING_DIMENSIONS = 3072
CANDIDATE_LIMIT = 30
DEFAULT_RESULT_LIMIT = 5
EMBED_CONCURRENCY = 2
NO_XAI_SUMMARY = "XAI 판정 결과가 없습니다."
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


_LOGGER = logging.getLogger(__name__)


class SimilarSkuService:
    """크롭 이미지 임베딩으로 유사 SKU를 조회하는 서비스입니다."""

    def __init__(
        self,
        session: sqlalchemy_async.AsyncSession,
        gemini_service: GeminiService,
        settings: config.Settings,
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
        self.sku_image_storage = SkuImageStorage(settings.sku_image_root)
        self._embed_semaphore = asyncio.Semaphore(EMBED_CONCURRENCY)

    async def build_detected_objects(
        self,
        crops: list[CroppedObject],
    ) -> list[DetectedObject]:
        """크롭 목록으로 SKU 후보까지 채운 탐지 객체를 만듭니다.

        임베딩은 외부 API 왕복이라 ``asyncio.gather``로 동시에 호출합니다.
        유사도 조회는 요청 범위 ``AsyncSession``을 공유하며 세션은 동시
        사용이 불가능하므로 순차로 실행합니다.

        Args:
            crops: 장면 이미지에서 잘라낸 탐지 객체 목록입니다.

        Returns:
            sku_candidates까지 채워진 탐지 객체 목록입니다. label과
            confidence 등 XAI 관련 필드는 아직 기본값입니다.
        """
        if not crops:
            return []

        embeddings = await asyncio.gather(
            *(self._embed_crop(crop) for crop in crops),
            return_exceptions=True,
        )

        detected_objects = []
        for crop, embedding in zip(crops, embeddings):
            similar_skus = await self._find_skus_for_crop(crop, embedding)
            detected_objects.append(
                DetectedObject(
                    object_index=crop.crop_index,
                    bbox=crop.bbox,
                    sku_candidates=[
                        self._to_sku_candidate(sku) for sku in similar_skus
                    ],
                )
            )

        return detected_objects

    async def _find_skus_for_crop(
        self,
        crop: CroppedObject,
        embedding: list[float] | BaseException,
    ) -> list["SimilarSku"]:
        """임베딩 1건으로 유사 SKU를 조회합니다.

        Args:
            crop: 조회 대상 크롭입니다.
            embedding: ``asyncio.gather``가 돌려준 임베딩 또는 예외입니다.

        Returns:
            유사 SKU 목록이며, 임베딩·조회에 실패하면 빈 목록입니다.
        """
        # 크롭 1건의 실패가 나머지 크롭 추천까지 막지 않도록 폴백합니다.
        if isinstance(embedding, BaseException):
            _LOGGER.warning(
                "크롭 임베딩 실패로 SKU 후보를 비웁니다: crop_index=%s",
                crop.crop_index,
                exc_info=embedding,
            )
            return []

        try:
            return await self.find_similar_skus(embedding)
        except SimilarSkuQueryError:
            _LOGGER.exception(
                "유사 SKU 조회 실패로 후보를 비웁니다: crop_index=%s",
                crop.crop_index,
            )
            return []

    async def _embed_crop(self, crop: CroppedObject) -> list[float]:
        """크롭 1건을 임베딩합니다. 동시 호출 수를 세마포어로 제한합니다.

        Args:
            crop: 임베딩할 크롭입니다.

        Returns:
            크롭 이미지의 임베딩 벡터입니다.
        """
        async with self._embed_semaphore:
            return await asyncio.to_thread(
                self.gemini_service.embed_image, crop.image
            )

    def _to_sku_candidate(self, sku: "SimilarSku") -> SkuCandidate:
        """유사도 조회 결과를 응답용 SKU 후보로 변환합니다.

        similarity_score는 임베딩 유사도 기반 잠정값이며, XAI 채점
        단계에서 루브릭 총점으로 덮어씁니다.

        Args:
            sku: 유사도 조회로 얻은 SKU 1건입니다.

        Returns:
            XAI 결과가 비어 있는 SKU 후보입니다.
        """
        return SkuCandidate(
            sku_code=sku.sku_code,
            product_name=sku.product_name,
            category=sku.category or "",
            sub_category=sku.sub_category or "",
            attrs={
                key: str(value) for key, value in (sku.attributes or {}).items()
            },
            similarity_score=max(0, min(100, round(sku.similarity * 100))),
            matched_sku_image=MatchedSkuImage(
                sku_image_id=sku.sku_image_id,
                image_type=sku.image_type,
                image_url=self.sku_image_storage.public_url(sku.image_url),
            ),
            xai_result=XaiResult(summary=NO_XAI_SUMMARY),
        )

    async def find_similar_skus(
        self,
        embedding: collections.abc.Sequence[float],
        limit: int = DEFAULT_RESULT_LIMIT,
    ) -> list[SimilarSku]:
        """임베딩 벡터와 코사인 거리가 가까운 SKU를 조회합니다.

        Args:
            embedding: 크롭 이미지의 임베딩 벡터입니다.
            limit: 반환할 최대 SKU 개수입니다.

        Returns:
            유사도 내림차순으로 정렬된 SKU 목록입니다.

        Raises:
            SimilarSkuQueryError: 임베딩 차원이 맞지 않는 경우입니다.
        """
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
        # SQLAlchemy 동적 함수의 반환형을 Pylint가 None으로 오인합니다.
        # pylint: disable-next=assignment-from-no-return
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
