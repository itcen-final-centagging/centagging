"""제품 이미지 등록 추천 작업 상태·결과 조회 응답 스키마입니다."""

import datetime
import typing
import uuid

import pydantic

from app.schemas.tagging import SkuCandidate

ProductImageSubmissionJobStatus = typing.Literal[
    "PENDING", "RUNNING", "SUCCEEDED", "FAILED"
]


class ProductImageSubmissionJobResultPayload(pydantic.BaseModel):
    """추천 파이프라인이 성공했을 때 채우는 결과값입니다."""

    proposed_category: str | None = None
    proposed_sub_category: str | None = None
    proposed_attributes: dict[str, typing.Any] = pydantic.Field(
        default_factory=dict
    )
    sku_candidates: list[SkuCandidate] = pydantic.Field(default_factory=list)


class ProductImageSubmissionJobResponse(pydantic.BaseModel):
    """프론트엔드 폴링에 필요한 제품 이미지 등록 추천 작업의 공개 상태입니다."""

    model_config = pydantic.ConfigDict(from_attributes=True)

    job_id: uuid.UUID
    submission_id: int
    status: ProductImageSubmissionJobStatus
    attempt_count: int
    max_attempts: int
    result_payload: ProductImageSubmissionJobResultPayload | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime.datetime
    started_at: datetime.datetime | None = None
    finished_at: datetime.datetime | None = None
    updated_at: datetime.datetime
