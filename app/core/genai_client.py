"""Google Gen AI 런타임 클라이언트 생성 정책입니다."""

from google import genai

from app.core import config


def is_configured(settings: config.Settings) -> bool:
    """Vertex AI 또는 Gemini Developer API 인증 설정 여부를 반환합니다."""
    return bool(
        settings.vertex_api_key
        or settings.gcp_project_id
        or settings.gemini_api_key
    )


def create_client(settings: config.Settings) -> genai.Client:
    """실행 환경에 맞는 Google Gen AI 클라이언트를 생성합니다.

    로컬 Vertex AI Express Mode 키, 운영 VM 서비스 계정 ADC, 기존
    Gemini Developer API 키 순으로 인증 방식을 선택합니다. 기존 팀원
    환경의 ``GEMINI_API_KEY``는 하위 호환 용도로 유지합니다.

    Args:
        settings: AI 인증과 Vertex AI 라우팅 설정입니다.

    Returns:
        선택된 인증 방식으로 초기화한 Google Gen AI 클라이언트입니다.

    Raises:
        ValueError: 사용할 수 있는 AI 인증 설정이 없는 경우입니다.
    """
    if settings.vertex_api_key:
        return genai.Client(vertexai=True, api_key=settings.vertex_api_key)

    if settings.gcp_project_id:
        return genai.Client(
            vertexai=True,
            project=settings.gcp_project_id,
            location=settings.vertex_ai_location,
        )

    if settings.gemini_api_key:
        return genai.Client(api_key=settings.gemini_api_key)

    raise ValueError("VERTEX_API_KEY, GCP_PROJECT_ID 또는 GEMINI_API_KEY가 필요합니다.")
