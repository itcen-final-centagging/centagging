"""크롭과 SKU 후보 이미지를 루브릭으로 채점하는 서비스입니다."""

import asyncio
import logging
import string
import typing

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.core import config, genai_client
from app.schemas.tagging import DetectedObject, XaiResult
from app.services.gemini_service import (
    GeminiApiError,
    GeminiConfigurationError,
    GeminiResponseInvalidError,
)
from app.services.image_processing_service import (
    CroppedObject,
    read_sku_image_bytes,
)
from app.services.xai_prompt import XAI_PROMPT

_LOGGER = logging.getLogger(__name__)


class ScoringCandidate(BaseModel):
    """채점 대상 SKU 후보 1건입니다."""

    sku_code: str
    image_bytes: bytes


class ScoringCrop(BaseModel):
    """크롭 1건과 그 크롭에 붙는 SKU 후보들입니다."""

    crop_index: int
    crop_image_bytes: bytes
    candidates: list[ScoringCandidate] = Field(default_factory=list)


class SkuEvaluation(BaseModel):
    sku_id: str
    status: typing.Literal["Matched", "Rejected"]
    total_score: int = Field(ge=0, le=100)
    xai_result: XaiResult


class ObjectAttribute(BaseModel):
    key: str
    value: str


class CropScore(BaseModel):
    crop_index: int
    label: str = ""
    confidence: int = Field(default=0, ge=0, le=100)
    object_attrs: list[ObjectAttribute] = Field(default_factory=list)
    evaluations: list[SkuEvaluation] = Field(default_factory=list)


class RubricScoreResult(BaseModel):
    crops: list[CropScore] = Field(default_factory=list)


