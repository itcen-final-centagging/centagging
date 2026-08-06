"""PostgreSQL/pgvector persistence for SKU candidates and HITL reviews."""

import dataclasses
import json
import logging
import typing

import psycopg
from psycopg.rows import dict_row

from app.core import config

LOGGER = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class CatalogItem:
    """A seed SKU available to the PoC catalog."""

    sku: str
    name: str
    category: str
    kind: str
    color: str
    material: str
    size: str
    image_filename: str
    key_features: tuple[str, ...]
    attributes: dict[str, str]


CATALOG_ITEMS: tuple[CatalogItem, ...] = (
    CatalogItem(
        sku="sku_chair",
        name="에르고 메쉬 오피스체어 화이트",
        category="의자",
        kind="chair",
        color="화이트",
        material="메쉬 · 패브릭 · 알루미늄",
        size="W660 × D620 × H1,110 mm",
        image_filename="sku_chair.jpg",
        key_features=("메쉬", "화이트 프레임", "5스타 캐스터", "하이백"),
        attributes={
            "형태": "하이백",
            "구조": "5스타 캐스터",
            "공간": "홈오피스",
        },
    ),
    CatalogItem(
        sku="sku_chair_black",
        name="에르고 메쉬 오피스체어 블랙",
        category="의자",
        kind="chair",
        color="블랙",
        material="메쉬 · 패브릭 · 알루미늄",
        size="W660 × D620 × H1,110 mm",
        image_filename="sku_chair_black.jpg",
        key_features=("메쉬", "블랙 프레임", "5스타 캐스터", "하이백"),
        attributes={
            "형태": "하이백",
            "구조": "5스타 캐스터",
            "공간": "홈오피스",
        },
    ),
    CatalogItem(
        sku="sku_desk",
        name="오피스 책상 원목",
        category="테이블",
        kind="table",
        color="오크",
        material="원목 · 스틸",
        size="W1,400 × D700 × H740 mm",
        image_filename="sku_desk.jpg",
        key_features=("원목 상판", "화이트 프레임", "직사각형", "책상"),
        attributes={"형태": "직사각형", "구조": "4다리", "공간": "홈오피스"},
    ),
    CatalogItem(
        sku="sku_lamp",
        name="데스크 스탠드 블랙",
        category="조명",
        kind="lamp",
        color="블랙",
        material="스틸 · 패브릭",
        size="W280 × D280 × H520 mm",
        image_filename="sku_lamp.jpg",
        key_features=("블랙", "스탠드", "원형 갓", "간접 조명"),
        attributes={"형태": "스탠드", "구조": "원형 베이스", "공간": "데스크"},
    ),
    CatalogItem(
        sku="sku_cabinet",
        name="이동식 서랍장 화이트",
        category="수납",
        kind="cabinet",
        color="화이트",
        material="스틸",
        size="W400 × D500 × H600 mm",
        image_filename="sku_cabinet.jpg",
        key_features=("화이트", "서랍", "캐스터", "수납"),
        attributes={"형태": "3단 서랍", "구조": "4개 캐스터", "공간": "오피스"},
    ),
)


