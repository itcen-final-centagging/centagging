from fastapi import APIRouter, Depends
from app.dependencies import get_similar_sku_service

from app.schemas.tagging import DetectionResponse, DetectionResult
from app.services.similar_sku_service import SimilarSkuService

router = APIRouter(prefix="/tagging", tags=["tagging"])

@router.get("/scenes/{scene_id}")
async def get_recommendation_sku(
    scene_id: int,
    similar_sku_service: SimilarSkuService= Depends(
        get_similar_sku_service
    ),
) -> DetectionResponse:
    """장면 이미지에서 탐지된 객체들의 유사 SKU를 추천합니다.

        Args:
            scene_id: 조회할 장면 이미지 ID입니다.
            similar_sku_service: 유사 SKU 조회 서비스입니다.

        Returns:
            추천 SKU 목록입니다. detected_object 연동 전까지는 빈 목록을
            반환합니다.
        """
    result = await similar_sku_service.orchestrate_similar_skus(scene_id)

    return DetectionResponse(status="success", data=result)