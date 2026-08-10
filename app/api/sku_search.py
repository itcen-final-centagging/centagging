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

@router.get("/skus/{sku_code}", response_model=sku_search_schema.SkuDetailResponse)
async def sku_code_detail(
    sku_code: str,
) -> sku_search_schema.SkuDetailResponse:
    """POC용 CH-2041 SKU 상세 정보를 반환합니다."""
    normalized_sku_code = sku_code.strip()

    if normalized_sku_code.upper() != "CH-2041":
        raise fastapi.HTTPException(
            status_code=404,
            detail={
                "code": "SKU_NOT_FOUND",
                "message": f"SKU를 찾을 수 없습니다: {normalized_sku_code}",
            },
        )

    data = sku_search_schema.SkuDetailData(
        sku_code="CH-2041",
        product_name="에르고 메쉬 오피스체어 화이트",
        category="의자",
        sub_category="오피스체어",
        key_features={
            "요약": "높은 통기성과 5년 무상 A/S를 제공하는 홈오피스 체어",
        },
        description="메쉬 소재로 통기성이 뛰어난 하이백 오피스체어입니다.",
        attrs={
            "소재": "메쉬 · 패브릭 · 알루미늄",
            "색상": "화이트 / 차콜",
            "형태": "하이백",
            "구조": "5스타 캐스터",
        },
        images=[
            sku_search_schema.SkuImageItem(
                sku_image_id=5501,
                image_type="MAIN",
                image_url="<https://cdn.example.com/skus/CH-2041_main.jpg>",
            ),
            sku_search_schema.SkuImageItem(
                sku_image_id=5502,
                image_type="ANGLE",
                image_url="<https://cdn.example.com/skus/CH-2041_angle.jpg>",
            ),
            sku_search_schema.SkuImageItem(
                sku_image_id=5503,
                image_type="DETAIL",
                image_url="<https://cdn.example.com/skus/CH-2041_detail.jpg>",
            ),
            sku_search_schema.SkuImageItem(
                sku_image_id=5504,
                image_type="STYLING",
                image_url="<https://cdn.example.com/skus/CH-2041_styling.jpg>",
            ),
        ],
    )
    return sku_search_schema.SkuDetailResponse(data=data)
