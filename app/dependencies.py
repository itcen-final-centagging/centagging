"""라우터에서 공통으로 사용하는 FastAPI 의존성입니다."""

import typing

import fastapi
import sqlalchemy
from fastapi import Depends
from sqlalchemy.ext import asyncio as sqlalchemy_async

from app.core import config, database
from app.services.approval_service import ApprovalService
from app.services.gemini_service import GeminiService
from app.services.product_image_submission_service import (
    ProductImageSubmissionService,
)
from app.services.similar_sku_service import SimilarSkuService
from app.services.sku_image_storage import SkuImageStorage
from app.services.sku_match_service import SkuMatchService
from app.services.tagging_service import TaggingService
from app.services.xai_scoring_service import XaiScoringService


# NOTE: 기존 공용 의존성 모듈을 확장합니다. 관리자 API가 같은 세션·권한
# 검증 규칙을 사용하도록 이곳에 단일 진입점을 둡니다.
class AdminUser(typing.TypedDict):
    """관리자 권한 확인에 필요한 현재 사용자 정보입니다."""

    user_id: int
    user_name: str
    role: str


_SELECT_ACTIVE_SESSION_USER = sqlalchemy.text("""
    SELECT user_id, user_name, role
      FROM app_user
     WHERE session = :session
       AND is_active = TRUE
    """)


def _get_bearer_session(authorization: str | None) -> str:
    """Authorization 헤더에서 Bearer 세션 값을 반환합니다."""
    scheme, separator, session = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not separator or not session:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
            detail="인증이 필요합니다.",
        )
    return session


async def get_admin_user(
    authorization: str | None = fastapi.Header(default=None),
    session: sqlalchemy_async.AsyncSession = fastapi.Depends(
        database.get_database_session
    ),
) -> AdminUser:
    """유효한 ADMIN 또는 SUPER_ADMIN 사용자 정보를 반환합니다."""
    result = await session.execute(
        _SELECT_ACTIVE_SESSION_USER,
        {"session": _get_bearer_session(authorization)},
    )
    user = result.mappings().one_or_none()
    if user is None:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
            detail="세션이 유효하지 않습니다.",
        )
    if user["role"] not in {"ADMIN", "SUPER_ADMIN"}:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_403_FORBIDDEN,
            detail="관리자 권한이 필요합니다.",
        )
    return {
        "role": str(user["role"]),
        "user_id": int(user["user_id"]),
        "user_name": str(user["user_name"]),
    }


def require_super_admin(
    user: AdminUser = fastapi.Depends(get_admin_user),
) -> AdminUser:
    """SKU 카탈로그를 변경할 수 있는 최종 관리자만 허용합니다."""
    if user["role"] != "SUPER_ADMIN":
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_403_FORBIDDEN,
            detail="최종 관리자 권한이 필요합니다.",
        )
    return user


def get_sku_image_storage() -> SkuImageStorage:
    """설정된 SKU 이미지 저장소를 반환합니다.

    Returns:
        SKU 이미지 저장 경로와 공개 URL 변환기입니다.
    """
    return SkuImageStorage(config.get_settings().sku_image_root)


def get_tagging_service(
    session: sqlalchemy_async.AsyncSession = Depends(
        database.get_database_session
    ),
) -> TaggingService:
    """요청 범위 세션으로 태깅 오케스트레이션 서비스를 조립합니다.

    Args:
        session: 요청 범위의 비동기 SQLAlchemy 세션입니다.

    Returns:
        유사 SKU 조회와 XAI 채점이 주입된 TaggingService입니다.
    """
    settings = config.get_settings()

    return TaggingService(
        session=session,
        settings=settings,
        similar_sku_service=SimilarSkuService(
            session=session,
            gemini_service=GeminiService(settings=settings),
            settings=settings,
        ),
        xai_scoring_service=XaiScoringService(settings=settings),
    )


def get_sku_match_service(
    session: sqlalchemy_async.AsyncSession = Depends(
        database.get_database_session
    ),
) -> SkuMatchService:
    """요청 범위 세션으로 SKU 확정 서비스를 조립합니다.

    Args:
        session: 요청 범위의 비동기 SQLAlchemy 세션입니다.

    Returns:
        설정이 주입된 SkuMatchService입니다.
    """
    return SkuMatchService(
        session=session,
        settings=config.get_settings(),
    )


def get_approval_service(
    session: sqlalchemy_async.AsyncSession = Depends(
        database.get_database_session
    ),
) -> ApprovalService:
    """요청 범위 세션으로 승인 요청 서비스를 조립합니다.

    Args:
        session: 요청 범위의 비동기 SQLAlchemy 세션입니다.

    Returns:
        설정이 주입된 ApprovalService입니다.
    """
    return ApprovalService(session=session, settings=config.get_settings())


def get_product_image_submission_service(
    session: sqlalchemy_async.AsyncSession = Depends(
        database.get_database_session
    ),
) -> ProductImageSubmissionService:
    """요청 범위 세션으로 제품 이미지 등록 승인 서비스를 조립합니다."""
    return ProductImageSubmissionService(
        session=session,
        settings=config.get_settings(),
    )
