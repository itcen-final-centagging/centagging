"""로그인 API의 요청 및 응답 모델입니다."""

from typing import Literal

import pydantic

UserRole = Literal["USER", "ADMIN", "SUPER_ADMIN"]


class LoginRequest(pydantic.BaseModel):
    """고정 계정 로그인 요청입니다."""

    model_config = pydantic.ConfigDict(
        json_schema_extra={"examples": [{"login_id": "user", "password": "1234"}]}
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
    user_name: str = pydantic.Field(description="화면에 표시할 사용자 이름입니다.")
    role: UserRole = pydantic.Field(
        description="사용자 권한입니다. USER, ADMIN, SUPER_ADMIN 중 하나입니다."
    )
    session: str = pydantic.Field(
        description="이후 인증 요청의 Authorization Bearer 값으로 사용할 고정 세션입니다."
    )
