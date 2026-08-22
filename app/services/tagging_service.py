"""장면 이미지 태깅 흐름을 단계별로 조립하는 오케스트레이션 서비스입니다."""

import asyncio
import dataclasses
import logging
import pathlib

from PIL import Image
from sqlalchemy.ext import asyncio as sqlalchemy_async

from app.core.config import Settings
from app.models.scene_image import SceneImage
from app.repositories.scene_image_repository import get_scene_image
from app.schemas.furniture_attribute import FurnitureAttributeResult
from app.schemas.tagging import (
    DetectedObject,
    DetectionResult,
    EditedSceneObject,
    SceneImageInfo,
    VlmMood,
)
from app.services import sku_search_service
from app.services.gemini_service import GeminiService
from app.services.image_processing_service import (
    CroppedObject,
    crop_scene_objects,
    parse_image_to_bytes,
    read_sku_image_bytes,
)
from app.services.image_preprocessing_service import preprocess_for_embedding
from app.services.fused_metadata import build_metadata_text
from app.services.similar_sku_service import (
    FusedEmbeddingInput,
    SimilarSkuService,
)
from app.services.xai_scoring_service import (
    ScoringCandidate,
    ScoringCrop,
    XaiObjectResult,
    XaiScoringService,
)

DETECTED_STATUS = "DETECTED"
ATTRIBUTE_EXTRACTION_CONCURRENCY = 3

_LOGGER = logging.getLogger(__name__)


class SkuNotFoundError(RuntimeError):
    """검색으로 선택한 SKU 코드가 카탈로그에 없는 경우입니다."""


