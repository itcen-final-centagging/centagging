import fastapi
from sqlalchemy.ext import asyncio as sqlalchemy_async

from app.core import database
from app.repositories import tagging_history_repository
from app.schemas import history as history_schema

router = fastapi.APIRouter(prefix="/history", tags=["history"])


@router.get(
    "/results",
    response_model=history_schema.TaggingHistoryListResponse,
)
async def list_tagging_history(
    session: sqlalchemy_async.AsyncSession = fastapi.Depends(
        database.get_database_session
    ),
) -> history_schema.TaggingHistoryListResponse:
    """저장된 태깅 결과를 최신순으로 조회합니다.

    Args:
        session: 요청 범위의 비동기 DB 세션입니다.

    Returns:
        검수 이력 화면에 표시할 태깅 결과 목록입니다.
    """
    items = await tagging_history_repository.list_tagging_history(session)
    return history_schema.TaggingHistoryListResponse(
        status="success",
        data={"items": items},
    )


@router.get("/results/{result_id}")
def get_tagging_history(result_id):
    return {
      "status": "success",
      "data": {
        "result_id": 8801,
        "created_by": "김태깅",
        "created_at": "2026-08-10T17:56:00+09:00",
        "similarity_score": 92,
        "scene_image": {
          "image_url": "/uploads/scene-images/9f2c.jpg",
          "origin_name": "scene_office_01.jpg"
        },
        "detected_object": {
          "category": "의자",
          "sub_category": "학생·사무용의자",
          "attrs": { "color": "화이트", "material": "메쉬" },
          "bbox": { "xmin": 262, "ymin": 300, "xmax": 681, "ymax": 890 },
          "vlm_mood": {
            "summary": "밝은 자연광이 드는 미니멀한 홈오피스에 어울리는 화이트 톤 워크체어입니다.",
            "tags": ["미니멀", "내추럴", "홈오피스", "밝은 톤"]
          }
        },
        "matched_sku": {
          "sku_code": "CHR-2041",
          "product_name": "에르고 메쉬 오피스체어 화이트",
          "brand": "센터퍼니처",
          "price": 249000,
          "image_url": "/uploads/sku-images/CHR-2041_main.jpg",
          "category": "의자",
          "sub_category": "학생·사무용의자",
          "attrs": { "color": "화이트", "material": "메쉬" }
        },
        "xai_result": {
          "summary": "등받이 곡률과 헤드레스트 형태가 거의 동일하고 색상까지 일치합니다.",
          "criteria": [
            { "label": "구조", "score": 29, "comment": "등받이 곡률·암레스트 각도가 일치합니다." },
            { "label": "색상", "score": 28, "comment": "화이트 바디와 차콜 메쉬 조합이 같습니다." },
            { "label": "디테일", "score": 17, "comment": "5스타 캐스터 형태가 유사합니다." },
            { "label": "맥락", "score": 18, "comment": "홈오피스 연출과 사용 공간이 맞습니다." }
          ]
        }
      }
    }
