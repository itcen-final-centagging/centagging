"""제품 이미지 등록 추천 작업 큐 ORM 모델입니다."""

import datetime
import enum
import uuid

import sqlalchemy
from sqlalchemy import orm
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext import mutable

from app.models.sku import Base


class ProductImageSubmissionJobStatus(str, enum.Enum):
    """제품 이미지 등록 추천 작업의 처리 상태입니다."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class ProductImageSubmissionJob(Base):  # pylint: disable=too-few-public-methods
    """제품 이미지 등록 요청 1건의 AI 추천 파이프라인 작업입니다."""

    __tablename__ = "product_image_submission_job"
    __table_args__ = (
        sqlalchemy.CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED')",
            name="ck_product_image_submission_job_status",
        ),
        sqlalchemy.CheckConstraint(
            "attempt_count >= 0 AND max_attempts > 0 "
            "AND attempt_count <= max_attempts",
            name="ck_product_image_submission_job_attempts",
        ),
        sqlalchemy.Index(
            "idx_product_image_submission_job_pending_created",
            "status",
            "created_at",
            postgresql_where=sqlalchemy.text("status = 'PENDING'"),
        ),
        sqlalchemy.Index(
            "idx_product_image_submission_job_submission_created",
            "submission_id",
            sqlalchemy.desc("created_at"),
        ),
        sqlalchemy.Index(
            "uq_product_image_submission_job_active",
            "submission_id",
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
    submission_id: orm.Mapped[int] = orm.mapped_column(
        sqlalchemy.BigInteger,
        sqlalchemy.ForeignKey(
            "product_image_submission.submission_id", ondelete="CASCADE"
        ),
        nullable=False,
    )
    status: orm.Mapped[str] = orm.mapped_column(
        sqlalchemy.String(20),
        nullable=False,
        default=ProductImageSubmissionJobStatus.PENDING.value,
        server_default=ProductImageSubmissionJobStatus.PENDING.value,
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
