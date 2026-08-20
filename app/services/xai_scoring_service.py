"""크롭과 SKU 후보 이미지를 루브릭으로 채점하는 서비스입니다."""

import asyncio
import logging
import string
import typing

from google import genai
from google.genai import errors, types
from pydantic import BaseModel, Field

from app.core import config, genai_client
from app.schemas.tagging import (
    DetectedObject,
    VlmMood,
    XaiCriterion,
    XaiResult,
)
from app.services.gemini_service import (
    GeminiApiError,
    GeminiConfigurationError,
    GeminiRateLimitError,
    GeminiResponseInvalidError,
)
from app.services.image_processing_service import (
    CroppedObject,
    read_sku_image_bytes,
)
from app.services.prompt.xai_prompt.xai_prompt import XAI_PROMPT

_LOGGER = logging.getLogger(__name__)

XAI_CONCURRENCY = 5

THINKING_BUDGET = 0

class ScoringCandidate(BaseModel):
    """채점 대상 SKU 후보 1건입니다."""

    sku_code: str
    image_bytes: bytes


class ScoringCrop(BaseModel):
    """크롭 1건과 그 크롭에 붙는 SKU 후보들입니다."""

    crop_index: int
    crop_image_bytes: bytes
    candidates: list[ScoringCandidate] = Field(default_factory=list)


class GeminiXaiResult(BaseModel):
    """Gemini response-only XAI result without dynamic dictionaries."""

    summary: str
    criteria: list[XaiCriterion] = Field(default_factory=list)
    vlm_mood: VlmMood = Field(default_factory=VlmMood)


class SkuEvaluation(BaseModel):
    """Gemini가 반환한 SKU 후보 1건의 루브릭 평가입니다."""

    sku_id: str
    status: typing.Literal["Matched", "Rejected"]
    total_score: int = Field(ge=0, le=100)
    xai_result: GeminiXaiResult


class ObjectAttribute(BaseModel):
    """Gemini가 추출한 객체 속성 키와 값입니다."""

    key: str
    value: str


class ResolvedSkuEvaluation(BaseModel):
    """Gemini 응답을 애플리케이션 XAI 계약으로 변환한 SKU 평가입니다."""

    sku_id: str
    status: typing.Literal["Matched", "Rejected"]
    total_score: int = Field(ge=0, le=100)
    xai_result: XaiResult


class CropScore(BaseModel):
    """크롭 1건의 객체 속성과 SKU 후보 평가 결과입니다."""

    crop_index: int
    label: str = ""
    confidence: int = Field(default=0, ge=0, le=100)
    object_attrs: list[ObjectAttribute] = Field(default_factory=list)
    evaluations: list[SkuEvaluation] = Field(default_factory=list)


class XaiObjectResult(BaseModel):
    """객체 단위 XAI 결과입니다."""

    object_idx: int
    xai_category: str = ""
    xai_confidence: int = Field(default=0, ge=0, le=100)
    xai_attrs: dict[str, str] = Field(default_factory=dict)
    evaluations: list[ResolvedSkuEvaluation] = Field(default_factory=list)


class RubricScoreResult(BaseModel):
    """한 번의 Gemini 채점 요청으로 받은 전체 크롭 결과입니다."""

    crops: list[CropScore] = Field(default_factory=list)


