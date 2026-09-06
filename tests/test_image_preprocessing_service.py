"""융합 임베딩용 공통 이미지 전처리 Module 테스트입니다."""

import dataclasses

from PIL import Image

from app.core import config
from app.services import image_preprocessing_service


def _settings() -> config.Settings:
    """외부 환경과 독립적인 전처리 설정을 생성합니다."""
    return config.Settings(
        gemini_api_key="",
        gemini_vlm_model="",
        gemini_embedding_model="",
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


def test_bright_sharp_image_is_left_unchanged() -> None:
    """밝고 선명한 입력은 전처리 픽셀 변경 없이 통과한다."""
    source = Image.new("L", (64, 64))
    source.putdata(
        [255 if (x + y) % 2 else 180 for y in range(64) for x in range(64)]
    )

    result = image_preprocessing_service.preprocess_for_embedding(
        source.convert("RGB"), _settings()
    )

    assert result.image.tobytes() == source.convert("RGB").tobytes()
    assert result.diagnostics.quality.applied is False
    assert result.diagnostics.lighting.applied is False
    assert result.diagnostics.resized is False


def test_dark_image_is_brightened_without_changing_size() -> None:
    """어두운 crop은 조명 보정 뒤에도 원본 크기를 유지한다."""
    source = Image.new("RGB", (32, 24), (50, 40, 30))

    result = image_preprocessing_service.preprocess_for_embedding(
        source, _settings()
    )

    assert result.image.size == source.size
    assert result.diagnostics.lighting.applied is True
    assert sum(result.image.convert("L").histogram()[61:]) > sum(
        source.convert("L").histogram()[61:]
    )


def test_blurry_image_receives_local_quality_recovery() -> None:
    """흐린 crop에만 로컬 노이즈 제거와 선명화를 적용한다."""
    source = Image.new("RGB", (64, 48), (80, 70, 60))

    result = image_preprocessing_service.preprocess_for_embedding(
        source, _settings()
    )

    assert result.image.size == source.size
    assert result.diagnostics.quality.applied is True
    assert result.diagnostics.quality.denoise_h == 3
    assert result.diagnostics.quality.unsharp_amount == 0.30


def test_preprocessing_can_be_disabled() -> None:
    """기능 플래그를 끄면 저화질·조명 보정과 리사이즈를 적용하지 않는다."""
    source = Image.new("RGB", (2048, 512), (20, 15, 10))
    settings = dataclasses.replace(_settings(), image_preprocess_enabled=False)

    result = image_preprocessing_service.preprocess_for_embedding(
        source, settings
    )

    assert result.image.tobytes() == source.tobytes()
    assert result.image.size == source.size
    assert result.diagnostics.quality.applied is False
    assert result.diagnostics.lighting.applied is False


def test_image_is_limited_to_configured_max_side() -> None:
    """긴 변만 설정값에 맞춰 축소하고 종횡비는 유지한다."""
    source = Image.new("RGB", (2048, 512), (180, 160, 140))

    result = image_preprocessing_service.preprocess_for_embedding(
        source, _settings()
    )

    assert result.image.size == (1024, 256)
    assert result.diagnostics.resized is True
