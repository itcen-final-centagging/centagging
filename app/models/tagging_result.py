"""최종 객체-SKU 매핑과 검수 이력 ORM 모델입니다."""

import datetime
import decimal
import typing

import sqlalchemy
from sqlalchemy import orm
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext import mutable

from app.models.sku import Base


class TaggingResult(Base):  # pylint: disable=too-few-public-methods
    """최종 객체-SKU 매핑 + 검수 이력입니다 (``schema.sql``의 ``tagging_result``)."""

    __tablename__ = "tagging_result"
    __table_args__ = (
        sqlalchemy.UniqueConstraint(
            "scene_image_id", "object_idx", name="uq_result_scene_object"
        ),
    )

    result_id: orm.Mapped[int] = orm.mapped_column(
        sqlalchemy.BigInteger, primary_key=True
    )
    scene_image_id: orm.Mapped[int] = orm.mapped_column(
        sqlalchemy.BigInteger,
        sqlalchemy.ForeignKey("scene_image.scene_image_id"),
        nullable=False,
    )
    object_idx: orm.Mapped[int] = orm.mapped_column(
        sqlalchemy.SmallInteger, nullable=False
    )
    sku_id: orm.Mapped[int] = orm.mapped_column(
        sqlalchemy.BigInteger,
        sqlalchemy.ForeignKey("sku_catalog.sku_id"),
        nullable=False,
    )
    sku_image_id: orm.Mapped[typing.Optional[int]] = orm.mapped_column(
        sqlalchemy.BigInteger,
        sqlalchemy.ForeignKey("sku_image.sku_image_id"),
    )
    match_source: orm.Mapped[typing.Literal["RECOMMEND", "SEARCH"]] = (
        orm.mapped_column(sqlalchemy.String(20), nullable=False)
    )
    match_rank: orm.Mapped[typing.Optional[int]] = orm.mapped_column(
        sqlalchemy.SmallInteger
    )
    similarity_score: orm.Mapped[typing.Optional[decimal.Decimal]] = (
        orm.mapped_column(sqlalchemy.Numeric(6, 4))
    )
    similarity_grade: orm.Mapped[typing.Optional[str]] = orm.mapped_column(
        sqlalchemy.CHAR(1)
    )
    xai_result: orm.Mapped[typing.Optional[dict[str, typing.Any]]] = (
        orm.mapped_column(
            mutable.MutableDict.as_mutable(postgresql.JSONB(none_as_null=True))
        )
    )
    vlm_mood: orm.Mapped[typing.Optional[dict[str, typing.Any]]] = (
        orm.mapped_column(
            mutable.MutableDict.as_mutable(postgresql.JSONB(none_as_null=True))
        )
    )
    created_by: orm.Mapped[int] = orm.mapped_column(
        sqlalchemy.BigInteger,
        sqlalchemy.ForeignKey("app_user.user_id"),
        nullable=False,
    )
    created_at: orm.Mapped[datetime.datetime] = orm.mapped_column(
        sqlalchemy.TIMESTAMP(timezone=True),
        server_default=sqlalchemy.text("now()"),
    )
