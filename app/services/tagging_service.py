"""장면 이미지 태깅 흐름을 단계별로 조립하는 오케스트레이션 서비스입니다."""

import asyncio
import pathlib

from sqlalchemy.ext import asyncio as sqlalchemy_async

from app.core.config import Settings
from app.models.scene_image import SceneImage
from app.repositories.scene_image_repository import get_scene_image
from app.schemas.tagging import DetectionResult, SceneImageInfo
from app.services.image_processing_service import crop_scene_objects
from app.services.similar_sku_service import SimilarSkuService
from app.services.xai_scoring_service import XaiScoringService

DETECTED_STATUS = "DETECTED"


class TaggingService:
    """crop → 유사 SKU 탐색 → XAI 순으로 태깅 응답을 만드는 서비스입니다."""

    def __init__(
        self,
        session: sqlalchemy_async.AsyncSession,
        settings: Settings,
        similar_sku_service: SimilarSkuService,
        xai_scoring_service: XaiScoringService,
    ) -> None:
        """오케스트레이션에 필요한 세션과 단계별 서비스를 주입받습니다.

        Args:
            session: 요청 범위의 비동기 SQLAlchemy 세션입니다.
            settings: 이미지 저장소 경로가 담긴 애플리케이션 설정입니다.
            similar_sku_service: 임베딩과 유사 SKU 탐색 담당 서비스입니다.
            xai_scoring_service: XAI 근거 산출 담당 서비스입니다.
        """
        self.session = session
        self.settings = settings
        self.similar_sku_service = similar_sku_service
        self.xai_scoring_service = xai_scoring_service

    async def get_sku_candidates(
        self,
        scene_image_id: int,
    ) -> DetectionResult:
        """장면 이미지 1건의 유사 SKU 추천 결과를 만듭니다.

        연출 이미지 crop → 임베딩 및 유사 SKU 탐색 → XAI 근거 산출
        순서로 응답 객체를 단계마다 채워 나갑니다.

        Args:
            scene_image_id: 조회할 장면 이미지 ID입니다.

        Returns:
            탐지 객체별 SKU 후보와 XAI 판정이 담긴 결과입니다.

        Raises:
            SceneImageNotFoundError: 장면 이미지가 없는 경우입니다.
            InvalidImageError: 장면 원본 이미지를 열 수 없는 경우입니다.
        """
        scene = await get_scene_image(self.session, scene_image_id)
        result = DetectionResult(
            processing_status=DETECTED_STATUS,
            scene_image=self._to_scene_image_info(scene),
            objects=[],
        )

        # 1) 연출 이미지 crop
        crops = await asyncio.to_thread(
            crop_scene_objects,
            self._resolve_image_path(scene),
            list(scene.object_metadata),
        )

        # 2) 임베딩 및 유사 SKU 탐색
        result.objects = await self.similar_sku_service.build_detected_objects(
            crops
        )

        # 3) XAI 근거 산출
        result.objects = await self.xai_scoring_service.enrich_detected_objects(
            crops, result.objects
        )

        return result

    def _resolve_image_path(self, scene: SceneImage) -> pathlib.Path:
        """``scene_image.image_url``을 실제 저장소 경로로 변환합니다.

        Args:
            scene: 조회한 장면 이미지 엔티티입니다.

        Returns:
            장면 원본 이미지의 파일 경로입니다.
        """
        return pathlib.Path(
            self.settings.image_storage_root
        ) / scene.image_url.removeprefix("/uploads/")

    @staticmethod
    def _to_scene_image_info(scene: SceneImage) -> SceneImageInfo:
        """장면 이미지 엔티티를 응답 메타데이터로 변환합니다.

        Args:
            scene: 조회한 장면 이미지 엔티티입니다.

        Returns:
            응답에 포함할 장면 이미지 메타데이터입니다.
        """
        return SceneImageInfo(
            scene_image_id=scene.scene_image_id,
            image_url=scene.image_url,
            origin_name=scene.origin_name,
            mime_type=scene.mime_type,
            file_size=scene.file_size,
            width_px=scene.width_px,
            height_px=scene.height_px,
        )
