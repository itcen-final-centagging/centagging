"""애플리케이션 사용자 ORM 모델입니다."""

import datetime

import sqlalchemy
from sqlalchemy import orm

from app.models.sku import Base


# SQLAlchemy 매핑 전용 클래스입니다.
class AppUser(Base):  # pylint: disable=too-few-public-methods
    """로그인과 태깅 작업자를 나타내는 애플리케이션 사용자입니다."""

    __tablename__ = "app_user"

    user_id: orm.Mapped[int] = orm.mapped_column(
        sqlalchemy.Integer, primary_key=True, autoincrement=True
    )
    login_id: orm.Mapped[str] = orm.mapped_column(
        sqlalchemy.String(50), nullable=False
    )
    user_name: orm.Mapped[str] = orm.mapped_column(
        sqlalchemy.String(100), nullable=False
    )
    password_hash: orm.Mapped[str] = orm.mapped_column(
        sqlalchemy.String(255), nullable=False
    )
    is_active: orm.Mapped[bool] = orm.mapped_column(
        sqlalchemy.Boolean, nullable=False
    )
    created_at: orm.Mapped[datetime.datetime] = orm.mapped_column(
        sqlalchemy.DateTime, nullable=False
    )
