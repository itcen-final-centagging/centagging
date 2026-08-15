"""Google Gen AI 런타임 클라이언트 선택 정책 테스트입니다."""

import unittest
from unittest import mock

from app.core import config, genai_client


def _settings(
    *,
    vertex_api_key: str = "",
    gcp_project_id: str = "",
    vertex_ai_location: str = "global",
    gemini_api_key: str = "",
) -> config.Settings:
    """인증 방식별 변경이 가능한 테스트 설정을 생성합니다."""
    settings = config.Settings(
        gemini_api_key=gemini_api_key,
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
        vertex_api_key=vertex_api_key,
        gcp_project_id=gcp_project_id,
        vertex_ai_location=vertex_ai_location,
    )
    return settings


class GenAIClientTest(unittest.TestCase):
    """Express Mode, ADC, Developer API 선택 순서를 검증합니다."""

    @mock.patch("app.core.genai_client.genai.Client")
    def test_prefers_vertex_express_mode_key(
        self, client_mock: mock.Mock
    ) -> None:
        """Vertex API 키가 있으면 다른 인증 설정보다 우선합니다."""
        settings = _settings(
            vertex_api_key="vertex-key",
            gcp_project_id="centagging",
            gemini_api_key="developer-key",
        )

        genai_client.create_client(settings)

        client_mock.assert_called_once_with(
            vertexai=True,
            api_key="vertex-key",
        )

    @mock.patch("app.core.genai_client.genai.Client")
    def test_uses_vertex_adc_for_production(
        self, client_mock: mock.Mock
    ) -> None:
        """GCP 프로젝트가 있으면 VM 서비스 계정 ADC를 사용합니다."""
        settings = _settings(
            gcp_project_id="centagging",
            vertex_ai_location="global",
            gemini_api_key="developer-key",
        )

        genai_client.create_client(settings)

        client_mock.assert_called_once_with(
            vertexai=True,
            project="centagging",
            location="global",
        )

    @mock.patch("app.core.genai_client.genai.Client")
    def test_keeps_gemini_developer_api_fallback(
        self, client_mock: mock.Mock
    ) -> None:
        """기존 로컬 GEMINI_API_KEY 환경은 계속 지원합니다."""
        settings = _settings(gemini_api_key="developer-key")

        genai_client.create_client(settings)

        client_mock.assert_called_once_with(api_key="developer-key")

    def test_rejects_missing_authentication(self) -> None:
        """어떤 인증 설정도 없으면 명확한 오류를 발생시킵니다."""
        settings = _settings()

        self.assertFalse(genai_client.is_configured(settings))
        with self.assertRaisesRegex(ValueError, "VERTEX_API_KEY"):
            genai_client.create_client(settings)


if __name__ == "__main__":
    unittest.main()
