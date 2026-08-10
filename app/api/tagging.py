from fastapi import APIRouter, Depends, Query, HTTPException
from app.dependencies import get_similar_sku_service

from app.schemas.tagging import DetectionResponse
from app.services.similar_sku_service import SimilarSkuService, SceneImageNotFoundError

router = APIRouter(prefix="/tagging", tags=["tagging"])

@router.get("/scenes/{scene_id}")
async def get_recommendation_sku(
    scene_id: int,
    object_indexes: list[int] = Query(default=[]),
    similar_sku_service: SimilarSkuService= Depends(
        get_similar_sku_service
    ),
) -> DetectionResponse:
    """장면 이미지에서 탐지된 객체들의 유사 SKU를 추천합니다.

        Args:
            scene_id: 조회할 장면 이미지 ID입니다.
            object_indexes: 탐지된 객체 인덱스입니다.
            similar_sku_service: 유사 SKU 조회 서비스입니다.

        Returns:
            탐지된 객체 별 유사 SKU 후보 정보 목록을 반환합니다.
        """
    try:
        result = await similar_sku_service.orchestrate_similar_skus(scene_id, object_indexes)
    except SceneImageNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return DetectionResponse(status="success", data=result)