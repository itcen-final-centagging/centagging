"""크롭 이미지 임베딩을 이용해 유사 SKU를 조회하는 서비스입니다."""

import asyncio
import collections.abc
import pathlib
import typing

import pgvector.sqlalchemy as pgvector_sa  # type: ignore[import-untyped]
import pydantic
import sqlalchemy
from PIL import Image
from sqlalchemy.ext import asyncio as sqlalchemy_async

from app.core import config
from app.schemas.tagging import (
    DetectedObject,
    DetectionResult,
    MatchedSkuImage,
    SkuCandidate,
    XaiResult,
)
from app.services.gemini_service import GeminiService
from app.services.image_processing_service import get_crop_image

EMBEDDING_DIMENSIONS = 3072
CANDIDATE_LIMIT = 30
DEFAULT_RESULT_LIMIT = 5


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
    category: str
    sub_category: str
    attributes: dict[str, typing.Any]
    similarity: float


class SceneCropData(typing.TypedDict):
    """scene_image에서 조회한 원본 이미지 경로와 대상 좌표입니다."""

    image_url: str
    indexed_coords: list[tuple[int, dict[str, float]]]


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
               c.sku_id, c.sku_image_id, c.image_url, c.image_type, c.distance
          FROM candidate c
         ORDER BY c.sku_id, c.distance
    )
    SELECT b.sku_id,
           b.sku_image_id,
           b.image_url,
           b.image_type,
           sc.sku_code,
           sc.product_name,
           sc.category,
           sc.sub_category,
           sc.attributes,
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

_CROP_IMAGE_COORD_QUERY = sqlalchemy.text("""
    SELECT image_url, bbox_coord
      FROM scene_image
     WHERE scene_image_id = :scene_image_id
    """)


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

    async def orchestrate_similar_skus(
        self,
        scene_id: int,
        object_indexes: list[int],
    ) -> DetectionResult:
        """탐지 객체별로 크롭·임베딩·유사 SKU 조회를 순서대로 수행합니다.

        Args:
            scene_id: 조회할 장면 이미지 ID입니다.
            object_indexes: 추천을 조회할 탐지 객체 인덱스 목록입니다.

        Returns:
            요청한 탐지 객체별 유사 SKU 후보가 담긴 결과입니다.

        Raises:
            SceneImageNotFoundError: scene_id에 해당하는 장면 이미지가
                없는 경우입니다.
        """
        scene = await self.get_crop_image_coords(scene_id, object_indexes)

        image_path = pathlib.Path(self.settings.image_storage_root) / scene[
            "image_url"
        ].removeprefix("/uploads/")

        objects = []

        with Image.open(image_path, "r") as scene_image:
            for object_index, coord in scene["indexed_coords"]:
                crop_image = get_crop_image(scene_image, coord)
                embedding = await asyncio.to_thread(
                    self.gemini_service.embed_image, crop_image
                )
                similar_skus = await self.find_similar_skus(embedding)

                objects.append(
                    DetectedObject(
                        object_index=object_index,
                        bbox_coord=coord,
                        sku_candidates=[
                            SkuCandidate(
                                sku_code=sku.sku_code,
                                product_name=sku.product_name,
                                category=sku.category or "",
                                sub_category=sku.sub_category or "",
                                attrs={
                                    key: str(value)
                                    for key, value in sku.attributes.items()
                                },
                                similarity_score=int(sku.similarity * 100),
                                matched_sku_image=MatchedSkuImage(
                                    sku_image_id=sku.sku_image_id,
                                    image_type=sku.image_type,
                                    image_url=sku.image_url,
                                ),
                                xai_result=XaiResult(
                                    summary=(
                                        "XAI 판정 요약은 아직 구현되지 "
                                        "않았습니다."
                                    )
                                ),
                            )
                            for sku in similar_skus
                        ],
                    )
                )
        return DetectionResult(
            processing_status="DETECTED",
            objects=objects,
        )

    async def get_crop_image_coords(
        self,
        scene_id: int,
        object_indexes: list[int],
    ) -> SceneCropData:
        """장면 이미지 경로와 요청된 인덱스의 좌표를 함께 조회합니다.

        Args:
            scene_id: 조회할 장면 이미지 ID입니다.
            object_indexes: 좌표를 조회할 탐지 객체 인덱스 목록입니다.
                범위를 벗어난 인덱스는 조용히 무시합니다.

        Returns:
            원본 이미지 경로와 `(원래 인덱스, 좌표)` 쌍 목록입니다.
            enumerate로 다시 번호를 매기지 않도록 인덱스를 좌표와 함께
            유지합니다.

        Raises:
            SceneImageNotFoundError: scene_id에 해당하는 장면 이미지가
                없는 경우입니다.
        """
        result = await self.session.execute(
            _CROP_IMAGE_COORD_QUERY,
            {"scene_image_id": scene_id},
        )
        row = result.mappings().first()
        if row is None:
            raise SceneImageNotFoundError(scene_id)

        coords = row["bbox_coord"]
        indexed_coords = [
            (i, coords[i]) for i in object_indexes if 0 <= i < len(coords)
        ]

        return {
            "image_url": row["image_url"],
            "indexed_coords": indexed_coords,
        }

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
                f"임베딩 벡터 차원은 {EMBEDDING_DIMENSIONS} 차원이어야 "
                f"합니다. 현재 {len(embedding)} 차원입니다."
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
