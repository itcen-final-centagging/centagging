"""Google Gen AI client configuration shared by runtime API services."""

from google import genai

from app.core import config


def is_configured(settings: config.Settings) -> bool:
    """Return whether local Express Mode or production ADC is configured."""
    return bool(
        settings.vertex_api_key
        or (settings.gcp_project_id and settings.vertex_ai_location)
    )


def create_client(settings: config.Settings) -> genai.Client:
    """Create a Vertex AI client for local or production runtime.

    Local development uses a Vertex AI Express Mode API key. Production uses
    Vertex AI with Application Default Credentials from the VM service account.
    """
    if settings.vertex_api_key:
        return genai.Client(vertexai=True, api_key=settings.vertex_api_key)

    if settings.gcp_project_id and settings.vertex_ai_location:
        return genai.Client(
            vertexai=True,
            project=settings.gcp_project_id,
            location=settings.vertex_ai_location,
        )

    raise ValueError(
        "VERTEX_API_KEY or GCP_PROJECT_ID and VERTEX_AI_LOCATION must be "
        "configured."
    )
