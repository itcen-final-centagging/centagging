"""크롭과 SKU 후보 이미지를 비교해 XAI 근거를 만드는 서비스입니다.

crop의 카테고리에 정의된 메타데이터를 항목별로 비교해 일치/불일치/판단
불가를 판정합니다. 응답 스키마는 ``MetadataScoreResult``입니다. 화면에
표시할 일치도는 XAI 판정 비율이 아니라 기존 임베딩 유사도를 사용하며,
후보를 응답에 반영하는 단계에서 채웁니다.

구조/색상/디테일/맥락 루브릭으로 100점을 매기던 v1·v2 채점 경로는
제거했습니다. 프롬프트 원문(``xai_prompt.py``, ``xai_prompt_v2.py``)만
참고용으로 남아 있으며 이 서비스는 더 이상 호출하지 않습니다.
"""

import asyncio
import collections.abc
import json
import logging
import typing

from google import genai
from google.genai import errors, types
from pydantic import BaseModel, Field

from app.core import catalog_spec, config, genai_client
from app.schemas.tagging import (
    DetectedObject,
    XaiCriterion,
    XaiCropReading,
    XaiResult,
)
from app.services.gemini_service import (
    GeminiApiError,
    GeminiConfigurationError,
    GeminiRateLimitError,
    GeminiResponseInvalidError,
)
from app.services.genai_retry import call_with_rate_limit_retry
from app.services.image_processing_service import (
    CroppedObject,
    read_sku_image_bytes,
)
from app.services.prompt.xai_prompt.xai_prompt_v3 import (
    build_comparison_block,
    build_xai_prompt,
)

_LOGGER = logging.getLogger(__name__)

XAI_CONCURRENCY = 3

THINKING_BUDGET = 0

# 재요청 후에도 모델 응답에서 누락된 항목에 붙이는 사용자용 근거입니다.
# 모델 내부 동작을 그대로 노출하지 않고 시각 정보 부족으로 안내합니다.
MISSING_VERDICT_COMMENT = "해당 항목을 충분히 비교하기 어려워 판단할 수 없습니다."
MISSING_READING_NOTE = "해당 항목의 시각 정보가 충분하지 않아 판단하기 어렵습니다."


class ScoringCandidate(BaseModel):
    """채점 대상 SKU 후보 1건입니다."""

    sku_code: str
    image_bytes: bytes
    # v3 프롬프트에 참고용으로 제시하는 SKU 카탈로그 메타데이터입니다.
    attrs: dict[str, str] = Field(default_factory=dict)


class ScoringCrop(BaseModel):
    """크롭 1건과 그 크롭에 붙는 SKU 후보들입니다."""

    crop_index: int
    crop_image_bytes: bytes
    # v3에서 비교 항목을 정하는 기준입니다. 비교 항목을 만들 수 없는
    # 카테고리면 해당 크롭은 v3 채점 대상에서 제외됩니다.
    category: str = ""
    candidates: list[ScoringCandidate] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 메타데이터 비교 응답 스키마
# ---------------------------------------------------------------------------


class GeminiCropReading(BaseModel):
    """crop 이미지에서 판독한 비교 항목 1건입니다."""

    key: str
    value: str = ""
    note: str = ""


class GeminiCandidateVerdict(BaseModel):
    """후보 1건에 대한 메타데이터 1건의 판정입니다."""

    key: str
    verdict: typing.Literal["MATCH", "MISMATCH", "UNKNOWN"]
    comment: str = ""


class MetadataXaiResult(BaseModel):
    """후보 1건의 총평과 항목별 판정입니다."""

    common: str = ""
    difference: str = ""
    verdicts: list[GeminiCandidateVerdict] = Field(default_factory=list)


class MetadataSkuEvaluation(BaseModel):
    """Gemini가 반환한 SKU 후보 1건의 메타데이터 비교 결과입니다."""

    sku_id: str
    status: typing.Literal["Matched", "Rejected"]
    xai_result: MetadataXaiResult


class MetadataCropScore(BaseModel):
    """크롭 1건의 판독값과 SKU 후보별 판정입니다."""

    crop_index: int
    crop_readings: list[GeminiCropReading] = Field(default_factory=list)
    evaluations: list[MetadataSkuEvaluation] = Field(default_factory=list)


class MetadataScoreResult(BaseModel):
    """한 번의 Gemini 비교 요청으로 받은 전체 크롭 결과입니다."""

    crops: list[MetadataCropScore] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 정규화된 결과