# 단일 태깅 유스케이스를 제공하는 오케스트레이터입니다.
class TaggingService:  # pylint: disable=too-few-public-methods
    """crop → 유사 SKU 탐색 → XAI 순으로 태깅 응답을 만드는 서비스입니다."""

    def __init__(
        self,
        session: sqlalchemy_async.AsyncSession,
        settings: Settings,
        gemini_service: GeminiService,
        similar_sku_service: SimilarSkuService,
        xai_scoring_service: XaiScoringService,
    ) -> None:
        """오케스트레이션에 필요한 세션과 단계별 서비스를 주입받습니다.

        Args:
            session: 요청 범위의 비동기 SQLAlchemy 세션입니다.
            settings: 이미지 저장소 경로가 담긴 애플리케이션 설정입니다.
            gemini_service: 객체 속성 추출과 Gemini API 호출을 담당하는 서비스입니다.
            similar_sku_service: 임베딩과 유사 SKU 탐색 담당 서비스입니다.
            xai_scoring_service: XAI 근거 산출 담당 서비스입니다.
        """
        self.session = session
        self.settings = settings
        self.gemini_service = gemini_service
        self.similar_sku_service = similar_sku_service
        self.xai_scoring_service = xai_scoring_service
        self._attribute_semaphore = asyncio.Semaphore(
            ATTRIBUTE_EXTRACTION_CONCURRENCY
        )

    async def get_sku_candidates(
        self,
        scene_image_id: int,
        object_idxs: list[int] | None = None,
        objects: list[EditedSceneObject] | None = None,
    ) -> DetectionResult:
        """장면 이미지 1건의 유사 SKU 추천 결과를 만듭니다.

        연출 이미지 crop → 임베딩 및 유사 SKU 탐색 → XAI 근거 산출
        순서로 응답 객체를 단계마다 채워 나갑니다.

        Args:
            scene_image_id: 조회할 장면 이미지 ID입니다.
            object_idxs: 조회할 탐지 객체 인덱스 목록입니다. None이면
                전체 객체를 조회합니다.

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

        # 0) 프론트에서 전달한 객체 목록 배열
        object_metadata = (
            [item.model_dump() for item in objects]
            if objects is not None
            else list(scene.object_metadata)
        )

        category_by_idx = {
            int(item.get("object_idx", index)): item.get("category", "")
            for index, item in enumerate(object_metadata)
        }

        # 1) 연출 이미지 crop
        crops = await asyncio.to_thread(
            crop_scene_objects,
            self._resolve_image_path(scene),
            object_metadata,
        )
        if object_idxs is not None:
            requested_idxs = set(object_idxs)
            crops = [
                crop for crop in crops if crop.crop_index in requested_idxs
            ]

        preprocessed_images = await self._preprocess_crops(crops)
        attributes_by_idx = await self._extract_attributes(
            crops,
            category_by_idx,
            preprocessed_images,
        )
        fused_inputs = self._build_fused_embedding_inputs(
            crops,
            category_by_idx,
            attributes_by_idx,
            preprocessed_images,
        )

        # 2) 임베딩 및 유사 SKU 탐색
        result.objects = await self.similar_sku_service.build_detected_objects(
            crops,
            fused_inputs,
        )

        # 3) XAI 근거 산출
        xai_crops = self._build_xai_crops(crops, preprocessed_images)
        xai_results = await self.xai_scoring_service.score_detected_objects(
            xai_crops, result.objects
        )
        self._apply_xai_results(result.objects, xai_results)

        # 4) 추출 속성 매핑
        for detected in result.objects:
            detected.category = category_by_idx.get(
                detected.object_idx,
                detected.category,
            )

            attribute_result = attributes_by_idx.get(detected.object_idx)

            detected.sub_category = (
                attribute_result.sub_category
                if attribute_result is not None
                else None
            )

            if attribute_result is not None:
                detected.attrs = attribute_result.attributes

        return result

    async def score_search_selected_sku(
        self,
        scene_image_id: int,
        object_edit: EditedSceneObject,
        sku_code: str,
    ) -> VlmMood:
        """전체 카탈로그 검색으로 선택한 SKU의 공간 분위기·스타일 태그를 계산합니다.

        AI 추천 흐름과 같은 XAI 채점(``XaiScoringService``)을 크롭 1건 ×
        후보 1건으로 좁혀 실행하고, 거기서 얻은 ``vlm_mood``만 돌려줍니다.
        검색으로 확정한 결과는 순위 근거(xai_result)를 저장할 수 없으므로
        (``SkuMatching.validate_source_consistency``) 점수·criteria는
        쓰지 않고 버립니다.

        VLM 채점 자체가 실패해도 SKU 선택 흐름을 막지 않도록, 크롭·SKU
        이미지를 읽지 못했거나 채점이 실패하면 빈 VlmMood를 반환합니다.

        Args:
            scene_image_id: 크롭을 잘라낼 연출 이미지 ID입니다.
            object_edit: 크롭 대상 객체의 바운딩 박스·카테고리입니다.
            sku_code: 검색으로 선택한 SKU 코드입니다.

        Returns:
            VLM이 크롭에서 읽어낸 공간 분위기 요약과 스타일 태그입니다.
            채점에 실패하면 빈 VlmMood입니다.

        Raises:
            SceneImageNotFoundError: 장면 이미지가 없는 경우입니다.
            InvalidImageError: 장면 원본 이미지를 열 수 없는 경우입니다.
            SkuNotFoundError: sku_code가 카탈로그에 없는 경우입니다.
        """
        scene = await get_scene_image(self.session, scene_image_id)

        sku_image = await sku_search_service.get_sku_image_for_scoring(
            self.session, sku_code
        )
        if sku_image is None:
            raise SkuNotFoundError(sku_code)

        crops = await asyncio.to_thread(
            crop_scene_objects,
            self._resolve_image_path(scene),
            [object_edit.model_dump()],
        )
        crop = next(
            (
                item
                for item in crops
                if item.crop_index == object_edit.object_idx
            ),
            None,
        )
        if crop is None:
            return VlmMood()

        candidate_image_bytes = await asyncio.to_thread(
            read_sku_image_bytes,
            sku_image.image_url,
            self.settings.sku_image_root,
            self.settings.image_storage_root,
        )
        if candidate_image_bytes is None:
            _LOGGER.warning(
                "검색 SKU 이미지를 읽지 못해 VLM 분위기 계산을 건너뜁니다: "
                "sku_code=%s",
                sku_code,
            )
            return VlmMood()

        scoring_crop = ScoringCrop(
            crop_index=crop.crop_index,
            crop_image_bytes=crop.image_bytes,
            candidates=[
                ScoringCandidate(
                    sku_code=sku_code, image_bytes=candidate_image_bytes
                )
            ],
        )

        try:
            score_result = await asyncio.to_thread(
                self.xai_scoring_service.score_all, [scoring_crop]
            )
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception(
                "검색 SKU VLM 분위기 채점 실패, 빈 값으로 대체합니다: "
                "sku_code=%s",
                sku_code,
            )
            return VlmMood()

        for crop_score in score_result.crops:
            for evaluation in crop_score.evaluations:
                if evaluation.sku_id == sku_code:
                    return evaluation.xai_result.vlm_mood
        return VlmMood()

    async def _extract_attributes(
        self,
        crops: list[CroppedObject],
        category_by_idx: dict[int, str],
        preprocessed_images: dict[int, Image.Image],
    ) -> dict[int, FurnitureAttributeResult | None]:
        """보정 크롭별 카테고리 규격에 맞춰 속성을 추출합니다."""
        extraction_targets = []
        attributes_by_idx: dict[int, FurnitureAttributeResult | None] = {}
        for crop in crops:
            category = category_by_idx.get(crop.crop_index, "")
            if not category:
                attributes_by_idx[crop.crop_index] = None
                continue
            preprocessed_image = preprocessed_images.get(crop.crop_index)
            if preprocessed_image is None:
                attributes_by_idx[crop.crop_index] = None
                continue
            extraction_targets.append((crop, category, preprocessed_image))

        extraction_results = await asyncio.gather(
            *(
                self._extract_attributes_for_crop(crop, category, image)
                for crop, category, image in extraction_targets
            )
        )
        attributes_by_idx.update(
            (crop.crop_index, result)
            for (crop, _, _), result in zip(
                extraction_targets, extraction_results
            )
        )
        return attributes_by_idx

    async def _extract_attributes_for_crop(
        self,
        crop: CroppedObject,
        category: str,
        image: Image.Image,
    ) -> FurnitureAttributeResult:
        """보정 크롭의 속성 추출 Vertex AI 요청 수를 제한합니다."""
        async with self._attribute_semaphore:
            return await asyncio.to_thread(
                self.gemini_service.extract_furniture_attributes,
                image,
                category,
            )

    async def _preprocess_crops(
        self,
        crops: list[CroppedObject],
    ) -> dict[int, Image.Image]:
        """속성 추출과 융합 임베딩에서 공유할 크롭 보정 결과를 만듭니다."""
        processed = await asyncio.gather(
            *(
                asyncio.to_thread(
                    preprocess_for_embedding,
                    crop.image,
                    self.settings,
                )
                for crop in crops
            )
        )
        return {
            crop.crop_index: result.image
            for crop, result in zip(crops, processed)
        }

    @staticmethod
    def _build_fused_embedding_inputs(
        crops: list[CroppedObject],
        category_by_idx: dict[int, str],
        attributes_by_idx: dict[int, FurnitureAttributeResult | None],
        preprocessed_images: dict[int, Image.Image],
    ) -> dict[int, FusedEmbeddingInput]:
        """보정 크롭과 추출 속성을 SKU와 동일한 입력 규칙으로 조립합니다."""
        fused_inputs = {}
        for crop in crops:
            image = preprocessed_images.get(crop.crop_index)
            if image is None:
                continue
            attributes = attributes_by_idx.get(crop.crop_index)
            fused_inputs[crop.crop_index] = FusedEmbeddingInput(
                image=image,
                metadata_text=build_metadata_text(
                    category=category_by_idx.get(crop.crop_index),
                    sub_category=(
                        attributes.sub_category
                        if attributes is not None
                        else None
                    ),
                    attributes=(
                        attributes.attributes
                        if attributes is not None
                        else None
                    ),
                ),
            )
        return fused_inputs

    @staticmethod
    def _build_xai_crops(
        crops: list[CroppedObject],
        preprocessed_images: dict[int, Image.Image],
    ) -> list[CroppedObject]:
        """보정 Crop을 XAI 요청용 이미지·JPEG 바이트로 재구성합니다.

        전처리 결과는 파일로 저장하지 않고, Gemini 요청 직전에만 JPEG 바이트로
        직렬화합니다. 보정 결과가 없는 객체는 XAI 채점 대상에서 제외합니다.
        """
        xai_crops = []
        for crop in crops:
            image = preprocessed_images.get(crop.crop_index)
            if image is None:
                continue
            xai_crops.append(
                dataclasses.replace(
                    crop,
                    image=image,
                    image_bytes=parse_image_to_bytes(image),
                )
            )
        return xai_crops

    @staticmethod
    def _apply_xai_results(
        detected_objects: list[DetectedObject],
        xai_results: dict[int, XaiObjectResult],
    ) -> None:
        """XAI 결과 중 XAI 속성과 후보 평가만 탐지 객체에 반영합니다."""
        for detected in detected_objects:
            xai_result = xai_results.get(detected.object_idx)
            if xai_result is None:
                continue

            detected.xai_attrs = xai_result.xai_attrs
            evaluations = {
                evaluation.sku_id: evaluation
                for evaluation in xai_result.evaluations
            }

            for candidate in detected.sku_candidates:
                evaluation = evaluations.get(candidate.sku_code)
                if evaluation is None:
                    continue
                candidate.similarity_score = evaluation.total_score
                candidate.xai_result = evaluation.xai_result

            detected.sku_candidates.sort(
                key=lambda candidate: candidate.similarity_score,
                reverse=True,
            )

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
