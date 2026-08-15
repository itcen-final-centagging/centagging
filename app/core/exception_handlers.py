"""FastAPI 예외를 공통 API 오류 응답으로 변환합니다."""

import collections.abc
import logging
import typing

import fastapi
import fastapi.exceptions
import starlette.exceptions
import starlette.requests
import starlette.responses

from app.core.error_codes import ErrorCode
from app.core.request_context import get_or_create_request_id
from app.schemas.common import ErrorDetail, error_response

_logger = logging.getLogger(__name__)

_HTTP_ERROR_CODES: dict[int, ErrorCode] = {
    400: ErrorCode.BAD_REQUEST,
    401: ErrorCode.AUTH_SESSION_INVALID,
    403: ErrorCode.AUTH_FORBIDDEN,
    404: ErrorCode.RESOURCE_NOT_FOUND,
    409: ErrorCode.RESOURCE_CONFLICT,
    422: ErrorCode.VALIDATION_ERROR,
    502: ErrorCode.UPSTREAM_ERROR,
    503: ErrorCode.SERVICE_UNAVAILABLE,
}

_VALIDATION_REASONS: dict[str, str] = {
    "missing": "required",
    "string_too_short": "min_length",
    "too_short": "min_length",
    "string_too_long": "max_length",
    "too_long": "max_length",
    "string_pattern_mismatch": "invalid_format",
    "json_invalid": "invalid_format",
}

_VALIDATION_MESSAGES: dict[str, str] = {
    "required": "필수 값입니다.",
    "min_length": "입력값이 너무 짧습니다.",
    "max_length": "입력값이 너무 깁니다.",
    "invalid_format": "입력 형식이 올바르지 않습니다.",
    "invalid_type": "입력값의 형식이 올바르지 않습니다.",
    "invalid_value": "입력값을 확인해 주세요.",
}


def _get_error_code(status_code: int) -> ErrorCode:
    """HTTP 상태 코드에 대응하는 공통 오류 코드를 반환합니다."""
    if status_code >= 500:
        return ErrorCode.INTERNAL_SERVER_ERROR
    return _HTTP_ERROR_CODES.get(status_code, ErrorCode.BAD_REQUEST)


def _get_http_exception_error(
    exception: starlette.exceptions.HTTPException,
) -> tuple[ErrorCode, str]:
    """HTTPException의 상태와 detail에서 오류 코드와 메시지를 추출합니다."""
    error_code = _get_error_code(exception.status_code)
    detail = exception.detail
    if not isinstance(detail, dict):
        return error_code, str(detail)

    detail_code = detail.get("code")
    if isinstance(detail_code, str):
        try:
            error_code = ErrorCode(detail_code)
        except ValueError:
            pass

    detail_message = detail.get("message")
    if isinstance(detail_message, str):
        return error_code, detail_message
    return error_code, error_code.default_message


def _get_validation_reason(error_type: str) -> str:
    """Pydantic 오류 유형을 프런트용 오류 원인 코드로 변환합니다."""
    if error_type in _VALIDATION_REASONS:
        return _VALIDATION_REASONS[error_type]
    if error_type.endswith("_type") or error_type.endswith("_parsing"):
        return "invalid_type"
    return "invalid_value"


def _get_validation_field(location: tuple[str | int, ...]) -> str:
    """Pydantic 오류 위치를 점 표기 요청 필드명으로 변환합니다."""
    field_parts = [
        str(part)
        for part in location
        if part not in {"body", "query", "path", "header", "cookie"}
    ]
    return ".".join(field_parts) or "request"


def _to_validation_details(
    errors: collections.abc.Sequence[typing.Mapping[str, typing.Any]],
) -> list[ErrorDetail]:
    """Convert FastAPI 검증 오류 목록을 공통 오류 상세 목록으로 변환합니다."""
    details: list[ErrorDetail] = []
    for error in errors:
        location = error.get("loc", ())
        if not isinstance(location, tuple):
            location = tuple(location)
        error_type = str(error.get("type", "invalid_value"))
        reason = _get_validation_reason(error_type)
        details.append(
            ErrorDetail(
                field=_get_validation_field(location),
                reason=reason,
                message=_VALIDATION_MESSAGES[reason],
            )
        )
    return details


def _get_response_request_id(request: starlette.requests.Request) -> str:
    """미들웨어가 만든 요청 ID를 예외 처리 응답에도 사용합니다."""
    request_id = getattr(request.state, "request_id", None)
    if isinstance(request_id, str):
        return request_id
    return get_or_create_request_id()


def _json_error_response(
    status_code: int,
    code: ErrorCode,
    *,
    request_id: str,
    message: str | None = None,
    details: list[ErrorDetail] | None = None,
) -> starlette.responses.JSONResponse:
    """공통 오류 모델을 JSON HTTP 응답으로 변환합니다."""
    response = error_response(
        code,
        message=message,
        details=details,
        request_id=request_id,
    )
    return starlette.responses.JSONResponse(
        status_code=status_code,
        content=response.model_dump(mode="json"),
        headers={"X-Request-ID": response.meta.request_id},
    )


def register_exception_handlers(application: fastapi.FastAPI) -> None:
    """애플리케이션에 공통 오류 응답 전역 예외 처리기를 등록합니다."""

    @application.exception_handler(starlette.exceptions.HTTPException)
    async def handle_http_exception(
        request: starlette.requests.Request,
        exception: starlette.exceptions.HTTPException,
    ) -> starlette.responses.JSONResponse:
        """명시적으로 발생한 HTTP 오류를 공통 오류 응답으로 변환합니다."""
        code, message = _get_http_exception_error(exception)
        return _json_error_response(
            exception.status_code,
            code,
            request_id=_get_response_request_id(request),
            message=message,
        )

    @application.exception_handler(fastapi.exceptions.RequestValidationError)
    async def handle_request_validation_error(
        request: starlette.requests.Request,
        exception: fastapi.exceptions.RequestValidationError,
    ) -> starlette.responses.JSONResponse:
        """요청 검증 오류를 필드별 공통 오류 응답으로 변환합니다."""
        return _json_error_response(
            422,
            ErrorCode.VALIDATION_ERROR,
            request_id=_get_response_request_id(request),
            details=_to_validation_details(exception.errors()),
        )

    @application.exception_handler(Exception)
    async def handle_unexpected_exception(
        request: starlette.requests.Request,
        exception: Exception,
    ) -> starlette.responses.JSONResponse:
        """예상하지 못한 오류를 기록하고 안전한 공통 오류 응답을 반환합니다."""
        _logger.exception(
            "Unexpected server error. request_id=%s path=%s",
            _get_response_request_id(request),
            request.url.path,
        )
        return _json_error_response(
            500,
            ErrorCode.INTERNAL_SERVER_ERROR,
            request_id=_get_response_request_id(request),
        )
