"""크롭과 SKU 후보 이미지를 루브릭으로 채점하는 서비스입니다."""

import string
import typing

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.core import config
from app.schemas.tagging import XaiResult
from app.services.gemini_service import (
    GeminiApiError,
    GeminiConfigurationError,
    GeminiResponseInvalidError,
)
from app.services.xai_prompt import XAI_PROMPT

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
        if not self.settings.gemini_api_key:
            raise GeminiConfigurationError("GEMINI_API_KEY가 설정되지 않았습니다.")
        if self._client is None:
            self._client = genai.Client(api_key=self.settings.gemini_api_key)
        return self._client

    def score_all(self, crops: list[ScoringCrop]) -> RubricScoreResult:
        """모든 크롭과 SKU 후보를 단 한 번의 요청으로 채점합니다.

        Args:
            crops: 크롭별 이미지와 SKU 후보 이미지 묶음입니다.

        Returns:
            crop_index 기준으로 정렬되지 않을 수 있는 전체 채점 결과입니다.

        Raises:
            ValueError: 채점 대상이 하나도 없는 경우입니다.
            GeminiConfigurationError: API 키가 없는 경우입니다.
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
            raise GeminiApiError("Gemini 루브릭 채점 요청에 실패했습니다.") from error