"""SKU 텍스트 임베딩 기반 검색 API입니다."""

import fastapi
from sqlalchemy.ext import asyncio as sqlalchemy_async

import app.schemas.sku_search as sku_search_schema
from app.core import database
from app.core.error_codes import ErrorCode
from app.dependencies import get_gemini_service, get_sku_image_storage
from app.services import sku_search_service
from app.services.gemini_service import (
    GeminiConfigurationError,
    GeminiEmbeddingError,
    GeminiService,
)
from app.services.sku_image_storage import SkuImageStorage

router = fastapi.APIRouter(prefix="/search", tags=["search"])


@router.get("/skus", response_model=sku_search_schema.SkuSearchResponse)
async def search_skus(
    q: str = fastapi.Query(default="", description="검색 프롬프트입니다."),
    session: sqlalchemy_async.AsyncSession = fastapi.Depends(
        database.get_database_session
    ),
    gemini_service: GeminiService = fastapi.Depends(get_gemini_service),
    sku_image_storage: SkuImageStorage = fastapi.Depends(get_sku_image_storage),
) -> sku_search_schema.SkuSearchResponse:
    """검색어와 의미적으로 유사한 SKU 목록을 조회합니다.

    유사도 점수는 응답에는 포함되지만 화면에는 노출하지 않는 값입니다.

    Args:
        q: 검색 프롬프트입니다. 비어 있으면 400을 반환합니다.
        session: 비동기 DB 세션입니다.
        gemini_service: 검색어 텍스트 임베딩 서비스입니다.
        sku_image_storage: 대표 이미지 경로를 공개 URL로 바꾸는 저장소입니다.

    Returns:
        유사도 내림차순으로 정렬된 SKU 검색 결과입니다 (최대 5건).

    Raises:
        fastapi.HTTPException: 검색어가 비어 있으면 400(INVALID_QUERY),
            Gemini 인증이 설정되지 않았으면 503, 임베딩·조회가 실패하면
            502를 반환합니다.
    """
    if not q.strip():
        raise fastapi.HTTPException(
            status_code=400,
            detail={
                "code": ErrorCode.INVALID_QUERY.value,
                "message": ErrorCode.INVALID_QUERY.default_message,
            },
        )

    try:
        data = await sku_search_service.search_skus(
            session, gemini_service, sku_image_storage, q
        )
    except GeminiConfigurationError as error:
        raise fastapi.HTTPException(
            status_code=503,
            detail={
                "code": ErrorCode.SERVICE_UNAVAILABLE.value,
                "message": "검색 기능이 아직 설정되지 않았습니다.",
            },
        ) from error
    except (
        GeminiEmbeddingError,
        sku_search_service.SkuSearchQueryError,
    ) as error:
        raise fastapi.HTTPException(
            status_code=502,
            detail={
                "code": ErrorCode.UPSTREAM_ERROR.value,
                "message": "검색어 처리 중 오류가 발생했습니다.",
            },
        ) from error

    return sku_search_schema.SkuSearchResponse(data=data)


@router.get(
    "/skus/{sku_code}", response_model=sku_search_schema.SkuDetailResponse
)
async def sku_code_detail(
    sku_code: str,
    session: sqlalchemy_async.AsyncSession = fastapi.Depends(
        database.get_database_session
    ),
    sku_image_storage: SkuImageStorage = fastapi.Depends(get_sku_image_storage),
) -> sku_search_schema.SkuDetailResponse:
    """SKU 코드로 카테고리별 속성을 포함한 상세 정보를 조회합니다.

    Args:
        sku_code: 조회할 SKU 코드입니다.
        session: 비동기 DB 세션입니다.
        sku_image_storage: 대표 이미지 경로를 공개 URL로 바꾸는 저장소입니다.

    Returns:
        SKU 상세 정보입니다. image_url은 MAIN 타입 이미지만 포함합니다.

    Raises:
        fastapi.HTTPException: SKU 코드가 존재하지 않으면
            404(SKU_NOT_FOUND)를 반환합니다.
    """
    detail = await sku_search_service.get_sku_detail(
        session, sku_image_storage, sku_code
    )
    if detail is None:
        raise fastapi.HTTPException(
            status_code=404,
            detail={
                "code": ErrorCode.SKU_NOT_FOUND.value,
                "message": ErrorCode.SKU_NOT_FOUND.default_message,
            },
        )

    return sku_search_schema.SkuDetailResponse(data=detail)
