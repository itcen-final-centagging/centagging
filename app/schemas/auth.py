"""로그인 API의 요청 및 응답 모델입니다."""

from typing import Literal

import pydantic

UserRole = Literal["USER", "ADMIN", "SUPER_ADMIN"]


class ErrorResponse(pydantic.BaseModel):
    """인증 요청 실패 시 반환하는 오류 응답입니다."""

    detail: str = pydantic.Field(
        description="사용자에게 표시할 오류 메시지입니다."
    )


class ValidationErrorDetail(pydantic.BaseModel):
    """입력값 하나에 대한 검증 오류 상세입니다."""

    type: str = pydantic.Field(
        description="오류를 구분하는 시스템용 코드입니다. 예: string_too_short"
    )
    loc: list[str | int] = pydantic.Field(
        description=(
            "오류가 발생한 위치입니다. 예: [body, login_id]는 요청 본문의 "
            "login_id 필드를 뜻합니다."
        )
    )
    msg: str = pydantic.Field(
        description="검증에 실패한 이유를 설명하는 메시지입니다."
    )
    input: object | None = pydantic.Field(
        default=None,
        description="클라이언트가 실제로 전달한 잘못된 값입니다.",
    )
    ctx: dict[str, object] | None = pydantic.Field(
        default=None,
        description=(
            "검증 기준에 사용한 추가 정보입니다. 예: min_length는 최소 글자 수입니다."
        ),
    )


class ValidationErrorResponse(pydantic.BaseModel):
    """요청 본문 또는 필드 형식이 API 규칙에 맞지 않을 때의 오류 응답입니다."""

    detail: list[ValidationErrorDetail] = pydantic.Field(
        description="검증에 실패한 필드별 오류 목록입니다."
    )


class LoginRequest(pydantic.BaseModel):
    """고정 계정 로그인 요청입니다."""

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [{"login_id": "user", "password": "1234"}]
        }
    )

    login_id: str = pydantic.Field(
        description="로그인에 사용할 사용자 아이디입니다.",
        min_length=1,
        max_length=50,
    )
    password: pydantic.SecretStr = pydantic.Field(
        description="사용자 비밀번호입니다.",
    )


class UserResponse(pydantic.BaseModel):
    """고정 세션으로 인증된 사용자 정보입니다."""

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "user_id": 1,
                    "login_id": "user",
                    "user_name": "일반 사용자",
                    "role": "USER",
                    "session": "centagging-poc-user-session",
                }
            ]
        }
    )

    user_id: int = pydantic.Field(description="사용자 고유 번호입니다.")
    login_id: str = pydantic.Field(description="사용자 로그인 아이디입니다.")
    user_name: str = pydantic.Field(
        description="화면에 표시할 사용자 이름입니다."
    )
    role: UserRole = pydantic.Field(
        description="사용자 권한입니다. USER, ADMIN, SUPER_ADMIN 중 하나입니다."
    )
    session: str = pydantic.Field(
        description="이후 인증 요청의 Authorization Bearer 값으로 사용할 고정 세션입니다."
    )