class CatalogRepository:
    """Synchronous repository kept small enough for the current PoC scale."""

    def __init__(self, settings: config.Settings) -> None:
        self._settings = settings
        self._is_available = False

    @property
    def is_available(self) -> bool:
        """Return whether the database was initialized successfully."""
        return self._is_available

    def initialize(self) -> None:
        """Create pgvector-backed tables and seed catalog attributes."""
        try:
            with self._connect() as connection:
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS sku_catalog (
                        sku TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        category TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        color TEXT NOT NULL,
                        material TEXT NOT NULL,
                        size TEXT NOT NULL,
                        image_filename TEXT NOT NULL,
                        key_features JSONB NOT NULL DEFAULT '[]'::jsonb,
                        attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
                        embedding VECTOR(768)
                    )
                    """)
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS tagging_reviews (
                        id UUID PRIMARY KEY,
                        analysis_id UUID NOT NULL,
                        object_id TEXT NOT NULL,
                        object_name TEXT NOT NULL,
                        image_name TEXT NOT NULL,
                        sku TEXT NOT NULL REFERENCES sku_catalog(sku),
                        tags JSONB NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """)
            self._is_available = True
            self.upsert_catalog(CATALOG_ITEMS)
        except psycopg.Error as error:
            LOGGER.warning(
                "PostgreSQL is unavailable; using in-memory fallback: %s", error
            )
            self._is_available = False

    def upsert_catalog(self, items: typing.Iterable[CatalogItem]) -> None:
        """Insert catalog metadata without overwriting an existing embedding."""
        if not self._is_available:
            return
        query = """
            INSERT INTO sku_catalog (
                sku, name, category, kind, color, material, size, image_filename,
                key_features, attributes
            ) VALUES (
                %(sku)s, %(name)s, %(category)s, %(kind)s, %(color)s,
                %(material)s, %(size)s, %(image_filename)s,
                %(key_features)s::jsonb, %(attributes)s::jsonb
            )
            ON CONFLICT (sku) DO UPDATE SET
                name = EXCLUDED.name,
                category = EXCLUDED.category,
                kind = EXCLUDED.kind,
                color = EXCLUDED.color,
                material = EXCLUDED.material,
                size = EXCLUDED.size,
                image_filename = EXCLUDED.image_filename,
                key_features = EXCLUDED.key_features,
                attributes = EXCLUDED.attributes
        """
        try:
            with self._connect() as connection:
                for item in items:
                    connection.execute(
                        query,
                        {
                            "sku": item.sku,
                            "name": item.name,
                            "category": item.category,
                            "kind": item.kind,
                            "color": item.color,
                            "material": item.material,
                            "size": item.size,
                            "image_filename": item.image_filename,
                            "key_features": json.dumps(item.key_features),
                            "attributes": json.dumps(item.attributes),
                        },
                    )
        except psycopg.Error as error:
            LOGGER.warning("Could not seed catalog metadata: %s", error)
            self._is_available = False

    def get_items_missing_embeddings(self) -> list[CatalogItem]:
        """Return catalog records that still need their image vector generated."""
        if not self._is_available:
            return list(CATALOG_ITEMS)
        try:
            with self._connect(row_factory=dict_row) as connection:
                rows = connection.execute("""
                    SELECT sku, name, category, kind, color, material, size,
                           image_filename, key_features, attributes
                    FROM sku_catalog
                    WHERE embedding IS NULL
                    ORDER BY sku
                    """).fetchall()
            return [self._row_to_item(row) for row in rows]
        except psycopg.Error as error:
            LOGGER.warning(
                "Could not load unembedded catalog records: %s", error
            )
            self._is_available = False
            return list(CATALOG_ITEMS)

    def save_embedding(self, sku: str, embedding: list[float]) -> None:
        """Persist a normalized 768-dimensional product image vector."""
        if not self._is_available:
            return
        try:
            with self._connect() as connection:
                connection.execute(
                    "UPDATE sku_catalog SET embedding = %s::vector WHERE sku = %s",
                    (self._vector_literal(embedding), sku),
                )
        except psycopg.Error as error:
            LOGGER.warning("Could not save %s embedding: %s", sku, error)
            self._is_available = False

    def search_by_embedding(
        self,
        embedding: list[float],
        category: str,
        limit: int,
    ) -> list[tuple[CatalogItem, float]]:
        """Return Top-K candidates using cosine similarity and category filtering."""
        if not self._is_available:
            return []
        query = """
            SELECT sku, name, category, kind, color, material, size,
                   image_filename, key_features, attributes,
                   1 - (embedding <=> %(embedding)s::vector) AS vector_score
            FROM sku_catalog
            WHERE embedding IS NOT NULL
              AND (%(category)s = '' OR category = %(category)s)
            ORDER BY embedding <=> %(embedding)s::vector
            LIMIT %(limit)s
        """
        try:
            with self._connect(row_factory=dict_row) as connection:
                rows = connection.execute(
                    query,
                    {
                        "embedding": self._vector_literal(embedding),
                        "category": category,
                        "limit": limit,
                    },
                ).fetchall()
            return [
                (self._row_to_item(row), float(row["vector_score"]))
                for row in rows
            ]
        except psycopg.Error as error:
            LOGGER.warning("Vector search is unavailable: %s", error)
            self._is_available = False
            return []

    def search_catalog(self, query: str) -> list[CatalogItem]:
        """Search the full catalog by SKU or product name."""
        if not self._is_available:
            return self._filter_seed_items(query)
        try:
            with self._connect(row_factory=dict_row) as connection:
                rows = connection.execute(
                    """
                    SELECT sku, name, category, kind, color, material, size,
                           image_filename, key_features, attributes
                    FROM sku_catalog
                    WHERE sku ILIKE %(query)s OR name ILIKE %(query)s
                    ORDER BY name
                    LIMIT 30
                    """,
                    {"query": f"%{query}%"},
                ).fetchall()
            return [self._row_to_item(row) for row in rows]
        except psycopg.Error as error:
            LOGGER.warning("Catalog search is unavailable: %s", error)
            self._is_available = False
            return self._filter_seed_items(query)

    def save_review(self, review: dict[str, typing.Any]) -> None:
        """Save a confirmed decision into the persistent HITL review queue."""
        if not self._is_available:
            return
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO tagging_reviews (
                        id, analysis_id, object_id, object_name, image_name, sku, tags
                    ) VALUES (
                        %(id)s, %(analysis_id)s, %(object_id)s, %(object_name)s,
                        %(image_name)s, %(sku)s, %(tags)s::jsonb
                    )
                    """,
                    {**review, "tags": json.dumps(review["tags"])},
                )
        except psycopg.Error as error:
            LOGGER.warning("Could not save HITL review: %s", error)
            self._is_available = False

    def get_history(self) -> list[dict[str, typing.Any]]:
        """Return saved reviews joined with their selected SKU names."""
        if not self._is_available:
            return []
        try:
            with self._connect(row_factory=dict_row) as connection:
                return connection.execute("""
                    SELECT review.id, review.image_name, review.object_name,
                           catalog.name AS product_name, review.created_at,
                           review.sku, review.tags
                    FROM tagging_reviews AS review
                    INNER JOIN sku_catalog AS catalog ON catalog.sku = review.sku
                    ORDER BY review.created_at DESC
                    LIMIT 100
                    """).fetchall()
        except psycopg.Error as error:
            LOGGER.warning("Could not load HITL history: %s", error)
            self._is_available = False
            return []

    def _connect(self, **kwargs: typing.Any) -> psycopg.Connection[typing.Any]:
        return psycopg.connect(
            self._settings.database_url, connect_timeout=3, **kwargs
        )

    @staticmethod
    def _vector_literal(embedding: list[float]) -> str:
        return "[" + ",".join(str(value) for value in embedding) + "]"

    @staticmethod
    def _row_to_item(row: dict[str, typing.Any]) -> CatalogItem:
        key_features = row["key_features"]
        attributes = row["attributes"]
        return CatalogItem(
            sku=row["sku"],
            name=row["name"],
            category=row["category"],
            kind=row["kind"],
            color=row["color"],
            material=row["material"],
            size=row["size"],
            image_filename=row["image_filename"],
            key_features=tuple(key_features),
            attributes=attributes,
        )

    @staticmethod
    def _filter_seed_items(query: str) -> list[CatalogItem]:
        normalized_query = query.lower()
        return [
            item
            for item in CATALOG_ITEMS
            if normalized_query in item.sku.lower()
            or normalized_query in item.name.lower()
        ]
