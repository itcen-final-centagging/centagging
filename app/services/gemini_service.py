"""Google Gen AI 모델 실제 호출 서비스입니다.

Service for live Gemini model calls through Vertex AI or Developer API.
"""

import io
import json
import logging
import time
import typing

from google.genai import errors, types
from PIL import Image
from pydantic import ValidationError

from app.core import catalog_spec, config, genai_client
from app.schemas.furniture_attribute import FurnitureAttributeResult
from app.schemas.gemini_detection import (
    GeminiDetectionResult,
    GeminiModelDetectionResult,
)
from app.services.furniture_attribute_rules import (
    build_allowed_attribute_schema,
    validate_attribute_result,
)
from app.services.prompt.attribute_prompt.furniture_attribute_prompt import (
    FURNITURE_ATTRIBUTE_PROMPT,
)
from app.services.prompt.detect_prompt.furniture_detect_prompt import (
    FURNITURE_DETECTION_PROMPT,
)


# 오류 클래스들 모음
class GeminiConfigurationError(RuntimeError):
    """Google Gen AI 인증 설정이 누락되었을 때 발생합니다."""

    code = "DETECTION_NOT_CONFIGURED"


class GeminiApiError(RuntimeError):
    """Gemini API 호출이 실패한 경우 발생합니다. / Raised when a Gemini API call fails."""

    code = "API_CALL_FAIL"


class GeminiRateLimitError(GeminiApiError):
    """Gemini 요청 한도를 초과했을 때 발생합니다."""

    code = "RATE_LIMITED"


class GeminiAuthenticationError(GeminiApiError):
    """Gemini 인증에 실패할 때 발생합니다."""

    code = "DETECTION_AUTH_FAILED"


class GeminiInferenceError(GeminiApiError):
    """Gemini 추론 요청에 실패할 때 발생합니다."""

    code = "DETECTION_INFERENCE_FAILED"


class GeminiResponseInvalidError(GeminiApiError):
    """Gemini 응답 검증에 실패할 때 발생합니다."""

    code = "DETECTION_RESPONSE_INVALID"


class GeminiVerificationResult(typing.TypedDict):
    """Gemini 실제 호출 검증 결과입니다. / Result of a live Gemini verification call."""

    vlm_model: str
    embedding_model: str
    embedding_dimensions: int


class GeminiEmbeddingError(RuntimeError):
    """Gemini 기반 임베딩 호출이 실패한 경우의 오류입니다."""


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
        """Google Gen AI 인증 설정 여부를 반환합니다."""
        return genai_client.is_configured(self._settings)

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
                "Google Gen AI authentication is not configured."
            )

        try:
            client = genai_client.create_client(self._settings)
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
                "Google Gen AI authentication is not configured."
            )

        started_at = time.perf_counter()
        object_count = 0

        try:
            client = genai_client.create_client(self._settings)

            category_context = json.dumps(
                {"allowed_categories": catalog_spec.CATEGORIES},
                ensure_ascii=False,
            )

            contents: list[types.ContentUnionDict] = [
                image,
                FURNITURE_DETECTION_PROMPT,
                category_context,
            ]

            response = client.models.generate_content(
                model=self._settings.gemini_vlm_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=GeminiModelDetectionResult,
                ),
            )
            if not response.text:
                raise GeminiResponseInvalidError(
                    "Gemini VLM returned an empty response."
                )

            result = GeminiModelDetectionResult.model_validate_json(
                response.text
            )

            invalid_categories = [
                detection.category
                for detection in result.detections
                if detection.category not in catalog_spec.CATEGORIES
            ]

            if invalid_categories:
                raise GeminiResponseInvalidError(
                    f"허용되지 않은 카테고리입니다: {invalid_categories}"
                )

            processing_time_ms = round(
                (time.perf_counter() - started_at) * 1000
            )
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

    def extract_furniture_attributes(
        self, image: Image.Image, category: str
    ) -> FurnitureAttributeResult:
        """크롭 이미지에서 카테고리별 가구 속성을 추출합니다."""
        if not self.is_configured:
            raise GeminiConfigurationError("GEMINI_API_KEY is not configured.")

        try:
            attribute_schema = build_allowed_attribute_schema(category)
            attribute_context = json.dumps(attribute_schema, ensure_ascii=False)

            client = genai_client.create_client(self._settings)
            contents: list[types.ContentUnionDict] = [
                image,
                FURNITURE_ATTRIBUTE_PROMPT,
                attribute_context,
            ]

            response = client.models.generate_content(
                model=self._settings.gemini_vlm_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=FurnitureAttributeResult,
                ),
            )

            if not response.text:
                raise GeminiResponseInvalidError(
                    "Gemini 속성 응답이 비어 있습니다."
                )

            result = FurnitureAttributeResult.model_validate_json(response.text)

            return validate_attribute_result(category, result)

        except GeminiResponseInvalidError:
            raise

        except ValidationError as error:
            raise GeminiResponseInvalidError(
                "Gemini에서 반환된 속성 응답이 올바르지 않습니다."
            ) from error

        except errors.ClientError as error:
            if getattr(error, "code", None) in (401, 403):
                raise GeminiAuthenticationError(
                    "Gemini 인증이 실패했습니다."
                ) from error

            raise GeminiInferenceError(
                "Gemini 속성 추출 요청이 실패했습니다."
            ) from error

        except ValueError as error:
            raise GeminiResponseInvalidError(
                "Gemini 속성 결과 확인 실패했습니다."
            ) from error

        except Exception as error:
            raise GeminiInferenceError(
                "Gemini 속성 추출 요청이 실패했습니다."
            ) from error

    def embed_image(self, image: Image.Image) -> list[float]:
        """이미지를 임베딩하여 벡터 값을 반환합니다.

        Args:
            image: PIL 이미지 객체입니다.

        Returns:
            임베딩 벡터(float 리스트)입니다.

        Raises:
            GeminiConfigurationError: Gemini API 키가 설정되지 않은 경우입니다.
            GeminiEmbeddingError: 이미지 임베딩에 실패한 경우입니다.
        """
        if not self.is_configured:
            raise GeminiConfigurationError(
                "Google Gen AI 인증 설정이 누락되었습니다."
            )

        try:
            client = genai_client.create_client(self._settings)

            image_format = (image.format or "PNG").upper()
            buffer = io.BytesIO()
            image.save(buffer, format=image_format)
            image_bytes = buffer.getvalue()

            response = client.models.embed_content(
                model=self._settings.gemini_embedding_model,
                contents=[  # type: ignore[arg-type]
                    types.Part.from_bytes(
                        data=image_bytes,
                        mime_type=f"image/{image_format.lower()}",
                    ),
                ],
            )

            embeddings = response.embeddings
            if not embeddings or not embeddings[0].values:
                raise GeminiEmbeddingError(
                    "Gemini 임베딩 응답이 비어 있습니다."
                )

            return embeddings[0].values
        except GeminiEmbeddingError:
            raise
        except Exception as error:
            logging.getLogger(__name__).exception("Gemini 이미지 임베딩 실패")
            raise GeminiEmbeddingError(
                f"Gemini 이미지 임베딩에 실패했습니다: {error}"
            ) from error
