import fastapi
import app.schemas.sku_search as sku_search_schema

router = fastapi.APIRouter(prefix="/search", tags=["search"])


@router.get("/skus", response_model=sku_search_schema.SkuSearchResponse)
async def search_skus(
    q: str = fastapi.Query()
):
    return {
      "status": "success",
      "data": {
        "skus": [
          {
            "sku_code": "CHR-2041",
            "product_name": "에르고 메쉬 오피스체어 화이트",
            "category": "의자",
            "sub_category": "학생·사무용의자",
            "attrs": { "color": "화이트", "material": "메쉬", "style": "모던" }
          }
        ]
      }
    }


@router.get("/skus/{sku_code}", response_model=sku_search_schema.SkuDetailResponse)
async def sku_code_detail(
    sku_code: str,
):
    return {
      "status": "success",
      "data": {
        "sku_code": sku_code,
        "product_name": "에르고 메쉬 오피스체어 화이트",
        "brand": "센터퍼니처",
        "price": 249000,
        "category": "의자",
        "sub_category": "학생·사무용의자",
        "key_features": ["통기성이 우수한 메쉬 소재", "높이 조절 가능", "크기 W650 x D650 x H1150mm"],
        "attrs": { "color": "화이트", "material": "메쉬", "style": "모던" },
        "image_url": "/uploads/sku-images/CHR-2041_main.jpg"
      }
    }

