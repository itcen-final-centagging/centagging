import fastapi
import app.schemas.sku_search as sku_search_schema
import typing
from sqlalchemy.ext import asyncio
from app.core import database
from app.services import sku_search_service

router = fastapi.APIRouter(prefix="/search", tags=["search"])


@router.get("/skus", response_model=sku_search_schema.SkuSearchResponse)
async def search_skus(
    keyword: typing.Annotated[str | None, fastapi.Query(description="SKU 코드 또는 상품명 검색어")] = None,
    page: typing.Annotated[int, fastapi.Query(ge=0, description="0부터 시작하는 페이지 번호")] = 0,
    size: typing.Annotated[
        int,
        fastapi.Query(ge=1, le=100, description="페이지당 결과 개수"),
    ] = 10,
    database_session: asyncio.AsyncSession = fastapi.Depends(
        database.get_database_session
    ),
) -> sku_search_schema.SkuSearchResponse:
    """SKU 코드와 상품명을 기준으로 SKU를 검색합니다."""
    normalized_keyword = keyword.strip() if keyword else ""

    if not normalized_keyword:
        raise fastapi.HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_QUERY",
                "message": "keyword는 필수입니다.",
            },
        )

    data = await sku_search_service.search_skus(
        session=database_session,
        keyword=normalized_keyword,
        page=page,
        size=size,
    )

    return sku_search_schema.SkuSearchResponse(data=data)