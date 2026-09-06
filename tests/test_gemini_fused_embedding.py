"""Gemini 융합 임베딩 호출 계약 테스트입니다."""

import io
import types as python_types
import unittest.mock

from PIL import Image

from app.core import config
from app.services import gemini_service


def _settings() -> config.Settings:
    """외부 호출 없이 GeminiService를 생성할 테스트 설정입니다."""
    return config.Settings(
        gemini_api_key="test-key",
        gemini_vlm_model="gemini-test",
        gemini_embedding_model="embedding-test",
        mvp_login_id="",
        mvp_login_password="",
        image_storage_root="uploads",
        sku_image_root="data/images",
        database=config.DatabaseSettings(
            name="",
            username="",
            password="",
            host="",
            port=5432,
        ),
    )


def test_embed_fused_sends_text_rgb_and_grayscale_in_order() -> None:
    """메타 텍스트, RGB PNG, 그레이 PNG를 한 요청으로 보낸다."""
    client = unittest.mock.Mock()
    client.models.embed_content.return_value = python_types.SimpleNamespace(
        embeddings=[python_types.SimpleNamespace(values=[0.1, 0.2])]
    )
    image = Image.new("RGB", (2, 1))
    image.putdata([(255, 0, 0), (0, 255, 0)])
    service = gemini_service.GeminiService(_settings())

    with unittest.mock.patch.object(
        gemini_service.genai_client,
        "create_client",
        return_value=client,
    ):
        result = service.embed_fused(image, "카테고리: 의자")

    assert result == [0.1, 0.2]
    call = client.models.embed_content.call_args
    assert call.kwargs["model"] == "embedding-test"
    contents = call.kwargs["contents"]
    assert contents[0] == "상품 메타데이터:\n카테고리: 의자"
    assert len(contents) == 3
    assert contents[1].inline_data.mime_type == "image/png"
    assert contents[2].inline_data.mime_type == "image/png"

    with Image.open(io.BytesIO(contents[1].inline_data.data)) as rgb:
        assert list(rgb.convert("RGB").getdata())[0] == (255, 0, 0)
    with Image.open(io.BytesIO(contents[2].inline_data.data)) as gray:
        assert list(gray.convert("RGB").getdata()) == [
            (76, 76, 76),
            (150, 150, 150),
        ]


def test_embed_fused_rejects_empty_embedding_response() -> None:
    """Gemini가 벡터를 돌려주지 않으면 명확한 도메인 오류를 낸다."""
    client = unittest.mock.Mock()
    client.models.embed_content.return_value = python_types.SimpleNamespace(
        embeddings=[]
    )
    service = gemini_service.GeminiService(_settings())

    with unittest.mock.patch.object(
        gemini_service.genai_client,
        "create_client",
        return_value=client,
    ):
        try:
            service.embed_fused(Image.new("RGB", (1, 1)), "")
        except gemini_service.GeminiEmbeddingError as error:
            assert str(error) == "Gemini 융합 임베딩 응답이 비어 있습니다."
        else:
            raise AssertionError("빈 임베딩 응답을 허용했습니다.")
