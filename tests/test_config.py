"""융합 임베딩 파이프라인 설정 테스트입니다."""

import os
import unittest.mock

from app.core import config


def test_fused_pipeline_settings_have_stable_defaults() -> None:
    """전처리 파이프라인은 명시적인 기본값을 제공한다."""
    with unittest.mock.patch.dict(os.environ, {}, clear=True):
        settings = config.get_settings()

    assert settings.image_preprocess_enabled is True
    assert settings.embedding_pipeline_version == "2026-08-21.1"
    assert settings.image_max_side == 1024
    assert settings.quality_blur_laplacian_threshold == 180.0
    assert settings.similar_sku_max_cosine_distance == 0.35
    assert settings.lighting_moderate_median == 60.0
    assert settings.lighting_severe_median == 30.0


def test_fused_pipeline_settings_read_environment_overrides() -> None:
    """운영 환경에서 전처리 기준을 조정할 수 있다."""
    overrides = {
        "IMAGE_PREPROCESS_ENABLED": "false",
        "EMBEDDING_PIPELINE_VERSION": "2026-08-21.2",
        "IMAGE_MAX_SIDE": "768",
        "QUALITY_BLUR_LAPLACIAN_THRESHOLD": "200",
        "LIGHTING_SEVERE_GAMMA": "0.55",
        "SIMILAR_SKU_MAX_COSINE_DISTANCE": "0.30",
    }
    with unittest.mock.patch.dict(os.environ, overrides, clear=True):
        settings = config.get_settings()

    assert settings.image_preprocess_enabled is False
    assert settings.embedding_pipeline_version == "2026-08-21.2"
    assert settings.image_max_side == 768
    assert settings.quality_blur_laplacian_threshold == 200.0
    assert settings.lighting_severe_gamma == 0.55
    assert settings.similar_sku_max_cosine_distance == 0.30
