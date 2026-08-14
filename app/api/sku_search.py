"""SKU 카탈로그 검색 API입니다."""

import fastapi

import app.schemas.sku_search as sku_search_schema

router = fastapi.APIRouter(prefix="/search", tags=["search"])


@router.get("/skus", response_model=sku_search_schema.SkuSearchResponse)
async def search_skus(q: str = fastapi.Query()) -> dict[str, object]:
    """검색어와 일치하는 SKU 목록을 반환합니다.

    Args:
        q: SKU 코드 또는 상품명 검색어입니다.

    Returns:
        검색된 SKU 목록을 담은 성공 응답입니다.
    """
    _ = q
    return {
        "status": "success",
        "data": {
            "skus": [
                {
                    "sku_code": "CHR-2041",
                    "product_name": "에르고 메쉬 오피스체어 화이트",
                    "category": "의자",
                    "sub_category": "학생·사무용의자",
                    "attrs": {
                        "color": "화이트",
                        "material": "메쉬",
                        "style": "모던",
                    },
                }
            ]
        },
    }


@router.get(
    "/skus/{sku_code}", response_model=sku_search_schema.SkuDetailResponse
)
async def sku_code_detail(
    sku_code: str,
) -> dict[str, object]:
    """SKU 코드에 해당하는 상품 상세를 반환합니다.

    Args:
        sku_code: 조회할 SKU 상품 코드입니다.

    Returns:
        SKU 상세 정보를 담은 성공 응답입니다.
    """
    return {
        "status": "success",
        "data": {
            "sku_code": sku_code,
            "product_name": "에르고 메쉬 오피스체어 화이트",
            "brand": "센터퍼니처",
            "price": 249000,
            "category": "의자",
            "sub_category": "학생·사무용의자",
            "key_features": [
                "통기성이 우수한 메쉬 소재",
                "높이 조절 가능",
                "크기 W650 x D650 x H1150mm",
            ],
            "attrs": {"color": "화이트", "material": "메쉬", "style": "모던"},
            "image_url": "/uploads/sku-images/CHR-2041_main.jpg",
        },
    }
