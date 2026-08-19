"""환경변수 기반 애플리케이션 설정입니다. / Environment-based application settings."""

import dataclasses
import os


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
