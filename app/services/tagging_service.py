import pathlib
from PIL import Image
import asyncio
import logging

from app.core.config import Settings
from app.models.scene_image import SceneImage
from app.services.gemini_service import GeminiService
from sqlalchemy.ext import asyncio as sqlalchemy_async

from app.services.similar_sku_service import SimilarSkuService
from app.services.xai_scoring_service import (
    RubricScoreResult,
    ScoringCandidate,
    ScoringCrop,
    XaiScoringService,
)
from app.services.image_processing_service import read_sku_image_bytes, parse_image_to_bytes

from app.repositories.scene_image_repository import get_scene_image

from app.schemas.tagging import (
    BoundingBox,
    DetectedObject,
    DetectionResult,
    MatchedSkuImage,
    SceneImageInfo,
    SkuCandidate,
    XaiResult,
)

_LOGGER = logging.getLogger(__name__)

class TaggingService:

    semaphore = asyncio.Semaphore(2)

    def __init__(
        self,
        session: sqlalchemy_async.AsyncSession,
        get_crop_image,
        settings: Settings,
        similar_sku_service: SimilarSkuService,
        xai_scoring_service: XaiScoringService,
        gemini_service: GeminiService,
    ):
        self.session = session
        self.settings = settings
        self.get_crop_image = get_crop_image
        self.similar_sku_service = similar_sku_service
        self.xai_scoring_service = xai_scoring_service
        self.gemini_service = gemini_service

    async def get_sku_candidates(self, scene_image_id) -> DetectionResult:
        scene = await get_scene_image(self.session, scene_image_id)

        image_path = pathlib.Path(
            self.settings.image_storage_root
        ) / scene.image_url.removeprefix("/uploads/")

        objects = []
        with Image.open(image_path) as scene_image:
            scene_image.load()
            for idx, bbox in enumerate(scene.bbox_coord):
                crop_image = self.get_crop_image(
                        image=scene_image,
                        bbox=bbox
                    )
                async with self.semaphore:
                    embedding = await asyncio.to_thread(
                        self.gemini_service.embed_image, crop_image
                    )
                similar_skus = await self.similar_sku_service.find_similar_skus(embedding)

                candidates = []
                for sku in similar_skus:
                    image_bytes = await asyncio.to_thread(
                        read_sku_image_bytes, sku.image_url
                    )
                    if image_bytes is None:
                        continue
                    candidates.append(
                        ScoringCandidate(
                            sku_code=sku.sku_code,
                            image_bytes=image_bytes,
                        )
                    )
                    
                objects.append({
                    "crop_index": idx,
                    "bbox": bbox,
                    "similar_skus": similar_skus,
                    "scoring_crop": ScoringCrop(
                        crop_index=idx,
                        crop_image_bytes=parse_image_to_bytes(crop_image),
                        candidates=candidates,
                    ),
                })
        scoring_crops = [
            obj["scoring_crop"]
            for obj in objects
            if obj["scoring_crop"].candidates
        ]
        score_result = RubricScoreResult()
        if scoring_crops:
            try:
                score_result = await asyncio.to_thread(
                    self.xai_scoring_service.score_all, scoring_crops
                )
            # 채점 실패로 추천 전체가 실패하지 않도록 폴백합니다.
            except Exception:
                _LOGGER.exception(
                    "루브릭 채점 실패, 임베딩 유사도로 대체합니다: "
                    "scene_image_id=%s",
                    scene_image_id,
                )

        return self._make_result(scene, objects, score_result)

    def _make_result(
            self,
            scene: SceneImage,
            objects: list[dict],
            score_result: RubricScoreResult,
    ) -> DetectionResult:
        """유사도 결과와 XAI 채점 결과를 합쳐 최종 응답을 만듭니다.

        Args:
            scene: 조회한 장면 이미지 엔티티입니다.
            objects: crop별 bbox와 similar_skus가 담긴 수집 결과입니다.
            score_result: XAI 1회 호출로 받은 전체 채점 결과입니다.

        Returns:
            탐지 객체별 SKU 후보와 XAI 판정이 담긴 결과입니다.
        """
        # 응답 순서가 요청 순서와 다를 수 있으므로 crop_index로 색인합니다.
        scores = {crop.crop_index: crop for crop in score_result.crops}

        detected_objects = []
        for item in objects:
            crop_score = scores.get(item["crop_index"])
            evaluations = (
                {e.sku_id: e for e in crop_score.evaluations}
                if crop_score
                else {}
            )

            sku_candidates = []
            for sku in item["similar_skus"]:
                evaluation = evaluations.get(sku.sku_code)
                if evaluation is not None:
                    similarity_score = evaluation.total_score
                    xai_result = evaluation.xai_result
                else:
                    similarity_score = max(
                        0, min(100, round(sku.similarity * 100))
                    )
                    xai_result = XaiResult(summary="XAI 판정 결과가 없습니다.")

                sku_candidates.append(
                    SkuCandidate(
                        sku_code=sku.sku_code,
                        product_name=sku.product_name,
                        category=sku.category or "",
                        sub_category=sku.sub_category or "",
                        attrs={
                            key: str(value)
                            for key, value in (sku.attributes or {}).items()
                        },
                        similarity_score=similarity_score,
                        matched_sku_image=MatchedSkuImage(
                            sku_image_id=sku.sku_image_id,
                            image_type=sku.image_type,
                            image_url=sku.image_url,
                        ),
                        xai_result=xai_result,
                    )
                )

            # 점수가 높은 후보를 앞에 둡니다.
            sku_candidates.sort(
                key=lambda candidate: candidate.similarity_score, reverse=True
            )

            detected_objects.append(
                DetectedObject(
                    object_index=item["crop_index"],
                    label=crop_score.label if crop_score else "",
                    bbox=BoundingBox(**item["bbox"]),
                    confidence=crop_score.confidence if crop_score else 0,
                    attrs=(
                        {a.key: a.value for a in crop_score.object_attrs}
                        if crop_score
                        else {}
                    ),
                    sku_candidates=sku_candidates,
                )
            )

        return DetectionResult(
            processing_status="DETECTED",
            scene_image=SceneImageInfo(
                scene_image_id=scene.scene_image_id,
                image_url=scene.image_url,
                origin_name=scene.origin_name,
                mime_type=scene.mime_type,
                file_size=scene.file_size,
                width_px=scene.width_px,
                height_px=scene.height_px,
            ),
            objects=detected_objects,
        )