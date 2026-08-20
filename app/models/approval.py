"""태깅 확정 결과 승인 요청 ORM 모델입니다."""

import datetime
import typing

import sqlalchemy
from sqlalchemy import orm

from app.models.sku import Base


# SQLAlchemy 매핑 전용 클래스입니다.
class Approval(Base):  # pylint: disable=too-few-public-methods
    """객체-SKU 매칭(tagging_result) 단위 승인 요청입니다 (``schema.sql``의 ``approval``)."""

    __tablename__ = "approval"

    request_id: orm.Mapped[int] = orm.mapped_column(
        sqlalchemy.BigInteger, primary_key=True
    )
    tagging_result_id: orm.Mapped[int] = orm.mapped_column(
        sqlalchemy.BigInteger,
        sqlalchemy.ForeignKey("tagging_result.result_id", ondelete="CASCADE"),
        nullable=False,
    )
    scene_image_id: orm.Mapped[int] = orm.mapped_column(
        sqlalchemy.BigInteger,
        sqlalchemy.ForeignKey("scene_image.scene_image_id", ondelete="CASCADE"),
        nullable=False,
    )
    object_index: orm.Mapped[int] = orm.mapped_column(
        sqlalchemy.SmallInteger, nullable=False
    )
    status: orm.Mapped[typing.Literal["PENDING", "ACTIVE", "REJECTED"]] = (
        orm.mapped_column(
            sqlalchemy.String(20),
            nullable=False,
            server_default=sqlalchemy.text("'PENDING'"),
        )
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
