"""로그인 API의 요청 및 응답 모델입니다."""

import pydantic


class LoginRequest(pydantic.BaseModel):
    """고정 계정 로그인 요청입니다."""

    login_id: str = pydantic.Field(min_length=1, max_length=50)
    password: pydantic.SecretStr


class UserResponse(pydantic.BaseModel):
    """고정 세션으로 인증된 사용자 정보입니다."""

    user_id: int
    login_id: str
    user_name: str
    role: str
    session: str
