"""장면 이미지 태깅(유사 SKU 추천) API입니다."""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_similar_sku_service
from app.schemas.tagging import DetectionResponse
from app.services.similar_sku_service import (
    SceneImageNotFoundError,
    SimilarSkuService,
)

router = APIRouter(prefix="/tagging", tags=["tagging"])


@router.get("/scenes/{scene_id}")
async def get_recommendation_sku(
    scene_id: int,
    object_indexes: list[int] = Query(default=[]),
    similar_sku_service: SimilarSkuService = Depends(get_similar_sku_service),
) -> DetectionResponse:
    """장면 이미지에서 탐지된 객체들의 유사 SKU를 추천합니다.

    Args:
        scene_id: 조회할 장면 이미지 ID입니다.
        object_indexes: 탐지된 객체 인덱스입니다.
        similar_sku_service: 유사 SKU 조회 서비스입니다.

    Returns:
        탐지된 객체 별 유사 SKU 후보 정보 목록을 반환합니다.

    Raises:
        HTTPException: scene_id에 해당하는 장면 이미지가 없는 경우
            404를 반환합니다.
    """
    try:
        result = await similar_sku_service.orchestrate_similar_skus(
            scene_id, object_indexes
        )
    except SceneImageNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return DetectionResponse(status="success", data=result)

@router.put("/scenes/{scene_id}")
def update_scene(scene_id: int):
    return {
      "matching": [
        {
          "object_index": 0,
          "sku_code": "CHR-2041",
          "similarity_score": 92,
          "xai_result": {
            "summary": "등받이 곡률과 헤드레스트 형태가 거의 동일하고 색상까지 일치합니다.",
            "criteria": [
              { "label": "구조", "score": 29, "comment": "등받이 곡률·암레스트 각도가 일치합니다." },
              { "label": "색상", "score": 28, "comment": "화이트 바디와 차콜 메쉬 조합이 같습니다." },
              { "label": "디테일", "score": 17, "comment": "5스타 캐스터 형태가 유사합니다." },
              { "label": "맥락", "score": 18, "comment": "홈오피스 연출과 사용 공간이 맞습니다." }
            ]
          },
          "vlm_mood": {
            "summary": "밝은 자연광이 드는 미니멀한 홈오피스에 어울리는 화이트 톤 워크체어입니다.",
            "tags": ["미니멀", "내추럴", "홈오피스", "밝은 톤"]
          }
        }
      ]
    }