class XaiScoringService:
    """크롭 단위 VLM 요청을 동시에 보내 루브릭으로 채점하는 서비스입니다."""

    def __init__(self, settings: config.Settings) -> None:
        """Gemini 설정으로 XAI 채점기를 초기화합니다.

        Args:
            settings: Gemini 모델과 이미지 저장소 설정입니다.
        """
        self.settings = settings
        self._client: genai.Client | None = None
        self._score_semaphore = asyncio.Semaphore(XAI_CONCURRENCY)

    def _get_client(self) -> genai.Client:
        if not genai_client.is_configured(self.settings):
            raise GeminiConfigurationError(
                "Google Gen AI 인증 설정이 누락되었습니다."
            )
        if self._client is None:
            self._client = genai_client.create_client(self.settings)
        return self._client

    async def score_detected_objects(
        self,
        crops: list[CroppedObject],
        detected_objects: list[DetectedObject],
    ) -> dict[int, XaiObjectResult]:
        """탐지 객체별 XAI 결과를 계산해 반환합니다.

        크롭마다 별도의 채점 요청을 동시에 보냅니다. 채점에 실패한 크롭은
        임베딩 유사도 기반 후보를 그대로 유지하며, 한 크롭의 실패가 다른
        크롭의 결과에 영향을 주지 않습니다.

        Args:
            crops: 크롭 이미지 바이트를 담은 크롭 목록입니다.
            detected_objects: SKU 후보까지 채워진 탐지 객체 목록입니다.

        Returns:
            object_idx를 키로 하는 객체별 XAI 결과입니다.
        """
        crop_bytes = {crop.crop_index: crop.image_bytes for crop in crops}
        scoring_crops = await self._build_scoring_crops(
            crop_bytes, detected_objects
        )
        if not scoring_crops:
            _LOGGER.warning(
                "XAI 채점 입력을 만들지 못했습니다. object_idxs=%s",
                [item.object_idx for item in detected_objects],
            )
            return {}

        crop_scores = await self._score_crops_concurrently(scoring_crops)
        if not crop_scores:
            return {}

        # 응답 순서가 요청 순서와 다를 수 있으므로 crop_index로 색인합니다.
        scores = {crop.crop_index: crop for crop in crop_scores}
        requested_indexes = {item.object_idx for item in detected_objects}
        returned_indexes = set(scores)
        missing_indexes = requested_indexes - returned_indexes
        unexpected_indexes = returned_indexes - requested_indexes

        if missing_indexes or unexpected_indexes:
            _LOGGER.warning(
                "XAI crop_index 불일치: requested=%s returned=%s",
                sorted(requested_indexes),
                sorted(returned_indexes),
            )

        return {
            crop_index: self._to_xai_object_result(crop_score)
            for crop_index, crop_score in scores.items()
            if crop_index in requested_indexes
        }

    async def _score_crops_concurrently(
        self,
        scoring_crops: list[ScoringCrop],
    ) -> list[CropScore]:
        """크롭별 채점 요청을 동시에 보내고 성공한 결과만 모읍니다.

        Args:
            scoring_crops: 크롭별 이미지와 SKU 후보 이미지 묶음입니다.

        Returns:
            채점에 성공한 크롭의 결과 목록입니다.
        """
        results = await asyncio.gather(
            *(self._score_one_crop(crop) for crop in scoring_crops)
        )
        return [crop_score for result in results for crop_score in result]

    async def _score_one_crop(self, crop: ScoringCrop) -> list[CropScore]:
        """크롭 1건을 채점합니다. 동시 호출 수를 세마포어로 제한합니다.

        크롭 1건의 실패가 나머지 크롭 결과까지 없애지 않도록, 예외는
        기록만 하고 빈 목록으로 폴백합니다.

        Args:
            crop: 채점할 크롭과 그 SKU 후보 묶음입니다.

        Returns:
            채점 결과이며, 실패하면 빈 목록입니다.
        """
        async with self._score_semaphore:
            try:
                score_result = await asyncio.to_thread(self.score_all, [crop])
            except GeminiRateLimitError:
                _LOGGER.warning(
                    "Gemini 요청 한도 초과, crop_index=%s는 "
                    "임베딩 유사도로 대체합니다.",
                    crop.crop_index,
                )
                return []
            # 채점 실패로 추천 전체가 실패하지 않도록 폴백합니다.
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception(
                    "루브릭 채점 실패, crop_index=%s는 "
                    "임베딩 유사도로 대체합니다.",
                    crop.crop_index,
                )
                return []

        return self._align_crop_index(crop, list(score_result.crops))

    @staticmethod
    def _align_crop_index(
        crop: ScoringCrop,
        crop_scores: list[CropScore],
    ) -> list[CropScore]:
        """단일 크롭 응답의 crop_index를 요청 값으로 맞춥니다.

        요청에 크롭이 하나뿐이면 결과의 소속이 명확하므로, 모델이 0부터
        새로 매겨 돌려주더라도 요청한 인덱스로 교정합니다. 교정하지 않으면
        인덱스 불일치로 정상 채점 결과가 버려집니다.

        Args:
            crop: 채점을 요청한 크롭입니다.
            crop_scores: 모델이 돌려준 크롭 결과 목록입니다.

        Returns:
            crop_index를 요청 값에 맞춘 크롭 결과 목록입니다.
        """
        if len(crop_scores) != 1:
            return crop_scores

        crop_score = crop_scores[0]
        if crop_score.crop_index != crop.crop_index:
            _LOGGER.warning(
                "XAI 응답 crop_index를 교정합니다: returned=%s requested=%s",
                crop_score.crop_index,
                crop.crop_index,
            )
            crop_score.crop_index = crop.crop_index
        return crop_scores

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
            if detected.object_idx not in crop_bytes:
                continue

            image_bytes_list = await asyncio.gather(
                *(
                    asyncio.to_thread(
                        read_sku_image_bytes,
                        candidate.matched_sku_image.image_url,
                        self.settings.sku_image_root,
                        self.settings.image_storage_root,
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
                    crop_index=detected.object_idx,
                    crop_image_bytes=crop_bytes[detected.object_idx],
                    candidates=candidates,
                )
            )
        return scoring_crops

    @staticmethod
    def _to_xai_object_result(
        crop_score: CropScore,
    ) -> XaiObjectResult:
        xai_attrs = {
            attribute.key: attribute.value
            for attribute in crop_score.object_attrs
        }
        return XaiObjectResult(
            object_idx=crop_score.crop_index,
            xai_category=crop_score.label,
            xai_confidence=crop_score.confidence,
            xai_attrs=xai_attrs,
            evaluations=[
                ResolvedSkuEvaluation(
                    sku_id=evaluation.sku_id,
                    status=evaluation.status,
                    total_score=evaluation.total_score,
                    xai_result=XaiResult(
                        summary=evaluation.xai_result.summary,
                        criteria=evaluation.xai_result.criteria,
                        vlm_mood=evaluation.xai_result.vlm_mood,
                        xai_attrs=xai_attrs,
                    ),
                )
                for evaluation in crop_score.evaluations
            ],
        )

    def score_all(self, crops: list[ScoringCrop]) -> RubricScoreResult:
        """전달받은 크롭과 SKU 후보를 한 번의 요청으로 채점합니다.

        평소에는 ``_score_one_crop``이 크롭 1건씩 넘겨 호출하지만, 여러
        크롭을 한 번에 채점하는 호출도 그대로 지원합니다.

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
                    thinking_config=types.ThinkingConfig(
                        thinking_budget=THINKING_BUDGET
                    ),
                ),
            )
            if not response.text:
                raise GeminiResponseInvalidError(
                    "Gemini 루브릭 채점 응답이 비어 있습니다."
                )

            score_result = RubricScoreResult.model_validate_json(response.text)
            if not score_result.crops:
                raise GeminiResponseInvalidError(
                    "Gemini 루브릭 채점 결과에 crops가 없습니다."
                )
            return score_result

        except GeminiResponseInvalidError:
            raise
        except errors.ClientError as error:
            if getattr(error, "code", None) == 429:
                raise GeminiRateLimitError(
                    "Gemini 루브릭 채점 요청 한도를 초과했습니다."
                ) from error
            raise GeminiApiError(
                "Gemini 루브릭 채점 요청에 실패했습니다."
            ) from error
        except Exception as error:
            raise GeminiApiError(
                "Gemini 루브릭 채점 요청에 실패했습니다."
            ) from error
