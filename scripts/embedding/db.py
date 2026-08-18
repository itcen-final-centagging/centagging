"""sku_catalog / sku_image 적재와 임베딩 저장.

docker/db/init/schema.sql의 sku_catalog·sku_image 테이블을 그대로 쓴다.
스키마는 건드리지 않고, 여기서는 적재·갱신 SQL만 다룬다.

    sku_catalog.sku_id (PK)
        └─ sku_image.sku_id (FK, ON DELETE CASCADE)


data/images/incomming의 이미지는 파일명에 sku_id가 아니라 sku_code를
쓰므로, 이미지 적재 시에는 sku_code -> sku_id 매핑을 먼저 조회해서 쓴다
(fetch_sku_ids_by_code).
"""

from __future__ import annotations

import datetime
from typing import Any

import psycopg
from pgvector.psycopg import register_vector
from psycopg.types.json import Json

from app.core import config


def connect(settings: config.DatabaseSettings) -> psycopg.Connection:
    """PostgreSQL에 연결하고 vector 타입 어댑터를 등록한다.

    Args:
        settings: PostgreSQL 연결 정보입니다.

    Returns:
        vector 컬럼에 Python list를 바로 넘길 수 있는 연결입니다.
    """
    conn = psycopg.connect(
        host=settings.host,
        port=settings.port,
        dbname=settings.name,
        user=settings.username,
        password=settings.password,
        autocommit=False,
    )
    register_vector(conn)
    return conn


def upsert_sku_metadata(conn: psycopg.Connection, sku: dict[str, Any]) -> bool:
    """SKU 1건의 상품 마스터 정보를 적재한다. 이미 있으면 건드리지 않는다.

    sku_id가 이미 sku_catalog에 있으면 아무것도 덮어쓰지 않고 그대로 둔다
    (임베딩 컬럼뿐 아니라 상품명·속성 등 기존 값도 보존한다). 새 sku_id일
    때만 INSERT한다.

    Args:
        conn: DB 연결입니다.
        sku: sku.json의 항목 1건입니다.

    Returns:
        새로 삽입됐으면 True, 이미 있어서 건너뛰었으면 False입니다.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sku_catalog (
                sku_id, sku_code, product_name, category, sub_category,
                brand, price, key_features, attributes
            )
            VALUES (
                %(sku_id)s, %(sku_code)s, %(product_name)s, %(category)s,
                %(sub_category)s, %(brand)s, %(price)s, %(key_features)s,
                %(attributes)s
            )
            ON CONFLICT (sku_id) DO NOTHING
            """,
            {
                "sku_id": sku["sku_id"],
                "sku_code": sku["sku_code"],
                "product_name": sku["product_name"],
                "category": sku["category"],
                "sub_category": sku.get("sub_category"),
                "brand": sku.get("brand"),
                "price": sku.get("price"),
                "key_features": Json(sku.get("key_features") or []),
                "attributes": Json(sku.get("attributes") or {}),
            },
        )
        return cur.rowcount > 0


def sync_sku_sequence(conn: psycopg.Connection) -> None:
    """sku_catalog의 시퀀스를 현재 MAX(sku_id)로 맞춘다.

    sku_id를 명시적으로 넣은 뒤 반드시 호출해야, 다음에 애플리케이션이
    새 SKU를 넣을 때 sku_id가 겹치지 않는다.

    Args:
        conn: DB 연결입니다.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT setval("
            "  pg_get_serial_sequence('sku_catalog', 'sku_id'),"
            "  COALESCE((SELECT MAX(sku_id) FROM sku_catalog), 1)"
            ")"
        )


def fetch_text_embedded_sku_ids(conn: psycopg.Connection) -> set[int]:
    """이미 text_embedding이 채워진 sku_id 집합을 돌려준다."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT sku_id FROM sku_catalog WHERE text_embedding IS NOT NULL"
        )
        return {row[0] for row in cur.fetchall()}


def update_text_embedding(
    conn: psycopg.Connection, sku_id: int, embedding: list[float]
) -> None:
    """SKU 1건의 텍스트 임베딩을 저장한다.

    Args:
        conn: DB 연결입니다.
        sku_id: 대상 SKU입니다.
        embedding: Gemini 텍스트 임베딩 벡터입니다.
    """
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE sku_catalog SET text_embedding = %s WHERE sku_id = %s",
            (embedding, sku_id),
        )


def fetch_sku_ids_by_code(conn: psycopg.Connection) -> dict[str, int]:
    """sku_code -> sku_id 매핑을 돌려준다.

    data/images/incomming의 파일명은 sku_id가 아니라 sku_code를 쓰므로,
    이미지를 적재하기 전에 이 매핑으로 sku_id를 찾는다.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT sku_code, sku_id FROM sku_catalog")
        return {row[0]: row[1] for row in cur.fetchall()}


def fetch_embedded_image_urls(conn: psycopg.Connection) -> set[str]:
    """임베딩이 이미 채워진 image_url 집합을 돌려준다.

    이미지 1건 = image_url 1개 기준으로 완료 여부를 추적한다. SKU당
    이미지가 여러 장(MAIN + ANGLE 등)일 수 있어 sku_id 단위로는 더 이상
    완료 여부를 판단할 수 없다.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT image_url FROM sku_image WHERE embedding IS NOT NULL"
        )
        return {row[0] for row in cur.fetchall()}


def upsert_sku_image(
    conn: psycopg.Connection,
    sku_id: int,
    image_url: str,
    image_type: str,
    embedding: list[float],
    overwrite: bool = False,
) -> bool:
    """SKU 이미지 1건을 적재하되, 이미 임베딩이 있으면 건드리지 않는다.

    같은 image_url의 행이 없으면 새로 만든다. 있는데 embedding이 아직
    비어 있으면 채워 넣는다. 이미 embedding이 있으면 overwrite=True가
    아닌 한 그대로 두고 건너뛴다. image_url을 키로 써서 SKU당 이미지가
    여러 장이어도(MAIN + ANGLE, sequence 여러 장) 안전하게 재실행할 수
    있다.

    Args:
        conn: DB 연결입니다.
        sku_id: sku_catalog.sku_id입니다.
        image_url: 이미지 경로(프로젝트 루트 기준 상대 경로)입니다.
        image_type: 'MAIN' 또는 'ANGLE'입니다.
        embedding: Gemini 이미지 임베딩 벡터입니다.
        overwrite: True면 이미 임베딩이 있어도 덮어씁니다(--force-images용).

    Returns:
        실제로 삽입·갱신했으면 True, 이미 임베딩이 있어서 건너뛰었으면 False.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT sku_image_id, embedding FROM sku_image "
            "WHERE sku_id = %s AND image_url = %s",
            (sku_id, image_url),
        )
        existing = cur.fetchone()

        if existing and existing[1] is not None and not overwrite:
            return False

        if existing:
            cur.execute(
                "UPDATE sku_image "
                "SET image_type = %s, embedding = %s, indexed_at = %s "
                "WHERE sku_image_id = %s",
                (image_type, embedding, now, existing[0]),
            )
        else:
            cur.execute(
                "INSERT INTO sku_image "
                "(sku_id, image_url, image_type, embedding, indexed_at) "
                "VALUES (%s, %s, %s, %s, %s)",
                (sku_id, image_url, image_type, embedding, now),
            )
        return True
