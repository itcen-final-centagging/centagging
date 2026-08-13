"""Google Gen AI runtime client configuration tests."""

import dataclasses
import unittest
from unittest import mock

from app.core import config, genai_client


def _settings(vertex_api_key: str = "") -> config.Settings:
    """Build minimal settings for Gen AI client tests."""
    return config.Settings(
        gemini_api_key="unused-developer-api-key",
        vertex_api_key=vertex_api_key,
        gcp_project_id="centagging",
        vertex_ai_location="global",
        gemini_vlm_model="gemini-test",
        gemini_embedding_model="embedding-test",
        mvp_login_id="test-user",
        mvp_login_password="test-password",
        image_storage_root="uploads",
        sku_image_root="data/images",
        database=config.DatabaseSettings(
            name="test",
            username="test",
            password="test",
            host="localhost",
            port=5432,
        ),
    )


class GenAIClientTest(unittest.TestCase):
    """Verify local Express Mode and production Vertex AI clients."""

    @mock.patch("app.core.genai_client.genai.Client")
    def test_creates_express_mode_client_for_local_use(
        self, client_mock: mock.Mock
    ) -> None:
        """Local FastAPI uses the Vertex AI Express Mode API key."""
        settings = _settings("vertex-express-key")

        genai_client.create_client(settings)

        client_mock.assert_called_once_with(
            vertexai=True,
            api_key="vertex-express-key",
        )

    @mock.patch("app.core.genai_client.genai.Client")
    def test_creates_vertex_client_without_api_key(
        self, client_mock: mock.Mock
    ) -> None:
        """The production provider uses Vertex AI ADC routing values."""
        settings = _settings()

        genai_client.create_client(settings)

        client_mock.assert_called_once_with(
            vertexai=True,
            project="centagging",
            location="global",
        )

    def test_rejects_missing_vertex_configuration(self) -> None:
        """Missing both Express Mode and ADC routing fails early."""
        settings = dataclasses.replace(
            _settings(),
            gcp_project_id="",
        )

        with self.assertRaisesRegex(ValueError, "VERTEX_API_KEY"):
            genai_client.create_client(settings)
