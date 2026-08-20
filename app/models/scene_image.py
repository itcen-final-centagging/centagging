"""연출 이미지 ORM 모델입니다."""

import datetime
import typing

import sqlalchemy
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext import mutable
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.app_user import AppUser
from app.models.sku import Base

# SQLAlchemy Mapped 제네릭은 Pylint가 런타임 타입으로 해석하지 못합니다.
# pylint: disable=unsubscriptable-object


# SQLAlchemy 매핑 전용 클래스입니다.
class SceneImage(Base):  # pylint: disable=too-few-public-methods
    """업로드된 연출 이미지입니다 (``schema.sql``의 ``scene_image``)."""

    __tablename__ = "scene_image"

    scene_image_id: Mapped[int] = mapped_column(
        sqlalchemy.BigInteger, primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        sqlalchemy.BigInteger,
        sqlalchemy.ForeignKey("app_user.user_id"),
        nullable=False,
    )
    user: Mapped[AppUser] = relationship()
    image_url: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    origin_name: Mapped[str] = mapped_column(
        sqlalchemy.String(255), nullable=False
    )
    mime_type: Mapped[str] = mapped_column(
        sqlalchemy.String(20), nullable=False
    )
    file_size: Mapped[int] = mapped_column(sqlalchemy.Integer, nullable=False)
    width_px: Mapped[int] = mapped_column(sqlalchemy.Integer, nullable=False)
    height_px: Mapped[int] = mapped_column(sqlalchemy.Integer, nullable=False)
    analysis_status: Mapped[str] = mapped_column(
        sqlalchemy.String(20), nullable=False, default="pending"
    )
    analysis_error: Mapped[typing.Optional[str]] = mapped_column(
        sqlalchemy.Text
    )
    object_metadata: Mapped[list[dict[str, typing.Any]]] = mapped_column(
        mutable.MutableList.as_mutable(postgresql.JSONB),
        nullable=False,
        default=list,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        sqlalchemy.TIMESTAMP(timezone=True),
        server_default=sqlalchemy.text("now()"),
    )
