import datetime

import sqlalchemy.orm
from sqlalchemy import orm

from app.models.sku import Base

class AppUser(Base):
    __tablename__ = "app_user"

    user_id: orm.Mapped[int] = sqlalchemy.orm.mapped_column(
        sqlalchemy.Integer,
        primary_key=True,
        autoincrement=True
    )
    login_id: orm.Mapped[str] = sqlalchemy.orm.mapped_column(
        sqlalchemy.String(50),
        nullable=False
    )
    user_name: orm.Mapped[str] = sqlalchemy.orm.mapped_column(
        sqlalchemy.String(100),
        nullable=False
    )
    password_hash: orm.Mapped[str] = sqlalchemy.orm.mapped_column(
        sqlalchemy.String(255),
        nullable=False
    )
    is_active: orm.Mapped[bool] = sqlalchemy.orm.mapped_column(
        sqlalchemy.Boolean,
        nullable=False
    )
    created_at: orm.Mapped[datetime.datetime] = sqlalchemy.orm.mapped_column(
        sqlalchemy.DateTime,
        nullable=False
    )
