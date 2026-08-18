"""SKU 카탈로그·이미지 ORM 모델입니다.

SQLAlchemy models for the SKU catalog and its images. 테이블은
``docker/db/init/schema.sql``에 이미 정의되어 있으며(연출컷 매칭
서비스팀 소유), 여기서는 그 스키마에 매핑되는 모델만 선언합니다.
"""

import datetime
import typing

import pgvector.sqlalchemy as pgvector_sa  # type: ignore[import-untyped]
import sqlalchemy
from sqlalchemy import orm
from sqlalchemy.dialects import postgresql


class Base(orm.DeclarativeBase):  # pylint: disable=too-few-public-methods
    """모든 ORM 모델의 공통 베이스입니다. / Common base for all ORM models."""


class SkuCatalog(Base):  # pylint: disable=too-few-public-methods
    """상품 마스터 + 속성입니다 (``schema.sql``의 ``sku_catalog``)."""

    __tablename__ = "sku_catalog"

    sku_id: orm.Mapped[int] = orm.mapped_column(
        sqlalchemy.BigInteger, primary_key=True
    )
    sku_code: orm.Mapped[str] = orm.mapped_column(
        sqlalchemy.String(50), unique=True, nullable=False
    )
    product_name: orm.Mapped[str] = orm.mapped_column(
        sqlalchemy.String(200), nullable=False
    )
    brand: orm.Mapped[typing.Optional[str]] = orm.mapped_column(
        sqlalchemy.String(100)
    )
    price: orm.Mapped[typing.Optional[int]] = orm.mapped_column(
        sqlalchemy.Integer
    )
    space: orm.Mapped[typing.Optional[str]] = orm.mapped_column(
        sqlalchemy.String(50)
    )
    category: orm.Mapped[typing.Optional[str]] = orm.mapped_column(
        sqlalchemy.String(50)
    )
    sub_category: orm.Mapped[typing.Optional[str]] = orm.mapped_column(
        sqlalchemy.String(50)
    )
    attributes: orm.Mapped[dict[str, typing.Any]] = orm.mapped_column(
        postgresql.JSONB, nullable=False, default=dict
    )
    # 상품 메타데이터(상품명·카테고리·속성 등) 텍스트 임베딩입니다.
    text_embedding: orm.Mapped[typing.Optional[list[float]]] = orm.mapped_column(
        pgvector_sa.Vector(3072), deferred=True
    )
    created_at: orm.Mapped[datetime.datetime] = orm.mapped_column(
        sqlalchemy.TIMESTAMP(timezone=True),
        server_default=sqlalchemy.text("now()"),
    )


class SkuImage(Base):  # pylint: disable=too-few-public-methods
    """SKU 이미지입니다 (``schema.sql``의 ``sku_image``).

    임베딩 색인은 연출컷 매칭 서비스팀의 별도 배치가 채우므로 이
    모델은 ``embedding``/``indexed_at`` 컬럼을 다루지 않습니다.
    """

    __tablename__ = "sku_image"

    sku_image_id: orm.Mapped[int] = orm.mapped_column(
        sqlalchemy.BigInteger, primary_key=True
    )
    sku_id: orm.Mapped[int] = orm.mapped_column(
        sqlalchemy.BigInteger,
        sqlalchemy.ForeignKey("sku_catalog.sku_id", ondelete="CASCADE"),
        nullable=False,
    )
    image_url: orm.Mapped[str] = orm.mapped_column(
        sqlalchemy.Text, nullable=False
    )
    image_type: orm.Mapped[str] = orm.mapped_column(
        sqlalchemy.String(20), nullable=False, default="MAIN"
    )
    embedding: orm.Mapped[typing.Optional[list[float]]] = orm.mapped_column(
        pgvector_sa.Vector(3072), deferred=True
    )
    indexed_at: orm.Mapped[typing.Optional[datetime.datetime]] = (
        orm.mapped_column(sqlalchemy.TIMESTAMP(timezone=True))
    )
    created_at: orm.Mapped[datetime.datetime] = orm.mapped_column(
        sqlalchemy.TIMESTAMP(timezone=True),
        server_default=sqlalchemy.text("now()"),
    )
