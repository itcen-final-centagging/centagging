"""Gemini Developer API 실제 호출 서비스입니다.

Service for live Gemini Developer API calls.
"""

import logging
import typing
import time
from google.genai import errors, types

from google import genai
from PIL import Image

from pydantic import ValidationError

from app.core import config
from app.schemas.gemini_detection import GeminiDetectionResult, GeminiModelDetectionResult
from app.services.furniture_detect_prompt import furniture_detection_prompt


# 오류 클래스들 모음
class GeminiConfigurationError(RuntimeError):
    """Gemini API 키가 누락된 경우 발생합니다.
    Raised when the Gemini API key is missing.
    """
    code = "DETECTION_NOT_CONFIGURED"


class GeminiApiError(RuntimeError):
    """Gemini API 호출이 실패한 경우 발생합니다. / Raised when a Gemini API call fails."""


class GeminiAuthenticationError(GeminiApiError):
    code = "DETECTION_AUTH_FAILED"


class GeminiInferenceError(GeminiApiError):
    code = "DETECTION_INFERENCE_FAILED"


class GeminiResponseInvalidError(GeminiApiError):
    code = "DETECTION_RESPONSE_INVALID"

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

    def detect_furniture(self, image: Image.Image) -> GeminiDetectionResult:
        """이미지에서 가구를 감지합니다. / Detect furniture in an image.

        Args:
            image: PIL 이미지 객체입니다.

        Returns:
            GeminiRawDetection 객체 리스트입니다.
        """
        if not self.is_configured:
            raise GeminiConfigurationError(
                "GEMINI_API_KEY is not configured."
            )

        started_at = time.perf_counter()
        object_count = 0

        try:
            client = genai.Client(
                api_key=self._settings.gemini_api_key
            )

            response = client.models.generate_content(
                model=self._settings.gemini_vlm_model,
                contents=[image,furniture_detection_prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=GeminiModelDetectionResult,
            ),
        )
            if not response.text:
                raise GeminiResponseInvalidError("Gemini VLM returned an empty response.")

            result = GeminiModelDetectionResult.model_validate_json(response.text)
            processing_time_ms = round((time.perf_counter() - started_at) * 1000)
            object_count = len(result.detections)
        
        except GeminiResponseInvalidError:
            raise

        except ValidationError as error:
            raise GeminiResponseInvalidError(
                "Gemini detection response is invalid."
            ) from error

        except errors.ClientError as error:
            if getattr(error, "code", None) in (401, 403):
                raise GeminiAuthenticationError(
                    "Gemini authentication failed."
                ) from error

            raise GeminiInferenceError(
                "Gemini detection request failed."
            ) from error

        except Exception as error:
            raise GeminiInferenceError(
                "Gemini detection request failed."
            ) from error

        logging.getLogger(__name__).info(
            "Gemini furniture detection finished: "
            "model=%s, processing_time_ms=%d, object_count=%d",
            self._settings.gemini_vlm_model,
            processing_time_ms,
            object_count, 
        )
        return GeminiDetectionResult(
            detections=result.detections,
            processing_time_ms=processing_time_ms,
        )