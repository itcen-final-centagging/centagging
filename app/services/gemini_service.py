"""Google Gen AI 모델 실제 호출 서비스입니다.

Service for live Gemini model calls through Vertex AI or Developer API.
"""

import dataclasses
import io
import logging
import time
import typing
import json

from google.genai import errors, types
from PIL import Image
from pydantic import ValidationError
from collections.abc import Mapping

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
from app.services.genai_retry import (
    RateLimitCallback,
    call_with_rate_limit_retry,
)
from app.services.prompt.attribute_prompt.furniture_attribute_prompt import (
    build_furniture_attribute_prompt as build_furniture_attribute_prompt_v1,
)
from app.services.prompt.attribute_prompt.furniture_attribute_prompt_v2 import (
    build_furniture_attribute_prompt as build_furniture_attribute_prompt_v2,
)
from app.services.prompt.detect_prompt.furniture_detect_prompt import (
    build_furniture_detection_prompt as build_furniture_detection_prompt_v1,
)
from app.services.prompt.detect_prompt.furniture_detect_prompt_v2 import (
    build_furniture_detection_prompt as build_furniture_detection_prompt_v2,
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


PromptVersion = typing.Literal["v1", "v2"]


@dataclasses.dataclass(frozen=True)
class GeminiCallTelemetry:
    """프롬프트 평가에 전달할 단일 Gemini 호출 계측값입니다."""

    operation_name: str
    prompt_version: PromptVersion
    attempt_count: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    generation_succeeded: bool


GeminiTelemetryCallback = typing.Callable[[GeminiCallTelemetry], None]


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

    def __init__(  # pylint: disable=too-many-arguments
        self,
        settings: config.Settings,
        *,
        prompt_version: PromptVersion = "v2",
        telemetry_callback: GeminiTelemetryCallback | None = None,
        rate_limit_retry_delays_seconds: tuple[float, ...] | None = None,
        rate_limit_retry_jitter_seconds: float = 0.0,
        rate_limit_callback: RateLimitCallback | None = None,
    ) -> None:
        """Gemini 서비스에 필요한 설정을 초기화합니다.

        Args:
            settings: API 키와 모델명이 담긴 애플리케이션 설정입니다.
            prompt_version: 탐지·속성 추출에 적용할 프롬프트 버전입니다.
            telemetry_callback: 생성 호출의 토큰·재시도 정보를 받을 함수입니다.
            rate_limit_retry_delays_seconds: 429 응답의 재시도 간격입니다.
            rate_limit_retry_jitter_seconds: 재시도 간격에 추가할 최대 난수입니다.
            rate_limit_callback: 429 발생과 재시도 지연을 전달받을 함수입니다.

        Raises:
            ValueError: 프롬프트 버전 또는 재시도 설정이 유효하지 않은
                경우입니다.
        """
        if prompt_version not in ("v1", "v2"):
            raise ValueError(
                f"지원하지 않는 프롬프트 버전입니다: {prompt_version}"
            )
        if (
            rate_limit_retry_jitter_seconds < 0
            or rate_limit_retry_delays_seconds is not None
            and any(delay < 0 for delay in rate_limit_retry_delays_seconds)
        ):
            raise ValueError("재시도 지연 시간은 0 이상이어야 합니다.")
        self._settings = settings
        self._prompt_version = prompt_version
        self._telemetry_callback = telemetry_callback
        self._rate_limit_retry_delays_seconds = rate_limit_retry_delays_seconds
        self._rate_limit_retry_jitter_seconds = rate_limit_retry_jitter_seconds
        self._rate_limit_callback = rate_limit_callback

    @property
    def prompt_version(self) -> PromptVersion:
        """현재 탐지·속성 추출 프롬프트 버전을 반환합니다."""
        return self._prompt_version

    def _build_detection_contents(
        self,
        image: Image.Image,
    ) -> list[types.ContentUnionDict]:
        """프롬프트 버전에 맞는 객체 탐지 입력을 생성합니다."""
        if self._prompt_version == "v1":
            return [
                image,
                build_furniture_detection_prompt_v1(
                    allowed_categories=catalog_spec.CATEGORIES,
                ),
            ]

        return [
            image,
            build_furniture_detection_prompt_v2(
                allowed_categories=catalog_spec.CATEGORIES,
            ),
        ]

    def _build_attribute_contents(
        self,
        image: Image.Image,
        attribute_schema: Mapping[str, object],
    ) -> list[types.ContentUnionDict]:
        """프롬프트 버전에 맞는 속성 추출 입력을 생성합니다."""
        if self._prompt_version == "v1":
            return [
                image,
                build_furniture_attribute_prompt_v1(
                    attribute_schema=attribute_schema,
                ),
            ]

        return [
            image,
            build_furniture_attribute_prompt_v2(
                attribute_schema=attribute_schema,
            ),
        ]

    def _record_telemetry(
        self,
        *,
        operation_name: str,
        response: types.GenerateContentResponse | None,
        attempt_count: int,
        generation_succeeded: bool,
    ) -> None:
        """생성 응답의 토큰 사용량과 시도 횟수를 선택적으로 기록합니다."""
        if self._telemetry_callback is None:
            return

        usage_metadata = getattr(response, "usage_metadata", None)

        def _token_count(field_name: str) -> int:
            value = getattr(usage_metadata, field_name, 0)
            return value if isinstance(value, int) and value >= 0 else 0

        self._telemetry_callback(
            GeminiCallTelemetry(
                operation_name=operation_name,
                prompt_version=self._prompt_version,
                attempt_count=attempt_count,
                input_tokens=_token_count("prompt_token_count"),
                output_tokens=_token_count("candidates_token_count"),
                total_tokens=_token_count("total_token_count"),
                generation_succeeded=generation_succeeded,
            )
        )

    def _call_generation(
        self,
        operation: typing.Callable[[], types.GenerateContentResponse],
        operation_name: str,
    ) -> types.GenerateContentResponse:
        """재시도 시도 횟수와 토큰을 기록하며 생성 호출을 실행합니다."""
        attempt_count = 0

        def _tracked_operation() -> types.GenerateContentResponse:
            nonlocal attempt_count
            attempt_count += 1
            return operation()

        try:
            response = call_with_rate_limit_retry(
                _tracked_operation,
                operation_name=operation_name,
                retry_delays_seconds=self._rate_limit_retry_delays_seconds,
                jitter_seconds=self._rate_limit_retry_jitter_seconds,
                rate_limit_callback=self._rate_limit_callback,
            )
        except Exception:
            self._record_telemetry(
                operation_name=operation_name,
                response=None,
                attempt_count=attempt_count,
                generation_succeeded=False,
            )
            raise
        self._record_telemetry(
            operation_name=operation_name,
            response=response,
            attempt_count=attempt_count,
            generation_succeeded=True,
        )
        return response

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
            contents = self._build_detection_contents(image)
            response = self._call_generation(
                lambda: client.models.generate_content(
                    model=self._settings.gemini_vlm_model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=GeminiModelDetectionResult,
                    ),
                ),
                "detect_furniture",
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
            client = genai_client.create_client(self._settings)
            contents = self._build_attribute_contents(image, attribute_schema)
            response = self._call_generation(
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
                "extract_furniture_attributes",
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

    def embed_fused(
        self,
        image: Image.Image,
        metadata_text: str,
    ) -> list[float]:
        """메타 텍스트·전처리 RGB·그레이스케일을 한 번에 임베딩합니다.

        Args:
            image: 전처리가 완료된 RGB 이미지입니다.
            metadata_text: 카탈로그 스펙 순서로 정규화한 메타데이터입니다.

        Returns:
            세 입력을 융합한 임베딩 벡터입니다.

        Raises:
            GeminiConfigurationError: Gemini 인증이 설정되지 않은 경우입니다.
            GeminiEmbeddingError: Gemini 융합 임베딩 호출이 실패한 경우입니다.
        """
        if not self.is_configured:
            raise GeminiConfigurationError(
                "Google Gen AI 인증 설정이 누락되었습니다."
            )

        try:
            rgb = image.convert("RGB")
            gray = rgb.convert("L").convert("RGB")
            contents = [
                "상품 메타데이터:\n" + (metadata_text or "(없음)"),
                _image_part_as_png(rgb),
                _image_part_as_png(gray),
            ]
            client = genai_client.create_client(self._settings)
            response = client.models.embed_content(
                model=self._settings.gemini_embedding_model,
                contents=contents,  # type: ignore[arg-type]
            )
            embeddings = response.embeddings
            if not embeddings or not embeddings[0].values:
                raise GeminiEmbeddingError(
                    "Gemini 융합 임베딩 응답이 비어 있습니다."
                )
            return embeddings[0].values
        except GeminiEmbeddingError:
            raise
        except Exception as error:
            logging.getLogger(__name__).exception("Gemini 융합 임베딩 실패")
            raise GeminiEmbeddingError(
                f"Gemini 융합 임베딩에 실패했습니다: {error}"
            ) from error


def _image_part_as_png(image: Image.Image) -> types.Part:
    """Gemini interleaved 입력에 쓸 PNG Part를 생성합니다."""
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG", optimize=False)
    return types.Part.from_bytes(
        data=buffer.getvalue(),
        mime_type="image/png",
    )
