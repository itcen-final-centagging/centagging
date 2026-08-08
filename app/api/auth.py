"""세션을 사용하지 않는 고정 계정 로그인 API입니다."""

import fastapi
import sqlalchemy
from sqlalchemy.ext import asyncio as sqlalchemy_async

from app.core import config, database
from app.schemas import auth as auth_schema

router = fastapi.APIRouter(prefix="/api/centagging/auth", tags=["auth"])


@router.post("/login", response_model=auth_schema.UserResponse)
async def login(
    request: auth_schema.LoginRequest,
    database_session: sqlalchemy_async.AsyncSession = fastapi.Depends(
        database.get_database_session
    ),
) -> auth_schema.UserResponse:
    """고정 자격 증명과 DB의 활성 계정을 확인합니다."""
    settings = config.get_settings()
    password = request.password.get_secret_value()
    wrong_id = request.login_id != settings.mvp_login_id
    wrong_password = password != settings.mvp_login_password
    if wrong_id or wrong_password:
        raise fastapi.HTTPException(
            status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다."
        )
    result = await database_session.execute(
        sqlalchemy.text("""
            SELECT user_id, login_id, user_name, is_active
            FROM app_user
            WHERE login_id = :login_id
            """),
        {"login_id": request.login_id},
    )
    user = result.mappings().one_or_none()
    if user is None or not user["is_active"]:
        raise fastapi.HTTPException(
            status_code=401,
            detail="아이디 또는 비밀번호가 올바르지 않습니다.",
        )
    return auth_schema.UserResponse(
        user_id=int(user["user_id"]),
        login_id=str(user["login_id"]),
        user_name=str(user["user_name"]),
    )
