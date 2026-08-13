"""공통 API 오류 코드와 기본 사용자 안내 메시지를 정의합니다."""

import enum


class ErrorCode(str, enum.Enum):
    """클라이언트가 오류 상황을 구분할 때 사용하는 고정 코드입니다."""

    BAD_REQUEST = "BAD_REQUEST"
    AUTH_CREDENTIALS_INVALID = "AUTH_CREDENTIALS_INVALID"
    AUTH_SESSION_INVALID = "AUTH_SESSION_INVALID"
    AUTH_FORBIDDEN = "AUTH_FORBIDDEN"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    RESOURCE_CONFLICT = "RESOURCE_CONFLICT"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"
    UPSTREAM_ERROR = "UPSTREAM_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"

    @property
    def default_message(self) -> str:
        """사용자에게 표시할 기본 한국어 안내 메시지를 반환합니다."""
        return _DEFAULT_ERROR_MESSAGES[self]


_DEFAULT_ERROR_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.BAD_REQUEST: "요청 형식을 확인해 주세요.",
    ErrorCode.AUTH_CREDENTIALS_INVALID: "아이디 또는 비밀번호가 올바르지 않습니다.",
    ErrorCode.AUTH_SESSION_INVALID: "인증 세션이 유효하지 않습니다.",
    ErrorCode.AUTH_FORBIDDEN: "이 작업을 수행할 권한이 없습니다.",
    ErrorCode.RESOURCE_NOT_FOUND: "요청한 정보를 찾을 수 없습니다.",
    ErrorCode.RESOURCE_CONFLICT: "이미 존재하거나 현재 상태와 충돌합니다.",
    ErrorCode.VALIDATION_ERROR: "요청 값을 확인해 주세요.",
    ErrorCode.INTERNAL_SERVER_ERROR: "서버 오류가 발생했습니다.",
    ErrorCode.UPSTREAM_ERROR: "연동 서비스 처리 중 오류가 발생했습니다.",
    ErrorCode.SERVICE_UNAVAILABLE: "서비스를 일시적으로 사용할 수 없습니다.",
}
