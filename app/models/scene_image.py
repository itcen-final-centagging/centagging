"""연출 이미지 ORM 모델입니다."""

import datetime
import typing

import sqlalchemy
from sqlalchemy import orm
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext import mutable

from app.models.app_user import AppUser
from app.models.sku import Base


# SQLAlchemy 매핑 전용 클래스입니다.
class SceneImage(Base):  # pylint: disable=too-few-public-methods
    """업로드된 연출 이미지입니다 (``schema.sql``의 ``scene_image``)."""

    __tablename__ = "scene_image"

    scene_image_id: orm.Mapped[int] = orm.mapped_column(
        sqlalchemy.BigInteger, primary_key=True
    )
    user_id: orm.Mapped[int] = orm.mapped_column(
        sqlalchemy.BigInteger,
        sqlalchemy.ForeignKey("app_user.user_id"),
        nullable=False,
    )
    user: orm.Mapped[AppUser] = orm.relationship()
    image_url: orm.Mapped[str] = orm.mapped_column(
        sqlalchemy.Text, nullable=False
    )
    origin_name: orm.Mapped[str] = orm.mapped_column(
        sqlalchemy.String(255), nullable=False
    )
    mime_type: orm.Mapped[str] = orm.mapped_column(
        sqlalchemy.String(20), nullable=False
    )
    file_size: orm.Mapped[int] = orm.mapped_column(
        sqlalchemy.Integer, nullable=False
    )
    width_px: orm.Mapped[int] = orm.mapped_column(
        sqlalchemy.Integer, nullable=False
    )
    height_px: orm.Mapped[int] = orm.mapped_column(
        sqlalchemy.Integer, nullable=False
    )
    analysis_status: orm.Mapped[str] = orm.mapped_column(
        sqlalchemy.String(20), nullable=False, default="pending"
    )
    analysis_error: orm.Mapped[typing.Optional[str]] = orm.mapped_column(
        sqlalchemy.Text
    )
    object_metadata: orm.Mapped[list[dict[str, typing.Any]]] = (
        orm.mapped_column(
            mutable.MutableList.as_mutable(postgresql.JSONB),
            nullable=False,
            default=list,
        )
    )
    created_at: orm.Mapped[datetime.datetime] = orm.mapped_column(
        sqlalchemy.TIMESTAMP(timezone=True),
        server_default=sqlalchemy.text("now()"),
    )
