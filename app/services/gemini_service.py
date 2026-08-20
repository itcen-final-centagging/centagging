"""Google Gen AI 모델 실제 호출 서비스입니다.

Service for live Gemini model calls through Vertex AI or Developer API.
"""

import io
import json
import logging
import time
import typing
from collections.abc import Mapping

from google.genai import errors, types
from PIL import Image
from pydantic import ValidationError

from app.core import catalog_spec, config, genai_client
from app.schemas.furniture_attribute import FurnitureAttributeResult
from app.schemas.gemini_detection import (
    GeminiDetectionResult,
    GeminiModelDetectionResult,
)
from app.schemas.sku_rerank import SkuRerankResult
from app.services.furniture_attribute_rules import (
    build_allowed_attribute_schema,
    build_attribute_response_schema,
    validate_attribute_result,
)
from app.services.genai_retry import call_with_rate_limit_retry
from app.services.prompt.attribute_prompt.furniture_attribute_prompt import (
    FURNITURE_ATTRIBUTE_PROMPT,
)
from app.services.prompt.detect_prompt.furniture_detect_prompt import (
    FURNITURE_DETECTION_PROMPT,
)
from app.services.prompt.rerank_prompt.sku_rerank_prompt import (
    SKU_RERANK_PROMPT,
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


def _contains_hangul(text: str) -> bool:
    """문자열에 한글 음절이 포함되어 있는지 반환합니다."""
    return any("\uac00" <= char <= "\ud7a3" for char in text)


def _fallback_evidence(category: str) -> str:
    """탐지 근거가 한글이 아닐 때 사용할 기본 문장을 반환합니다."""
    return f"이미지에서 {category} 형태가 확인됩니다."


def _build_rerank_contents(
    query: str, candidates: list[dict[str, typing.Any]], top_k: int
) -> list[types.ContentUnionDict]:
    """SKU 재정렬 요청 본문을 만듭니다.

    정답 SKU나 평가용 라벨은 절대 포함하지 않습니다 — 검색어와 candidates에
    담긴 catalog 필드(sku_code/product_name/category/sub_category/
    attributes/brand/price)만 모델에 전달합니다.

    Args:
        query: 검색 프롬프트입니다.
        candidates: 1차 코사인 유사도로 뽑은 후보 SKU 목록입니다.
        top_k: 반환받을 최대 sku_code 개수입니다.

    Returns:
        Gemini ``generate_content`` 호출에 넘길 contents 목록입니다.
    """
    payload = json.dumps(
        {
            "query": query,
            "top_k": top_k,
            "candidates": candidates,
        },
        ensure_ascii=False,
        default=str,
    )
    return [SKU_RERANK_PROMPT, payload]


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

            response = call_with_rate_limit_retry(
                lambda: client.models.generate_content(
                    model=self._settings.gemini_vlm_model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=GeminiModelDetectionResult,
                    ),
                ),
                operation_name="detect_furniture",
            )
            if not response.text:
                raise GeminiResponseInvalidError(
                    "Gemini VLM returned an empty response."
                )

            result = GeminiModelDetectionResult.model_validate_json(
                response.text
            )

            normalized_detections = []

            for detection in result.detections:
                evidence = detection.evidence

                if not _contains_hangul(evidence):
                    logging.getLogger(__name__).warning(
                        "Gemini evidence가 한글이 아니어서 fallback을 사용합니다."
                    )
                    evidence = _fallback_evidence(detection.category)

                normalized_detections.append(
                    detection.model_copy(update={"evidence": evidence})
                )

            result = result.model_copy(
                update={"detections": normalized_detections}
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
            if getattr(error, "code", None) == 429:
                raise GeminiRateLimitError(
                    "Gemini 가구 탐지 요청 한도를 초과했습니다."
                ) from error
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

            # FurnitureAttributeResult를 Gemini SDK에 직접 전달 X
            response = call_with_rate_limit_retry(
                lambda: client.models.generate_content(
                    model=self._settings.gemini_vlm_model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=(
                            build_attribute_response_schema(category)
                        ),
                    ),
                ),
                operation_name="extract_furniture_attributes",
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
            if getattr(error, "code", None) == 429:
                raise GeminiRateLimitError(
                    "Gemini 가구 속성 추출 요청 한도를 초과했습니다."
                ) from error
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

    def rerank_sku_candidates(
        self,
        query: str,
        candidates: list[dict[str, typing.Any]],
        top_k: int,
    ) -> list[str]:
        """검색어 의미에 맞게 후보 SKU 목록을 Gemini로 재정렬합니다.

        1차 코사인 유사도로 뽑은 후보 풀의 순서를, 검색어와 각 후보의
        catalog 필드(product_name/category/sub_category/attributes/
        brand/price)를 비교해 다시 매깁니다. candidates에는 catalog
        필드만 담아야 하며 정답이나 평가용 정보는 포함하지 않습니다.

        Args:
            query: 검색 프롬프트입니다.
            candidates: 재정렬할 후보 SKU 목록입니다. 각 항목은 최소한
                sku_code 키를 가져야 합니다.
            top_k: 반환받을 최대 sku_code 개수입니다.

        Returns:
            검색어와 가장 잘 맞는 순서로 정렬된 sku_code 목록입니다
            (최대 top_k개). candidates가 비어 있으면 빈 목록입니다.

        Raises:
            GeminiConfigurationError: Gemini API 키가 설정되지 않은
                경우입니다.
            GeminiApiError: Gemini API 호출 또는 응답 검증에 실패한
                경우입니다.
        """
        if not self.is_configured:
            raise GeminiConfigurationError(
                "Google Gen AI 인증 설정이 누락되었습니다."
            )
        if not candidates:
            return []

        try:
            client = genai_client.create_client(self._settings)
            contents = _build_rerank_contents(query, candidates, top_k)

            response = client.models.generate_content(
                model=self._settings.gemini_rerank_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=SkuRerankResult,
                    temperature=0.0,
                ),
            )

            if not response.text:
                raise GeminiResponseInvalidError(
                    "Gemini 재정렬 응답이 비어 있습니다."
                )

            result = SkuRerankResult.model_validate_json(response.text)

            valid_codes = {candidate["sku_code"] for candidate in candidates}
            seen: set[str] = set()
            ranked_codes: list[str] = []
            for code in result.ranked_sku_codes:
                if code in valid_codes and code not in seen:
                    ranked_codes.append(code)
                    seen.add(code)

            return ranked_codes[:top_k]

        except GeminiResponseInvalidError:
            raise

        except ValidationError as error:
            raise GeminiResponseInvalidError(
                "Gemini 재정렬 응답이 올바르지 않습니다."
            ) from error

        except errors.ClientError as error:
            if getattr(error, "code", None) in (401, 403):
                raise GeminiAuthenticationError(
                    "Gemini 인증이 실패했습니다."
                ) from error

            raise GeminiInferenceError(
                "Gemini 재정렬 요청이 실패했습니다."
            ) from error

        except Exception as error:
            raise GeminiInferenceError(
                "Gemini 재정렬 요청이 실패했습니다."
            ) from error

    def embed_image(self, image: Image.Image | bytes) -> list[float]:
        """이미지를 임베딩하여 벡터 값을 반환합니다.

        Args:
            image: PIL 이미지 객체 또는 이미 변환된 JPEG 바이트입니다.

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

            if isinstance(image, bytes):
                image_format = "JPEG"
                image_bytes = image
            else:
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

    def embed_text(self, text: str) -> list[float]:
        """텍스트를 임베딩하여 벡터 값을 반환합니다.

        Args:
            text: 임베딩할 텍스트입니다.

        Returns:
            임베딩 벡터(float 리스트)입니다.

        Raises:
            GeminiConfigurationError: Gemini API 키가 설정되지 않은 경우입니다.
            GeminiEmbeddingError: 텍스트 임베딩에 실패한 경우입니다.
        """
        if not self.is_configured:
            raise GeminiConfigurationError(
                "Google Gen AI 인증 설정이 누락되었습니다."
            )

        try:
            client = genai_client.create_client(self._settings)

            response = client.models.embed_content(
                model=self._settings.gemini_embedding_model,
                contents=text,
            )

            embeddings = response.embeddings
            if not embeddings or not embeddings[0].values:
                raise GeminiEmbeddingError(
                    "Gemini 텍스트 임베딩 응답이 비어 있습니다."
                )

            return embeddings[0].values
        except GeminiEmbeddingError:
            raise
        except Exception as error:
            logging.getLogger(__name__).exception("Gemini 텍스트 임베딩 실패")
            raise GeminiEmbeddingError(
                f"Gemini 텍스트 임베딩에 실패했습니다: {error}"
            ) from error

    def embed_with_attrs(
        self,
        image: Image.Image,
        *,
        category: str | None = None,
        sub_category: str | None = None,
        attrs: Mapping[str, str] | None = None,
    ) -> list[float]:
        """이미지와 추출 속성을 함께 임베딩합니다."""
        raise NotImplementedError(
            "하이브리드 임베딩 구현이 아직 연결되지 않았습니다."
        )
