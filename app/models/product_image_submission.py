"""관리자 제품 이미지 등록 요청 ORM 모델입니다."""

import datetime
import typing

import pgvector.sqlalchemy as pgvector_sa  # type: ignore[import-untyped]
import sqlalchemy
from sqlalchemy import orm
from sqlalchemy.dialects import postgresql

from app.models.sku import Base


class ProductImageSubmission(Base):  # pylint: disable=too-few-public-methods
    """제품 이미지 신규/기존 SKU 등록 승인 요청입니다.

    ``proposed_*``와 상태 전이별 필수값 조합은
    ``ck_product_image_submission_review``(schema.sql)가 DB 레벨에서
    강제한다.
    """

    __tablename__ = "product_image_submission"

    submission_id: orm.Mapped[int] = orm.mapped_column(
        sqlalchemy.BigInteger, primary_key=True
    )
    target_type: orm.Mapped[typing.Optional[str]] = orm.mapped_column(
        sqlalchemy.String(20)
    )
    target_sku_id: orm.Mapped[typing.Optional[int]] = orm.mapped_column(
        sqlalchemy.BigInteger,
        sqlalchemy.ForeignKey("sku_catalog.sku_id"),
    )
    proposed_sku_code: orm.Mapped[typing.Optional[str]] = orm.mapped_column(
        sqlalchemy.String(50)
    )
    proposed_product_name: orm.Mapped[typing.Optional[str]] = orm.mapped_column(
        sqlalchemy.String(200)
    )
    proposed_brand: orm.Mapped[typing.Optional[str]] = orm.mapped_column(
        sqlalchemy.String(100)
    )
    proposed_price: orm.Mapped[typing.Optional[int]] = orm.mapped_column(
        sqlalchemy.Integer
    )
    proposed_category: orm.Mapped[typing.Optional[str]] = orm.mapped_column(
        sqlalchemy.String(50)
    )
    proposed_sub_category: orm.Mapped[typing.Optional[str]] = orm.mapped_column(
        sqlalchemy.String(50)
    )
    proposed_attributes: orm.Mapped[dict[str, typing.Any]] = orm.mapped_column(
        postgresql.JSONB, nullable=False, default=dict
    )
    image_url: orm.Mapped[str] = orm.mapped_column(
        sqlalchemy.Text, nullable=False
    )
    image_type: orm.Mapped[str] = orm.mapped_column(
        sqlalchemy.String(20), nullable=False, default="MAIN"
    )
    status: orm.Mapped[str] = orm.mapped_column(
        sqlalchemy.String(20), nullable=False, default="DRAFT"
    )
    requested_by: orm.Mapped[int] = orm.mapped_column(
        sqlalchemy.BigInteger,
        sqlalchemy.ForeignKey("app_user.user_id"),
        nullable=False,
    )
    requested_at: orm.Mapped[datetime.datetime] = orm.mapped_column(
        sqlalchemy.TIMESTAMP(timezone=True),
        server_default=sqlalchemy.text("now()"),
    )
    submitted_at: orm.Mapped[typing.Optional[datetime.datetime]] = (
        orm.mapped_column(sqlalchemy.TIMESTAMP(timezone=True))
    )
    reviewed_by: orm.Mapped[typing.Optional[int]] = orm.mapped_column(
        sqlalchemy.BigInteger,
        sqlalchemy.ForeignKey("app_user.user_id"),
    )
    reviewed_at: orm.Mapped[typing.Optional[datetime.datetime]] = (
        orm.mapped_column(sqlalchemy.TIMESTAMP(timezone=True))
    )
    reject_reason: orm.Mapped[typing.Optional[str]] = orm.mapped_column(
        sqlalchemy.String(255)
    )
    final_sku_id: orm.Mapped[typing.Optional[int]] = orm.mapped_column(
        sqlalchemy.BigInteger,
        sqlalchemy.ForeignKey("sku_catalog.sku_id"),
    )
    final_sku_image_id: orm.Mapped[typing.Optional[int]] = orm.mapped_column(
        sqlalchemy.BigInteger,
        sqlalchemy.ForeignKey("sku_image.sku_image_id"),
    )
    # 업로드 시점(Worker)에 계산한 융합 임베딩 캐시입니다. 승인 시
    # sku_image의 대응 컬럼으로 그대로 복사되며 재계산하지 않습니다.
    draft_embedding: orm.Mapped[typing.Optional[list[float]]] = (
        orm.mapped_column(pgvector_sa.HALFVEC(3072))
    )
    draft_embedding_pipeline_version: orm.Mapped[typing.Optional[str]] = (
        orm.mapped_column(sqlalchemy.String(50))
    )
    draft_embedding_image_sha256: orm.Mapped[typing.Optional[str]] = (
        orm.mapped_column(sqlalchemy.Text)
    )
