"""환경변수 기반 애플리케이션 설정입니다. / Environment-based application settings."""

import dataclasses
import os


def _env_bool(name: str, default: bool) -> bool:
    """환경 변수의 불리언 값을 읽습니다."""
    return os.getenv(name, str(default)).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


@dataclasses.dataclass(frozen=True)
class DatabaseSettings:
    """PostgreSQL connection settings."""

    name: str
    username: str
    password: str = dataclasses.field(repr=False)
    host: str
    port: int


@dataclasses.dataclass(frozen=True)
# 런타임 설정값을 평면 구조로 관리합니다.
class Settings:  # pylint: disable=too-many-instance-attributes
    """Application settings read from the runtime environment."""

    gemini_api_key: str
    gemini_vlm_model: str
    gemini_embedding_model: str
    mvp_login_id: str
    database: DatabaseSettings
    image_storage_root: str
    sku_image_root: str
    mvp_login_password: str = dataclasses.field(repr=False)
    vertex_api_key: str = dataclasses.field(default="", repr=False)
    gcp_project_id: str = ""
    vertex_ai_location: str = "global"
    gemini_rerank_model: str = "gemini-2.5-flash-lite"
    image_preprocess_enabled: bool = True
    embedding_pipeline_version: str = "2026-08-21.1"
    similar_sku_max_cosine_distance: float = 0.35
    image_max_side: int = 1024
    quality_blur_laplacian_threshold: float = 180.0
    quality_denoise_h: int = 3
    quality_unsharp_amount: float = 0.30
    quality_unsharp_sigma: float = 1.0
    lighting_dark_pixel_value: int = 32
    lighting_moderate_median: float = 60.0
    lighting_severe_median: float = 30.0
    lighting_moderate_dark_fraction: float = 0.35
    lighting_severe_dark_fraction: float = 0.60
    lighting_moderate_gamma: float = 0.80
    lighting_severe_gamma: float = 0.60
    lighting_clahe_clip_limit: float = 1.8
    lighting_clahe_grid_size: int = 8


def get_settings() -> Settings:
    """컨테이너 또는 로컬 환경변수에서 애플리케이션 설정을 읽습니다.

    Returns:
        AI, 로그인, PostgreSQL 설정이 담긴 Settings 객체입니다.
    """
    return Settings(
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        vertex_api_key=os.getenv("VERTEX_API_KEY", ""),
        gcp_project_id=os.getenv("GCP_PROJECT_ID", ""),
        vertex_ai_location=os.getenv("VERTEX_AI_LOCATION") or "global",
        gemini_vlm_model=os.getenv("GEMINI_VLM_MODEL", "gemini-3.5-flash"),
        gemini_embedding_model=os.getenv(
            "GEMINI_EMBEDDING_MODEL", "gemini-embedding-2"
        ),
        gemini_rerank_model=os.getenv(
            "GEMINI_RERANK_MODEL", "gemini-2.5-flash-lite"
        ),
        image_preprocess_enabled=_env_bool("IMAGE_PREPROCESS_ENABLED", True),
        embedding_pipeline_version=os.getenv(
            "EMBEDDING_PIPELINE_VERSION", "2026-08-21.1"
        ),
        similar_sku_max_cosine_distance=float(
            os.getenv("SIMILAR_SKU_MAX_COSINE_DISTANCE", "0.35")
        ),
        image_max_side=int(os.getenv("IMAGE_MAX_SIDE", "1024")),
        quality_blur_laplacian_threshold=float(
            os.getenv("QUALITY_BLUR_LAPLACIAN_THRESHOLD", "180")
        ),
        quality_denoise_h=int(os.getenv("QUALITY_DENOISE_H", "3")),
        quality_unsharp_amount=float(
            os.getenv("QUALITY_UNSHARP_AMOUNT", "0.30")
        ),
        quality_unsharp_sigma=float(os.getenv("QUALITY_UNSHARP_SIGMA", "1.0")),
        lighting_dark_pixel_value=int(
            os.getenv("LIGHTING_DARK_PIXEL_VALUE", "32")
        ),
        lighting_moderate_median=float(
            os.getenv("LIGHTING_MODERATE_MEDIAN", "60")
        ),
        lighting_severe_median=float(os.getenv("LIGHTING_SEVERE_MEDIAN", "30")),
        lighting_moderate_dark_fraction=float(
            os.getenv("LIGHTING_MODERATE_DARK_FRACTION", "0.35")
        ),
        lighting_severe_dark_fraction=float(
            os.getenv("LIGHTING_SEVERE_DARK_FRACTION", "0.60")
        ),
        lighting_moderate_gamma=float(
            os.getenv("LIGHTING_MODERATE_GAMMA", "0.80")
        ),
        lighting_severe_gamma=float(os.getenv("LIGHTING_SEVERE_GAMMA", "0.60")),
        lighting_clahe_clip_limit=float(
            os.getenv("LIGHTING_CLAHE_CLIP_LIMIT", "1.8")
        ),
        lighting_clahe_grid_size=int(
            os.getenv("LIGHTING_CLAHE_GRID_SIZE", "8")
        ),
        mvp_login_id=os.getenv("MVP_LOGIN_ID", ""),
        mvp_login_password=os.getenv("MVP_LOGIN_PASSWORD", ""),
        image_storage_root=os.getenv("IMAGE_STORAGE_ROOT", "uploads"),
        sku_image_root=os.getenv("SKU_IMAGE_ROOT", "data/images"),
        database=DatabaseSettings(
            name=os.getenv("POSTGRES_DB", "centagging"),
            username=os.getenv("POSTGRES_USER", "centagging"),
            password=os.getenv("POSTGRES_PASSWORD", "change-me"),
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
        ),
    )
