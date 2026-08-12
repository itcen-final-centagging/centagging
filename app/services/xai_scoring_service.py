"""크롭과 SKU 후보 이미지를 루브릭으로 채점하는 서비스입니다."""

import io
import string
import typing

from google import genai
from google.genai import types
from PIL import Image
from pydantic import BaseModel, Field

from app.core import config
from app.services.gemini_service import (
    GeminiApiError,
    GeminiConfigurationError,
    GeminiResponseInvalidError,
)
from app.services.xai_prompt import XAI_PROMPT


# response_schema로 그대로 넘길 내부 스키마입니다.
class XaiCriterion(BaseModel):
    """루브릭 기준 1건입니다."""

    label: typing.Literal["구조", "색상", "디테일", "맥락"]
    score: int = Field(ge=0, le=30)
    comment: str


class VlmMood(BaseModel):
    """크롭 이미지에서 읽어낸 분위기 요약입니다."""

    summary: str = ""
    tags: list[str] = Field(default_factory=list)


class XaiResultItem(BaseModel):
    """SKU 1건에 대한 XAI 설명입니다."""

    summary: str
    criteria: list[XaiCriterion] = Field(default_factory=list)
    vlm_mood: VlmMood = Field(default_factory=VlmMood)


class SkuEvaluation(BaseModel):
    """SKU 후보 1건의 채점 결과입니다."""

    sku_id: str
    status: typing.Literal["Matched", "Rejected"]
    total_score: int = Field(ge=0, le=100)
    xai_result: XaiResultItem

class ObjectAttribute(BaseModel):
    """크롭에서 관찰된 객체 속성 1건입니다."""

    key: str
    value: str

class CropScore(BaseModel):
    """크롭 1건의 채점 결과입니다."""

    crop_index: int
    label: str = ""
    confidence: int = Field(default=0, ge=0, le=100)
    object_attrs: list[ObjectAttribute] = Field(
        default_factory=list
    )
    evaluations: list[SkuEvaluation] = Field(default_factory=list)


class RubricScoreResult(BaseModel):
    """루브릭 채점 전체 결과입니다."""

    crops: list[CropScore] = Field(default_factory=list)


class XaiScoringService:
    """크롭과 SKU 후보 이미지를 루브릭 기준으로 채점하는 서비스입니다."""

    def __init__(self, settings: config.Settings) -> None:
        """채점에 필요한 Gemini 설정을 주입받습니다.

        Args:
            settings: API 키와 VLM 모델명이 담긴 애플리케이션 설정입니다.
        """
        self.settings = settings

    def scoring_by_xai(
        self,
        crop_index: int,
        crop_image: Image.Image,
        sku_images: dict[str, bytes],
    ) -> RubricScoreResult:
        """크롭 1건과 SKU 후보 이미지를 Gemini에 넘겨 루브릭 채점을 합니다.

        블로킹 SDK 호출이므로 호출부에서 `asyncio.to_thread`로 감싸세요.

        Args:
            crop_index: 탐지 객체 인덱스입니다. 프롬프트의 crop_id를
                `crop_{index}` 형태로 만드는 데 씁니다.
            crop_image: 대상 크롭 PIL 이미지입니다.
            sku_images: `{sku_code: JPEG 바이트}` 형태의 후보 이미지입니다.
                `_read_sku_image`가 실패로 None을 준 항목은 호출부에서
                미리 걸러서 넘기세요.

        Returns:
            해당 크롭 1건에 대한 채점 결과입니다.

        Raises:
            ValueError: 채점할 SKU 후보 이미지가 하나도 없는 경우입니다.
            GeminiConfigurationError: Gemini API 키가 없는 경우입니다.
            GeminiResponseInvalidError: 응답이 비었거나 스키마와 다른
                경우입니다.
            GeminiApiError: 그 밖의 Gemini 호출 실패입니다.
        """
        if not sku_images:
            raise ValueError("채점할 SKU 후보 이미지가 없습니다.")
        if not self.settings.gemini_api_key:
            raise GeminiConfigurationError(
                "GEMINI_API_KEY가 설정되지 않았습니다."
            )

        crop_id = f"crop_{crop_index}"
        crop_summary = f"    - {crop_id}: SKU 후보 {list(sku_images.keys())}"
        prompt = string.Template(XAI_PROMPT).substitute(
            crop_count=1,
            crop_summary=crop_summary,
        )

        buffer = io.BytesIO()
        crop_image.convert("RGB").save(buffer, format="JPEG", quality=90)

        contents: list[typing.Any] = [
            prompt,
            f"\n=== TARGET CROP: {crop_id} ===",
            types.Part.from_bytes(
                data=buffer.getvalue(), mime_type="image/jpeg"
            ),
        ]
        for sku_code, sku_bytes in sku_images.items():
            contents += [
                f"[{crop_id}] CANDIDATE SKU: {sku_code}",
                types.Part.from_bytes(
                    data=sku_bytes, mime_type="image/jpeg"
                ),
            ]

        try:
            client = genai.Client(api_key=self.settings.gemini_api_key)
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
        # 외부 SDK 경계이므로 도메인 오류로 변환해 다시 던집니다.
        except Exception as error:  # pylint: disable=broad-exception-caught
            raise GeminiApiError(
                "Gemini 루브릭 채점 요청에 실패했습니다."
            ) from error