"""AI 분석 작업 상태·결과 조회 응답 스키마입니다."""

import datetime
import typing
import uuid

import pydantic

AiJobType = typing.Literal["DETECT_SCENE", "RECOMMEND_SKU"]
AiJobStatus = typing.Literal["PENDING", "RUNNING", "SUCCEEDED", "FAILED"]


class AiJobResponse(pydantic.BaseModel):
    """프론트엔드 폴링에 필요한 AI 작업의 공개 상태입니다."""

    model_config = pydantic.ConfigDict(from_attributes=True)

    job_id: uuid.UUID
    scene_image_id: int
    job_type: AiJobType
    status: AiJobStatus
    attempt_count: int
    max_attempts: int
    result_payload: dict[str, typing.Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime.datetime
    started_at: datetime.datetime | None = None
    finished_at: datetime.datetime | None = None
    updated_at: datetime.datetime
