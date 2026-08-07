"""고정 계정 로그인·로그아웃 API입니다."""

import fastapi
import itsdangerous
import sqlalchemy
from sqlalchemy.ext import asyncio as sqlalchemy_async

from app.core import config, database
from app.schemas import auth as auth_schema

router = fastapi.APIRouter(prefix="/api/centagging/auth", tags=["auth"])
COOKIE_NAME = "centagging_session"
MAX_AGE_SECONDS = 8 * 60 * 60


def create_session_token(user_id: int) -> str:
    """사용자 ID를 세션 쿠키에 넣을 문자열로 만듭니다."""
    secret = config.get_settings().session_secret
    if len(secret) < 32:
        raise RuntimeError("SESSION_SECRET은 32자 이상이어야 합니다.")
    serializer = itsdangerous.URLSafeTimedSerializer(secret, salt="centagging-mvp")
    return serializer.dumps({"user_id": user_id})


def get_user_id_from_session(token: str) -> int | None:
    """세션 쿠키를 확인하고 사용자 ID를 반환합니다."""
    secret = config.get_settings().session_secret
    if len(secret) < 32:
        return None
    serializer = itsdangerous.URLSafeTimedSerializer(secret, salt="centagging-mvp")
    try:
        data = serializer.loads(token, max_age=MAX_AGE_SECONDS)
    except itsdangerous.BadSignature:
        return None
    user_id = data.get("user_id")
    if isinstance(user_id, int) and not isinstance(user_id, bool):
        return user_id
    return None


async def get_current_user(
    database_session: sqlalchemy_async.AsyncSession = fastapi.Depends(
        database.get_database_session
    ),
    session_cookie: str | None = fastapi.Cookie(default=None, alias=COOKIE_NAME),
) -> auth_schema.UserResponse:
    """세션 쿠키와 DB를 확인해 현재 사용자를 반환합니다."""
    user_id = get_user_id_from_session(session_cookie) if session_cookie else None
    if user_id is None:
        raise fastapi.HTTPException(status_code=401, detail="로그인이 필요합니다.")

    result = await database_session.execute(
        sqlalchemy.text(
            """
            SELECT user_id, login_id, user_name, is_active
            FROM app_user
            WHERE user_id = :user_id
            """
        ),
        {"user_id": user_id},
    )
    user = result.mappings().one_or_none()
    if user is None or not user["is_active"]:
        raise fastapi.HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return auth_schema.UserResponse(
        user_id=int(user["user_id"]),
        login_id=str(user["login_id"]),
        user_name=str(user["user_name"]),
    )


@router.post("/login", response_model=auth_schema.UserResponse)
async def login(
    request: auth_schema.LoginRequest,
    response: fastapi.Response,
    database_session: sqlalchemy_async.AsyncSession = fastapi.Depends(
        database.get_database_session
    ),
) -> auth_schema.UserResponse:
    """고정 문자열 계정을 비교하고 세션 쿠키를 발급합니다."""
    settings = config.get_settings()
    password = request.password.get_secret_value()
    wrong_id = request.login_id != settings.mvp_login_id
    wrong_password = password != settings.mvp_login_password
    if wrong_id or wrong_password:
        raise fastapi.HTTPException(
            status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다."
        )
    result = await database_session.execute(
        sqlalchemy.text(
            """
            SELECT user_id, login_id, user_name, is_active
            FROM app_user
            WHERE login_id = :login_id
            """
        ),
        {"login_id": request.login_id},
    )
    user = result.mappings().one_or_none()
    if user is None or not user["is_active"]:
        raise fastapi.HTTPException(status_code=401, detail="로그인이 필요합니다.")
    response.set_cookie(
        key=COOKIE_NAME,
        value=create_session_token(user["user_id"]),
        max_age=MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return auth_schema.UserResponse(
        user_id=int(user["user_id"]),
        login_id=str(user["login_id"]),
        user_name=str(user["user_name"]),
    )


@router.post("/logout", status_code=204)
async def logout(response: fastapi.Response) -> None:
    """세션 쿠키를 삭제합니다."""
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/me", response_model=auth_schema.UserResponse)
async def me(
    current_user: auth_schema.UserResponse = fastapi.Depends(get_current_user),
) -> auth_schema.UserResponse:
    """현재 로그인 사용자를 반환합니다."""
    return current_user
