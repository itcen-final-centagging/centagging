"""Gemini 연동 상태와 실제 호출 검증 API입니다. / Gemini status and live verification API."""

import fastapi
import pydantic

from app.core import config
from app.services import gemini_service

router = fastapi.APIRouter(prefix="/api/v1/gemini", tags=["gemini"])


class GeminiStatusResponse(pydantic.BaseModel):
    """API 키 노출 없이 Gemini 설정 상태를 전달합니다."""

    configured: bool
    vlm_model: str
    embedding_model: str


class GeminiVerifyResponse(pydantic.BaseModel):
    """실제 Gemini 호출 검증 결과입니다."""

    status: str
    vlm_model: str
    embedding_model: str
    embedding_dimensions: int


@router.get("/status", response_model=GeminiStatusResponse)
async def gemini_status() -> GeminiStatusResponse:
    """Return Gemini API 키 설정 여부와 현재 사용할 모델명입니다.

    Returns:
        API 키 노출 없이 Gemini 설정 상태와 모델명을 담은 응답입니다.
    """
    settings = config.get_settings()
    service = gemini_service.GeminiService(settings)
    return GeminiStatusResponse(
        configured=service.is_configured,
        vlm_model=settings.gemini_vlm_model,
        embedding_model=settings.gemini_embedding_model,
    )


@router.post("/verify", response_model=GeminiVerifyResponse)
async def verify_gemini_connection() -> GeminiVerifyResponse:
    """실제 Gemini VLM과 임베딩 API를 명시적으로 호출해 연동을 확인합니다.

    Returns:
        호출한 모델명과 임베딩 차원을 담은 성공 응답입니다.

    Raises:
        fastapi.HTTPException: API 키가 없거나 Gemini 호출에 실패한 경우입니다.
    """
    service = gemini_service.GeminiService(config.get_settings())

    try:
        result = service.verify_connection()
    except gemini_service.GeminiConfigurationError as error:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gemini API key is not configured.",
        ) from error
    except gemini_service.GeminiApiError as error:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_502_BAD_GATEWAY,
            detail="Gemini API call failed. Check the API key, model access, and quota.",
        ) from error

    return GeminiVerifyResponse(status="ok", **result)
