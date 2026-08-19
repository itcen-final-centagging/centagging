"""AI 분석 작업 큐 ORM 모델입니다."""

import datetime
import enum
import uuid

import sqlalchemy
from sqlalchemy import orm
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext import mutable

from app.models.sku import Base


class AiJobType(str, enum.Enum):
    """Worker가 처리하는 AI 작업 유형입니다."""

    DETECT_SCENE = "DETECT_SCENE"
    RECOMMEND_SKU = "RECOMMEND_SKU"


class AiJobStatus(str, enum.Enum):
    """AI 작업의 처리 상태입니다."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class AiJob(Base):  # pylint: disable=too-few-public-methods
    """Cloud SQL을 영속 작업 큐로 사용하는 AI 분석 작업입니다."""

    __tablename__ = "ai_job"
    __table_args__ = (
        sqlalchemy.CheckConstraint(
            "job_type IN ('DETECT_SCENE', 'RECOMMEND_SKU')",
            name="ck_ai_job_type",
        ),
        sqlalchemy.CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED')",
            name="ck_ai_job_status",
        ),
        sqlalchemy.CheckConstraint(
            "attempt_count >= 0 AND max_attempts > 0 "
            "AND attempt_count <= max_attempts",
            name="ck_ai_job_attempts",
        ),
        sqlalchemy.Index(
            "idx_ai_job_pending_created",
            "status",
            "created_at",
            postgresql_where=sqlalchemy.text("status = 'PENDING'"),
        ),
        sqlalchemy.Index(
            "idx_ai_job_scene_created",
            "scene_image_id",
            sqlalchemy.desc("created_at"),
        ),
        sqlalchemy.Index(
            "uq_ai_job_active_scene_type",
            "scene_image_id",
            "job_type",
            unique=True,
            postgresql_where=sqlalchemy.text(
                "status IN ('PENDING', 'RUNNING')"
            ),
        ),
    )

    job_id: orm.Mapped[uuid.UUID] = orm.mapped_column(
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    scene_image_id: orm.Mapped[int] = orm.mapped_column(
        sqlalchemy.BigInteger,
        sqlalchemy.ForeignKey("scene_image.scene_image_id", ondelete="CASCADE"),
        nullable=False,
    )
    job_type: orm.Mapped[str] = orm.mapped_column(
        sqlalchemy.String(30), nullable=False
    )
    status: orm.Mapped[str] = orm.mapped_column(
        sqlalchemy.String(20),
        nullable=False,
        default=AiJobStatus.PENDING.value,
        server_default=AiJobStatus.PENDING.value,
    )
    input_payload: orm.Mapped[dict[str, object]] = orm.mapped_column(
        mutable.MutableDict.as_mutable(postgresql.JSONB),
        nullable=False,
        default=dict,
        server_default=sqlalchemy.text("'{}'::jsonb"),
    )
    result_payload: orm.Mapped[dict[str, object] | None] = orm.mapped_column(
        mutable.MutableDict.as_mutable(postgresql.JSONB)
    )
    error_code: orm.Mapped[str | None] = orm.mapped_column(
        sqlalchemy.String(50)
    )
    error_message: orm.Mapped[str | None] = orm.mapped_column(sqlalchemy.Text)
    attempt_count: orm.Mapped[int] = orm.mapped_column(
        sqlalchemy.SmallInteger,
        nullable=False,
        default=0,
        server_default="0",
    )
    max_attempts: orm.Mapped[int] = orm.mapped_column(
        sqlalchemy.SmallInteger,
        nullable=False,
        default=3,
        server_default="3",
    )
    worker_id: orm.Mapped[str | None] = orm.mapped_column(
        sqlalchemy.String(100)
    )
    locked_at: orm.Mapped[datetime.datetime | None] = orm.mapped_column(
        sqlalchemy.TIMESTAMP(timezone=True)
    )
    created_at: orm.Mapped[datetime.datetime] = orm.mapped_column(
        sqlalchemy.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sqlalchemy.text("now()"),
    )
    started_at: orm.Mapped[datetime.datetime | None] = orm.mapped_column(
        sqlalchemy.TIMESTAMP(timezone=True)
    )
    finished_at: orm.Mapped[datetime.datetime | None] = orm.mapped_column(
        sqlalchemy.TIMESTAMP(timezone=True)
    )
    updated_at: orm.Mapped[datetime.datetime] = orm.mapped_column(
        sqlalchemy.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sqlalchemy.text("now()"),
        onupdate=sqlalchemy.text("now()"),
    )
