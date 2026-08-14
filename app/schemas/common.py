"""모든 JSON API가 공유하는 성공·오류 응답 모델을 제공합니다."""

import typing

import pydantic

from app.core.error_codes import ErrorCode
from app.core.request_context import get_or_create_request_id

ResponseData = typing.TypeVar("ResponseData")


class ResponseMeta(pydantic.BaseModel):
    """응답 추적에 필요한 공통 메타데이터입니다."""

    request_id: str = pydantic.Field(
        description="서버 로그 추적에 사용하는 요청 식별자입니다."
    )


class SuccessResponse(pydantic.BaseModel, typing.Generic[ResponseData]):
    """성공한 JSON API의 공통 응답입니다."""

    status: typing.Literal["success"] = "success"
    data: ResponseData
    meta: ResponseMeta


class ErrorDetail(pydantic.BaseModel):
    """입력값 또는 처리 실패의 필드별 상세 정보입니다."""

    field: str = pydantic.Field(description="오류가 발생한 요청 필드명입니다.")
    reason: str = pydantic.Field(
        description="클라이언트 처리를 위한 오류 원인 코드입니다."
    )
    message: str = pydantic.Field(
        description="사용자에게 표시할 수 있는 상세 안내 메시지입니다."
    )


class ErrorBody(pydantic.BaseModel):
    """실패한 JSON API의 오류 본문입니다."""

    code: ErrorCode
    message: str
    details: list[ErrorDetail] = pydantic.Field(default_factory=list)


class ErrorResponse(pydantic.BaseModel):
    """실패한 JSON API의 공통 응답입니다."""

    status: typing.Literal["error"] = "error"
    error: ErrorBody
    meta: ResponseMeta


def success_response(
    data: ResponseData, *, request_id: str | None = None
) -> SuccessResponse[ResponseData]:
    """성공 데이터를 공통 성공 응답 구조로 만듭니다."""
    return SuccessResponse(
        data=data,
        meta=ResponseMeta(request_id=request_id or get_or_create_request_id()),
    )


def error_response(
    code: ErrorCode,
    *,
    message: str | None = None,
    details: list[ErrorDetail] | None = None,
    request_id: str | None = None,
) -> ErrorResponse:
    """오류 정보를 공통 오류 응답 구조로 만듭니다."""
    return ErrorResponse(
        error=ErrorBody(
            code=code,
            message=message or code.default_message,
            details=details or [],
        ),
        meta=ResponseMeta(request_id=request_id or get_or_create_request_id()),
    )