# ---------------------------------------------------------------------------


class ResolvedSkuEvaluation(BaseModel):
    """Gemini 응답을 애플리케이션 XAI 계약으로 변환한 SKU 평가입니다."""

    sku_id: str
    status: typing.Literal["Matched", "Rejected"]
    xai_result: XaiResult


class XaiObjectResult(BaseModel):
    """객체 단위 XAI 결과입니다."""

    object_idx: int
    xai_category: str = ""
    # 판독에 성공한 비교 항목만 담은 key/value입니다.
    xai_attrs: dict[str, str] = Field(default_factory=dict)
    # 비교 항목 정의와 crop 판독값입니다.
    readings: list[XaiCropReading] = Field(default_factory=list)
    evaluations: list[ResolvedSkuEvaluation] = Field(default_factory=list)


class XaiScoringService:
    """크롭 단위 VLM 요청을 동시에 보내 XAI 근거를 만드는 서비스입니다."""

    def __init__(self, settings: config.Settings) -> None:
        """Gemini 설정으로 XAI 판정기를 초기화합니다.

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
        category_by_idx: collections.abc.Mapping[int, str] | None = None,
    ) -> dict[int, XaiObjectResult]:
        """탐지 객체별 XAI 결과를 계산해 반환합니다.

        크롭마다 별도의 채점 요청을 동시에 보냅니다. 채점에 실패한 크롭은
        임베딩 유사도 기반 후보를 그대로 유지하며, 한 크롭의 실패가 다른
        크롭의 결과에 영향을 주지 않습니다.

        Args:
            crops: 크롭 이미지 바이트를 담은 크롭 목록입니다.
            detected_objects: SKU 후보까지 채워진 탐지 객체 목록입니다.
            category_by_idx: object_idx별 대분류입니다. v3에서 비교 항목을
                정하는 데 씁니다. 추천 흐름에서는 XAI가 속성 매핑보다 먼저
                실행되어 ``DetectedObject.category``가 아직 비어 있으므로,
                호출하는 쪽이 확정된 카테고리를 넘겨야 합니다.

        Returns:
            object_idx를 키로 하는 객체별 XAI 결과입니다.
        """
        crop_bytes = {crop.crop_index: crop.image_bytes for crop in crops}
        scoring_crops = await self._build_scoring_crops(
            crop_bytes, detected_objects, category_by_idx or {}
        )
        if not scoring_crops:
            _LOGGER.warning(
                "XAI 채점 입력을 만들지 못했습니다. object_idxs=%s",
                [item.object_idx for item in detected_objects],
            )
            return {}

        categories = {crop.crop_index: crop.category for crop in scoring_crops}
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
            crop_index: self._to_xai_object_result(
                crop_score, categories.get(crop_index, "")
            )
            for crop_index, crop_score in scores.items()
            if crop_index in requested_indexes
        }

    async def _score_crops_concurrently(
        self,
        scoring_crops: list[ScoringCrop],
    ) -> list[MetadataCropScore]:
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

    async def _score_one_crop(self, crop: ScoringCrop) -> list[MetadataCropScore]:
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
                crop_scores = self._align_crop_index(
                    crop, list(score_result.crops)
                )
                if not self._is_complete_response(crop, crop_scores):
                    _LOGGER.warning(
                        "XAI 응답 항목 누락으로 한 번 재요청합니다: "
                        "crop_index=%s",
                        crop.crop_index,
                    )
                    score_result = await asyncio.to_thread(
                        self.score_all, [crop]
                    )
                    crop_scores = self._align_crop_index(
                        crop, list(score_result.crops)
                    )
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
                    "XAI 판정 실패, crop_index=%s는 "
                    "임베딩 유사도로 대체합니다.",
                    crop.crop_index,
                )
                return []

        return crop_scores

    @staticmethod
    def _is_complete_response(
        crop: ScoringCrop,
        crop_scores: list[MetadataCropScore],
    ) -> bool:
        """필수 crop 판독과 후보별 판정이 모두 반환됐는지 확인합니다.

        프롬프트만으로 배열의 필수 key 개수를 강제할 수 없으므로, 누락을
        서버가 검출해 ``_score_one_crop``에서 한 번 재요청할 수 있게 합니다.
        """
        if len(crop_scores) != 1:
            return False

        crop_score = crop_scores[0]
        expected_reading_keys = set(_comparison_keys(crop.category))
        readings = {reading.key: reading for reading in crop_score.crop_readings}
        if set(readings) != expected_reading_keys:
            return False

        evaluations = {
            evaluation.sku_id: evaluation
            for evaluation in crop_score.evaluations
        }
        expected_sku_ids = {candidate.sku_code for candidate in crop.candidates}
        if set(evaluations) != expected_sku_ids:
            return False

        readable_keys = {
            key for key, reading in readings.items() if reading.value
        }
        return all(
            readable_keys
            <= {verdict.key for verdict in evaluation.xai_result.verdicts}
            for evaluation in evaluations.values()
        )

    @staticmethod
    def _align_crop_index(
        crop: ScoringCrop,
        crop_scores: list[MetadataCropScore],
    ) -> list[MetadataCropScore]:
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
        category_by_idx: collections.abc.Mapping[int, str],
    ) -> list[ScoringCrop]:
        """탐지 객체의 SKU 이미지를 읽어 채점 입력을 만듭니다.

        Args:
            crop_bytes: crop_index별 크롭 JPEG 바이트입니다.
            detected_objects: SKU 후보가 채워진 탐지 객체 목록입니다.
            category_by_idx: object_idx별 대분류입니다.

        Returns:
            후보 이미지를 읽을 수 있었던 크롭만 담은 채점 입력입니다.
        """
        scoring_crops = []
        for detected in detected_objects:
            if detected.object_idx not in crop_bytes:
                continue

            category = (
                category_by_idx.get(detected.object_idx) or detected.category
            )
            if not _comparison_keys(category):
                _LOGGER.warning(
                    "비교 항목이 없어 XAI를 건너뜁니다: "
                    "object_idx=%s category=%r",
                    detected.object_idx,
                    category,
                )
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
                    attrs=candidate.attrs,
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
                    category=category,
                    candidates=candidates,
                )
            )
        return scoring_crops

    @classmethod
    def _to_xai_object_result(
        cls,
        crop_score: MetadataCropScore,
        category: str,
    ) -> XaiObjectResult:
        """모델 응답을 애플리케이션 XAI 결과로 변환합니다."""
        readings = cls._build_readings(category, crop_score.crop_readings)
        return XaiObjectResult(
            object_idx=crop_score.crop_index,
            xai_category=category,
            xai_attrs={
                reading.key: reading.value
                for reading in readings
                if reading.value
            },
            readings=readings,
            evaluations=[
                ResolvedSkuEvaluation(
                    sku_id=evaluation.sku_id,
                    status=evaluation.status,
                    xai_result=cls._build_metadata_xai_result(
                        evaluation.xai_result, readings
                    ),
                )
                for evaluation in crop_score.evaluations
            ],
        )

    @staticmethod
    def _build_readings(
        category: str,
        crop_readings: list[GeminiCropReading],
    ) -> list[XaiCropReading]:
        """비교 항목 정의에 crop 판독값을 채워 crop 단위 결과를 만듭니다.

        비교 항목과 그 순서는 모델 응답이 아니라 ``catalog_spec``이
        결정합니다. 모델이 항목을 빠뜨리거나 순서를 바꿔도 화면 구성과
        일치도 분모가 흔들리지 않습니다.
        """
        keys = _comparison_keys(category)
        returned = {reading.key: reading for reading in crop_readings}

        missing = [key for key in keys if key not in returned]
        if missing:
            _LOGGER.warning("XAI crop 판독 항목 누락: %s", missing)

        readings = []
        for key in keys:
            reading = returned.get(key)
            if reading is None:
                value = ""
                note = MISSING_READING_NOTE
            else:
                value = reading.value
                note = "" if value else reading.note
            readings.append(
                XaiCropReading(key=key, value=value, note=note)
            )
        return readings

    @staticmethod
    def _build_metadata_xai_result(
        gemini: MetadataXaiResult,
        readings: list[XaiCropReading],
    ) -> XaiResult:
        """후보 1건의 메타데이터 판정과 총평을 조립합니다.

        crop 판독값이 없는 항목은 모델에 묻지 않고 판단 불가로 채웁니다.
        모든 후보에서 결과가 같으므로 모델이 매번 판정할 이유가 없고,
        후보마다 다르게 답할 여지도 없앱니다.
        """
        returned = {verdict.key: verdict for verdict in gemini.verdicts}

        criteria: list[XaiCriterion] = []
        for reading in readings:
            if not reading.value:
                criteria.append(
                    XaiCriterion(
                        key=reading.key,
                        verdict="UNKNOWN",
                        comment=reading.note or MISSING_READING_NOTE,
                    )
                )
                continue

            verdict = returned.get(reading.key)
            if verdict is None:
                _LOGGER.warning(
                    "XAI 후보 판정 누락, 판단 불가로 보정합니다: key=%s",
                    reading.key,
                )
                criteria.append(
                    XaiCriterion(
                        key=reading.key,
                        verdict="UNKNOWN",
                        comment=MISSING_VERDICT_COMMENT,
                    )
                )
                continue

            criteria.append(
                XaiCriterion(
                    key=reading.key,
                    verdict=verdict.verdict,
                    comment=verdict.comment,
                )
            )

        summary = " ".join(
            part for part in (gemini.common, gemini.difference) if part
        )

        return XaiResult(
            summary=summary,
            criteria=criteria,
            common=gemini.common,
            difference=gemini.difference,
        )

    def score_all(self, crops: list[ScoringCrop]) -> MetadataScoreResult:
        """전달받은 크롭과 SKU 후보를 한 번의 요청으로 채점합니다.

        평소에는 ``_score_one_crop``이 크롭 1건씩 넘겨 호출하지만, 여러
        크롭을 한 번에 채점하는 호출도 그대로 지원합니다.

        Args:
            crops: 크롭별 이미지와 SKU 후보 이미지 묶음입니다.

        Returns:
            프롬프트 버전에 맞는 채점 결과입니다. crop_index 기준으로
            정렬되지 않을 수 있습니다.

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

        prompt = self._build_prompt(targets)

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
            response = call_with_rate_limit_retry(
                lambda: client.models.generate_content(
                    model=self.settings.gemini_vlm_model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=MetadataScoreResult,
                        thinking_config=types.ThinkingConfig(
                            thinking_budget=THINKING_BUDGET
                        ),
                    ),
                ),
                operation_name="score_sku_candidates",
            )
            if not response.text:
                raise GeminiResponseInvalidError(
                    "Gemini XAI 판정 응답이 비어 있습니다."
                )

            score_result = MetadataScoreResult.model_validate_json(
                response.text
            )
            if not score_result.crops:
                raise GeminiResponseInvalidError(
                    "Gemini XAI 판정 결과에 crops가 없습니다."
                )
            return score_result

        except GeminiResponseInvalidError:
            raise
        except errors.ClientError as error:
            if getattr(error, "code", None) == 429:
                raise GeminiRateLimitError(
                    "Gemini XAI 판정 요청 한도를 초과했습니다."
                ) from error
            raise GeminiApiError(
                "Gemini XAI 판정 요청에 실패했습니다."
            ) from error
        except Exception as error:
            raise GeminiApiError(
                "Gemini XAI 판정 요청에 실패했습니다."
            ) from error

    def _build_prompt(self, targets: list[ScoringCrop]) -> str:
        """crop과 SKU 후보 구성을 프롬프트에 주입합니다."""
        return build_xai_prompt(
            crop_count=len(targets),
            crop_summary="\n".join(
                self._build_crop_block(crop) for crop in targets
            ),
        )

    @staticmethod
    def _build_crop_block(crop: ScoringCrop) -> str:
        """crop 1건의 카테고리·비교 항목·후보 카탈로그 값을 정리합니다.

        crop마다 카테고리가 다를 수 있으므로 비교 항목을 crop 블록 안에
        넣습니다. 후보의 카탈로그 값은 비교 항목에 해당하는 키만 추립니다.
        """
        keys = _comparison_keys(crop.category)
        lines = [
            f"    - crop {crop.crop_index} · 카테고리: {crop.category}",
            "      비교 항목:",
            build_comparison_block(crop.category),
            "      SKU 후보와 카탈로그 값:",
        ]
        for candidate in crop.candidates:
            values = {key: candidate.attrs.get(key, "") for key in keys}
            lines.append(
                f"        - {candidate.sku_code}: "
                f"{json.dumps(values, ensure_ascii=False)}"
            )
        return "\n".join(line for line in lines if line)

def _comparison_keys(category: str) -> list[str]:
    """해당 카테고리의 XAI 비교 대상 속성 키를 반환합니다.

    정의되지 않은 대분류이면 비교할 항목이 없으므로 빈 목록입니다.
    """
    try:
        return catalog_spec.visual_attribute_names(category)
    except KeyError:
        return []
