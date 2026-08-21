"""Gemini 텍스트·이미지 임베딩 호출.

이미지 임베딩은 app/services/gemini_service.py의 GeminiService.embed_image를
그대로 재사용한다(로직 중복 방지, 기존 서비스는 수정하지 않는다).

텍스트 임베딩은 GeminiService에 아직 공개 메서드가 없어서, 같은 Developer API
클라이언트 패턴(GEMINI_API_KEY)으로 이 모듈에서 직접 호출한다.
"""

from __future__ import annotations

from google import genai

from app.core import config
from app.services.gemini_service import (
    GeminiConfigurationError,
    GeminiEmbeddingError,
    GeminiService,
)

__all__ = [
    "GeminiConfigurationError",
    "GeminiEmbeddingError",
    "embed_text",
    "make_image_embedder",
]


def embed_text(settings: config.Settings, text: str) -> list[float]:
    """텍스트 1건을 임베딩하여 벡터 값을 반환한다.
    ...
    """
    if not settings.gcp_project_id and not settings.gemini_api_key:
        raise GeminiConfigurationError(
            "GEMINI_API_KEY 또는 GCP_PROJECT_ID(Vertex) 중 하나는 설정되어야 합니다."
        )

    try:
        if settings.gcp_project_id:
            client = genai.Client(
                vertexai=True,
                project=settings.gcp_project_id,
                location=settings.vertex_ai_location,
            )
        else:
            client = genai.Client(api_key=settings.gemini_api_key)

        response = client.models.embed_content(
            model=settings.gemini_embedding_model,
            contents=text,
        )
        embeddings = response.embeddings
        if not embeddings or not embeddings[0].values:
            raise GeminiEmbeddingError("Gemini 텍스트 임베딩 응답이 비어 있습니다.")
        return embeddings[0].values
    except GeminiEmbeddingError:
        raise
    except Exception as error:
        raise GeminiEmbeddingError("Gemini 텍스트 임베딩에 실패했습니다.") from error


def make_image_embedder(settings: config.Settings) -> GeminiService:
    """이미지 임베딩에 쓸 GeminiService 인스턴스를 만든다.

    Args:
        settings: GEMINI_API_KEY·임베딩 모델이 담긴 애플리케이션 설정입니다.

    Returns:
        `embed_image(image)`를 제공하는 GeminiService입니다.
    """
    return GeminiService(settings)
