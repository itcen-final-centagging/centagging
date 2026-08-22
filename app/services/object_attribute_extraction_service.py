"""크롭 이미지의 가구 속성을 추출하는 공용 서비스입니다."""

import asyncio
from collections.abc import Mapping

from PIL import Image

from app.core.config import Settings
from app.schemas.furniture_attribute import FurnitureAttributeResult
from app.services.gemini_service import GeminiService
from app.services.image_preprocessing_service import preprocess_for_embedding
from app.services.image_processing_service import CroppedObject

ATTRIBUTE_EXTRACTION_CONCURRENCY = 2


class ObjectAttributeExtractionService:
    """탐지와 SKU 추천 단계에서 공통으로 속성을 추출합니다."""

    def __init__(
        self,
        settings: Settings,
        gemini_service: GeminiService,
    ) -> None:
        self._settings = settings
        self._gemini_service = gemini_service
        self._semaphore = asyncio.Semaphore(
            ATTRIBUTE_EXTRACTION_CONCURRENCY,
        )

    async def preprocess_crops(
        self,
        crops: list[CroppedObject],
    ) -> dict[int, Image.Image]:
        """속성 추출과 임베딩에서 공유할 크롭 전처리 결과를 만듭니다."""
        processed = await asyncio.gather(
            *(
                asyncio.to_thread(
                    preprocess_for_embedding,
                    crop.image,
                    self._settings,
                )
                for crop in crops
            )
        )
        return {
            crop.crop_index: result.image
            for crop, result in zip(crops, processed)
        }

    async def extract_for_crops(
        self,
        crops: list[CroppedObject],
        category_by_idx: Mapping[int, str],
        preprocessed_images: Mapping[int, Image.Image] | None = None,
    ) -> dict[int, FurnitureAttributeResult | None]:
        """객체별 crop과 category로 속성을 추출합니다."""
        if preprocessed_images is None:
            preprocessed_images = await self.preprocess_crops(crops)

        attributes_by_idx: dict[int, FurnitureAttributeResult | None] = {}
        extraction_targets: list[tuple[CroppedObject, str, Image.Image]] = []

        for crop in crops:
            category = category_by_idx.get(crop.crop_index, "")
            image = preprocessed_images.get(crop.crop_index)

            if not category or image is None:
                attributes_by_idx[crop.crop_index] = None
                continue

            extraction_targets.append((crop, category, image))

        results = await asyncio.gather(
            *(
                self._extract_for_crop(crop, category, image)
                for crop, category, image in extraction_targets
            )
        )

        attributes_by_idx.update(
            (crop.crop_index, result)
            for (crop, _, _), result in zip(extraction_targets, results)
        )
        return attributes_by_idx

    async def _extract_for_crop(
        self,
        crop: CroppedObject,
        category: str,
        image: Image.Image,
    ) -> FurnitureAttributeResult:
        """동시 호출 수를 제한해 crop 1건의 속성을 추출합니다."""
        async with self._semaphore:
            return await asyncio.to_thread(
                self._gemini_service.extract_furniture_attributes,
                image,
                category,
            )
