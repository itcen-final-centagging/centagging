"""DB 고정 세션을 사용하는 POC 인증 API입니다."""

import hashlib
import typing

import fastapi
import sqlalchemy
from sqlalchemy.ext import asyncio as sqlalchemy_async

from app.api.examples import (
    INVALID_CREDENTIALS_DETAIL,
    LOGIN_SUCCESS_RESPONSE,
    LOGIN_UNAUTHORIZED_RESPONSE,
    LOGIN_VALIDATION_ERROR_RESPONSE,
    ME_SUCCESS_RESPONSE,
    SESSION_UNAUTHORIZED_RESPONSE,
    UNAUTHORIZED_DETAIL,
)
from app.core import database
from app.schemas import auth as auth_schema
from app.schemas import common as common_schema

router = fastapi.APIRouter(
    prefix="/auth",
    tags=["인증"],
)

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
        role=typing.cast(auth_schema.UserRole, str(user["role"])),
        session=str(user["session"]),
    )


def _get_bearer_session(authorization: str | None) -> str:
    """Authorization 헤더에서 Bearer 세션을 반환합니다.

    Raises:
        fastapi.HTTPException: Bearer 세션이 없거나 형식이 잘못된 경우입니다.
    """
    if authorization is None:
        raise fastapi.HTTPException(status_code=401, detail=UNAUTHORIZED_DETAIL)
    scheme, _, session = authorization.partition(" ")
    if scheme.lower() != "bearer" or not session:
        raise fastapi.HTTPException(status_code=401, detail=UNAUTHORIZED_DETAIL)
    return session


@router.post(
    "/login",
    response_model=common_schema.SuccessResponse[auth_schema.UserResponse],
    summary="아이디와 비밀번호로 로그인",
    description=(
        "등록된 사용자 아이디와 비밀번호를 확인합니다. "
        "성공하면 사용자 정보와 이후 인증에 사용할 고정 세션을 반환합니다."
    ),
    response_description="공통 성공 응답으로 사용자 정보와 고정 세션을 반환합니다.",
    responses={
        200: LOGIN_SUCCESS_RESPONSE,
        401: LOGIN_UNAUTHORIZED_RESPONSE,
        422: LOGIN_VALIDATION_ERROR_RESPONSE,
    },
)
async def login(
    request: auth_schema.LoginRequest,
    database_session: sqlalchemy_async.AsyncSession = fastapi.Depends(
        database.get_database_session
    ),
) -> common_schema.SuccessResponse[auth_schema.UserResponse]:
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
            detail=INVALID_CREDENTIALS_DETAIL,
        )
    return common_schema.success_response(_to_user_response(user))


@router.get(
    "/me",
    response_model=common_schema.SuccessResponse[auth_schema.UserResponse],
    summary="현재 로그인 사용자 조회",
    description=(
        "Authorization 헤더에 `Bearer {session}` 형식으로 세션을 전달하면 "
        "DB에 저장된 세션과 비교해 현재 사용자 정보를 반환합니다. "
        "헤더는 필수이며, 누락하거나 형식 또는 값이 맞지 않으면 401을 반환합니다."
    ),
    response_description="공통 성공 응답으로 현재 사용자 정보를 반환합니다.",
    responses={200: ME_SUCCESS_RESPONSE, 401: SESSION_UNAUTHORIZED_RESPONSE},
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
) -> common_schema.SuccessResponse[auth_schema.UserResponse]:
    """Bearer 세션과 DB 세션이 일치하는 현재 사용자를 반환합니다."""
    session = _get_bearer_session(authorization)
    result = await database_session.execute(
        _SELECT_SESSION_USER,
        {"session": session},
    )
    user = result.mappings().one_or_none()
    if user is None:
        raise fastapi.HTTPException(status_code=401, detail=UNAUTHORIZED_DETAIL)
    return common_schema.success_response(_to_user_response(user))
