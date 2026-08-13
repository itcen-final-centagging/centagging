"""DB 고정 세션을 사용하는 POC 인증 API입니다."""

import hashlib

import fastapi
import sqlalchemy
from sqlalchemy.ext import asyncio as sqlalchemy_async

from app.core import database
from app.schemas import auth as auth_schema

router = fastapi.APIRouter(prefix="/auth", tags=["auth"])

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


def _hash_password(password: str) -> str:
    """POC 비밀번호를 DB에 저장한 SHA-256 해시로 변환합니다."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _to_user_response(user: sqlalchemy.RowMapping) -> auth_schema.UserResponse:
    """DB 사용자 행을 인증 응답 모델로 변환합니다."""
    return auth_schema.UserResponse(
        user_id=int(user["user_id"]),
        login_id=str(user["login_id"]),
        user_name=str(user["user_name"]),
        role=str(user["role"]),
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


@router.post("/login", response_model=auth_schema.UserResponse)
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


@router.get("/me", response_model=auth_schema.UserResponse)
async def get_current_user(
    authorization: str | None = fastapi.Header(default=None),
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
