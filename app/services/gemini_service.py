"""Gemini Developer API 실제 호출 서비스입니다.

Service for live Gemini Developer API calls.
"""

import json
import typing

from google import genai
from google.genai import types
from PIL import Image

from app.core import config


class GeminiConfigurationError(RuntimeError):
    """Gemini API 키가 누락된 경우 발생합니다.

    Raised when the Gemini API key is missing.
    """


class GeminiApiError(RuntimeError):
    """Gemini API 호출이 실패한 경우 발생합니다. / Raised when a Gemini API call fails."""


class GeminiVerificationResult(typing.TypedDict):
    """Gemini 실제 호출 검증 결과입니다. / Result of a live Gemini verification call."""

    vlm_model: str
    embedding_model: str
    embedding_dimensions: int


class GeminiService:
    """VLM 및 임베딩 모델을 실제 Gemini API로 호출합니다."""

    def __init__(self, settings: config.Settings) -> None:
        """Gemini 서비스에 필요한 설정을 초기화합니다.

        Args:
            settings: API 키와 모델명이 담긴 애플리케이션 설정입니다.
        """
        self._settings = settings

    @property
    def is_configured(self) -> bool:
        """API 키 설정 여부를 반환합니다. 키 값 자체는 노출하지 않습니다."""
        return bool(self._settings.gemini_api_key)

    def verify_connection(self) -> GeminiVerificationResult:
        """텍스트 생성과 임베딩을 각각 한 번 호출해 실제 연동을 검증합니다.

        Returns:
            호출한 모델명과 임베딩 차원을 담은 검증 결과입니다.

        Raises:
            GeminiConfigurationError: Gemini API 키가 설정되지 않은 경우입니다.
            GeminiApiError: Gemini API 호출 또는 응답 검증에 실패한 경우입니다.
        """
        if not self.is_configured:
            raise GeminiConfigurationError(
                "GEMINI_API_KEY is not configured. "
                "Create .env from .env.example."
            )

        try:
            client = genai.Client(api_key=self._settings.gemini_api_key)
            text_response = client.models.generate_content(
                model=self._settings.gemini_vlm_model,
                contents="Connection verification. Reply only OK.",
            )
            if not text_response.text:
                raise RuntimeError("Gemini VLM returned an empty response.")

            embedding_response = client.models.embed_content(
                model=self._settings.gemini_embedding_model,
                contents="furniture",
            )
            embeddings = embedding_response.embeddings
            if not embeddings:
                raise RuntimeError(
                    "Gemini embedding model returned no embedding."
                )
            embedding_values = embeddings[0].values
            if not embedding_values:
                raise RuntimeError("Gemini embedding values are empty.")
        except (
            Exception
        ) as error:  # External SDK boundary; re-raise a domain error.
            raise GeminiApiError("Gemini API call failed.") from error

        return {
            "vlm_model": self._settings.gemini_vlm_model,
            "embedding_model": self._settings.gemini_embedding_model,
            "embedding_dimensions": len(embedding_values),
        }

    def generate_vlm_json(
        self,
        images: list[Image.Image],
        prompt: str,
    ) -> dict:
        """여러 이미지를 함께 분석하고 JSON 응답을 반환합니다.

        정답 SKU 메타데이터 추출처럼
        여러 장의 상품 이미지를 Gemini VLM에 전달하고
        구조화된 JSON 응답을 받아야 할 때 사용합니다.

        Args:
            images:
                Gemini에 전달할 PIL 이미지 목록입니다.

            prompt:
                이미지와 함께 전달할 VLM 프롬프트입니다.

        Returns:
            Gemini가 반환한 JSON을 Python dict로 변환한 결과입니다.

        Raises:
            GeminiConfigurationError:
                Gemini API 키가 설정되지 않은 경우입니다.

            GeminiApiError:
                Gemini API 호출 또는 JSON 응답 파싱에 실패한 경우입니다.
        """
        if not self.is_configured:
            raise GeminiConfigurationError(
                "GEMINI_API_KEY is not configured. "
                "Create .env from .env.example."
            )

        if not images:
            raise ValueError("At least one image is required.")

        if not prompt.strip():
            raise ValueError("Prompt must not be empty.")

        try:
            client = genai.Client(api_key=self._settings.gemini_api_key)

            # 이미지들을 먼저 전달하고 마지막에 prompt를 전달합니다.
            contents = [
                *images,
                prompt,
            ]

            response = client.models.generate_content(
                model=self._settings.gemini_vlm_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                ),
            )

            if not response.text:
                raise RuntimeError("Gemini VLM returned an empty response.")

            return json.loads(response.text)

        except json.JSONDecodeError as error:
            raise GeminiApiError("Gemini VLM returned invalid JSON.") from error

        except Exception as error:
            # External SDK boundary; re-raise a domain error.
            raise GeminiApiError(
                "Gemini VLM JSON generation failed."
            ) from error