class XaiScoringService:
    """모든 크롭·후보를 한 번의 VLM 요청으로 채점하는 서비스입니다."""

    def __init__(self, settings: config.Settings) -> None:
        self.settings = settings
        self._client: genai.Client | None = None

    def _get_client(self) -> genai.Client:
        if not genai_client.is_configured(self.settings):
            raise GeminiConfigurationError(
                "Google Gen AI 인증 설정이 누락되었습니다."
            )
        if self._client is None:
            self._client = genai_client.create_client(self.settings)
        return self._client

    async def enrich_detected_objects(
        self,
        crops: list[CroppedObject],
        detected_objects: list[DetectedObject],
    ) -> list[DetectedObject]:
        """탐지 객체에 라벨·속성·XAI 판정을 채워 넣습니다.

        채점에 실패해도 임베딩 유사도 기반 응답이 유지되도록, 예외를
        기록만 하고 입력 객체를 그대로 돌려줍니다.

        Args:
            crops: 크롭 이미지 바이트를 담은 크롭 목록입니다.
            detected_objects: SKU 후보까지 채워진 탐지 객체 목록입니다.

        Returns:
            XAI 결과가 반영된 탐지 객체 목록입니다.
        """
        crop_bytes = {crop.crop_index: crop.image_bytes for crop in crops}
        scoring_crops = await self._build_scoring_crops(
            crop_bytes, detected_objects
        )
        if not scoring_crops:
            return detected_objects

        try:
            score_result = await asyncio.to_thread(
                self.score_all, scoring_crops
            )
        # 채점 실패로 추천 전체가 실패하지 않도록 폴백합니다.
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("루브릭 채점 실패, 임베딩 유사도로 대체합니다.")
            return detected_objects

        # 응답 순서가 요청 순서와 다를 수 있으므로 crop_index로 색인합니다.
        scores = {crop.crop_index: crop for crop in score_result.crops}
        for detected in detected_objects:
            crop_score = scores.get(detected.object_index)
            if crop_score is not None:
                self._apply_crop_score(detected, crop_score)

        return detected_objects

    async def _build_scoring_crops(
        self,
        crop_bytes: dict[int, bytes],
        detected_objects: list[DetectedObject],
    ) -> list[ScoringCrop]:
        """탐지 객체의 SKU 이미지를 읽어 채점 입력을 만듭니다.

        Args:
            crop_bytes: crop_index별 크롭 JPEG 바이트입니다.
            detected_objects: SKU 후보가 채워진 탐지 객체 목록입니다.

        Returns:
            후보 이미지를 읽을 수 있었던 크롭만 담은 채점 입력입니다.
        """
        scoring_crops = []
        for detected in detected_objects:
            if detected.object_index not in crop_bytes:
                continue

            image_bytes_list = await asyncio.gather(
                *(
                    asyncio.to_thread(
                        read_sku_image_bytes,
                        candidate.matched_sku_image.image_url,
                        self.settings.sku_image_root,
                    )
                    for candidate in detected.sku_candidates
                )
            )
            candidates = [
                ScoringCandidate(
                    sku_code=candidate.sku_code,
                    image_bytes=image_bytes,
                )
                for candidate, image_bytes in zip(
                    detected.sku_candidates, image_bytes_list
                )
                # 이미지를 못 읽은 후보는 채점 대상에서만 제외합니다.
                if image_bytes is not None
            ]
            if not candidates:
                continue

            scoring_crops.append(
                ScoringCrop(
                    crop_index=detected.object_index,
                    crop_image_bytes=crop_bytes[detected.object_index],
                    candidates=candidates,
                )
            )
        return scoring_crops

    @staticmethod
    def _apply_crop_score(
        detected: DetectedObject,
        crop_score: CropScore,
    ) -> None:
        """채점 결과를 탐지 객체 1건에 반영하고 후보를 재정렬합니다.

        Args:
            detected: 채점 결과를 반영할 탐지 객체입니다.
            crop_score: 해당 크롭의 루브릭 채점 결과입니다.
        """
        detected.label = crop_score.label
        detected.confidence = crop_score.confidence
        detected.attrs = {
            attribute.key: attribute.value
            for attribute in crop_score.object_attrs
        }

        evaluations = {
            evaluation.sku_id: evaluation
            for evaluation in crop_score.evaluations
        }
        for candidate in detected.sku_candidates:
            evaluation = evaluations.get(candidate.sku_code)
            if evaluation is None:
                continue
            candidate.similarity_score = evaluation.total_score
            candidate.xai_result = evaluation.xai_result

        # 점수가 높은 후보를 앞에 둡니다.
        detected.sku_candidates.sort(
            key=lambda candidate: candidate.similarity_score, reverse=True
        )

    def score_all(self, crops: list[ScoringCrop]) -> RubricScoreResult:
        """모든 크롭과 SKU 후보를 단 한 번의 요청으로 채점합니다.

        Args:
            crops: 크롭별 이미지와 SKU 후보 이미지 묶음입니다.

        Returns:
            crop_index 기준으로 정렬되지 않을 수 있는 전체 채점 결과입니다.

        Raises:
            ValueError: 채점 대상이 하나도 없는 경우입니다.
            GeminiConfigurationError: Google Gen AI 인증 설정이 없는
                경우입니다.
            GeminiResponseInvalidError: 응답이 비어 있는 경우입니다.
            GeminiApiError: SDK 호출이 실패한 경우입니다.
        """
        targets = [crop for crop in crops if crop.candidates]
        if not targets:
            raise ValueError("채점할 SKU 후보 이미지가 없습니다.")

        client = self._get_client()

        crop_summary = "\n".join(
            f"    - crop {crop.crop_index}: "
            f"SKU 후보 {[c.sku_code for c in crop.candidates]}"
            for crop in targets
        )
        prompt = string.Template(XAI_PROMPT).substitute(
            crop_count=len(targets),
            crop_summary=crop_summary,
        )

        contents: list[typing.Any] = [prompt]
        for crop in targets:
            contents += [
                f"\n=== TARGET CROP: {crop.crop_index} ===",
                types.Part.from_bytes(
                    data=crop.crop_image_bytes, mime_type="image/jpeg"
                ),
            ]
            for candidate in crop.candidates:
                contents += [
                    f"[{crop.crop_index}] CANDIDATE SKU: {candidate.sku_code}",
                    types.Part.from_bytes(
                        data=candidate.image_bytes, mime_type="image/jpeg"
                    ),
                ]

        try:
            response = client.models.generate_content(
                model=self.settings.gemini_vlm_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=RubricScoreResult,
                ),
            )
            if not response.text:
                raise GeminiResponseInvalidError(
                    "Gemini 루브릭 채점 응답이 비어 있습니다."
                )
            return RubricScoreResult.model_validate_json(response.text)
        except GeminiResponseInvalidError:
            raise
        except Exception as error:
            raise GeminiApiError(
                "Gemini 루브릭 채점 요청에 실패했습니다."
            ) from error
