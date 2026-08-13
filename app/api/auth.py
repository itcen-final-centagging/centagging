"""DB 고정 세션을 사용하는 POC 인증 API입니다."""

import hashlib
import typing

import fastapi
import sqlalchemy
from sqlalchemy.ext import asyncio as sqlalchemy_async

from app.core import database
from app.schemas import auth as auth_schema

router = fastapi.APIRouter(
    prefix="/auth",
    tags=["인증"],
)

_INVALID_CREDENTIALS_DETAIL = "아이디 또는 비밀번호가 올바르지 않습니다."
_UNAUTHORIZED_DETAIL = "인증 세션이 유효하지 않습니다."

_SELECT_LOGIN_USER = sqlalchemy.text("""
    SELECT user_id, login_id, user_name, role, session
    FROM app_user
    WHERE login_id = :login_id
      AND password_hash = :password_hash
      AND is_active = TRUE
    """)

_SELECT_SESSION_USER = sqlalchemy.text("""
    SELECT user_id, login_id, user_name, role, session
    FROM app_user
    WHERE session = :session
      AND is_active = TRUE
    """)

_LOGIN_UNAUTHORIZED_RESPONSE = {
    "model": auth_schema.ErrorResponse,
    "description": "아이디 또는 비밀번호가 일치하지 않은 경우입니다.",
    "content": {
        "application/json": {
            "example": {"detail": "아이디 또는 비밀번호가 올바르지 않습니다."}
        }
    },
}

_SESSION_UNAUTHORIZED_RESPONSE = {
    "model": auth_schema.ErrorResponse,
    "description": (
        "Bearer 세션이 없거나 형식이 잘못되었거나 "
        "DB 값과 일치하지 않은 경우입니다."
    ),
    "content": {
        "application/json": {
            "example": {"detail": "인증 세션이 유효하지 않습니다."}
        }
    },
}

_LOGIN_VALIDATION_ERROR_RESPONSE = {
    "model": auth_schema.ValidationErrorResponse,
    "description": "아이디 또는 비밀번호가 없거나 형식이 올바르지 않은 경우입니다.",
    "content": {
        "application/json": {
            "example": {
                "detail": [
                    {
                        "type": "string_too_short",
                        "loc": ["body", "login_id"],
                        "msg": "String should have at least 1 character",
                        "input": "",
                        "ctx": {"min_length": 1},
                    }
                ]
            }
        }
    },
}


def _hash_password(password: str) -> str:
    """POC 비밀번호를 DB에 저장한 SHA-256 해시로 변환합니다."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _to_user_response(user: sqlalchemy.RowMapping) -> auth_schema.UserResponse:
    """DB 사용자 행을 인증 응답 모델로 변환합니다."""
    return auth_schema.UserResponse(
        user_id=int(user["user_id"]),
        login_id=str(user["login_id"]),
        user_name=str(user["user_name"]),
        role=typing.cast(auth_schema.UserRole, str(user["role"])),
        session=str(user["session"]),
    )


def _get_bearer_session(authorization: str | None) -> str:
    """Authorization 헤더에서 Bearer 세션을 반환합니다.

    Raises:
        fastapi.HTTPException: Bearer 세션이 없거나 형식이 잘못된 경우입니다.
    """
    if authorization is None:
        raise fastapi.HTTPException(
            status_code=401, detail=_UNAUTHORIZED_DETAIL
        )
    scheme, _, session = authorization.partition(" ")
    if scheme.lower() != "bearer" or not session:
        raise fastapi.HTTPException(
            status_code=401, detail=_UNAUTHORIZED_DETAIL
        )
    return session


@router.post(
    "/login",
    response_model=auth_schema.UserResponse,
    summary="아이디와 비밀번호로 로그인",
    description=(
        "등록된 사용자 아이디와 비밀번호를 확인합니다. "
        "성공하면 사용자 정보와 이후 인증에 사용할 고정 세션을 반환합니다."
    ),
    response_description="로그인한 사용자 정보와 고정 세션을 반환합니다.",
    responses={
        401: _LOGIN_UNAUTHORIZED_RESPONSE,
        422: _LOGIN_VALIDATION_ERROR_RESPONSE,
    },
)
async def login(
    request: auth_schema.LoginRequest,
    database_session: sqlalchemy_async.AsyncSession = fastapi.Depends(
        database.get_database_session
    ),
) -> auth_schema.UserResponse:
    """DB 고정 사용자 계정으로 로그인하고 저장된 세션을 반환합니다."""
    result = await database_session.execute(
        _SELECT_LOGIN_USER,
        {
            "login_id": request.login_id,
            "password_hash": _hash_password(
                request.password.get_secret_value()
            ),
        },
    )
    user = result.mappings().one_or_none()
    if user is None:
        raise fastapi.HTTPException(
            status_code=401,
            detail=_INVALID_CREDENTIALS_DETAIL,
        )
    return _to_user_response(user)


@router.get(
    "/me",
    response_model=auth_schema.UserResponse,
    summary="현재 로그인 사용자 조회",
    description=(
        "Authorization 헤더에 `Bearer {session}` 형식으로 세션을 전달하면 "
        "DB에 저장된 세션과 비교해 현재 사용자 정보를 반환합니다. "
        "헤더는 필수이며, 누락하거나 형식 또는 값이 맞지 않으면 401을 반환합니다."
    ),
    response_description="세션과 일치하는 현재 사용자 정보를 반환합니다.",
    responses={401: _SESSION_UNAUTHORIZED_RESPONSE},
)
async def get_current_user(
    authorization: str | None = fastapi.Header(
        default=None,
        description=(
            "로그인 응답의 session을 `Bearer {session}` 형식으로 전달합니다."
        ),
        openapi_examples={
            "user_session": {
                "summary": "일반 사용자 세션",
                "value": "Bearer centagging-poc-user-session",
            }
        },
    ),
    database_session: sqlalchemy_async.AsyncSession = fastapi.Depends(
        database.get_database_session
    ),
) -> auth_schema.UserResponse:
    """Bearer 세션과 DB 세션이 일치하는 현재 사용자를 반환합니다."""
    session = _get_bearer_session(authorization)
    result = await database_session.execute(
        _SELECT_SESSION_USER,
        {"session": session},
    )
    user = result.mappings().one_or_none()
    if user is None:
        raise fastapi.HTTPException(
            status_code=401, detail=_UNAUTHORIZED_DETAIL
        )
    return _to_user_response(user)
