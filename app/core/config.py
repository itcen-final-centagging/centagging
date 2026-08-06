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
class Settings:
    """Application settings read from the runtime environment."""

    gemini_api_key: str
    gemini_vlm_model: str
    gemini_embedding_model: str
    mvp_login_id: str
    database: DatabaseSettings
    mvp_login_password: str = dataclasses.field(repr=False)
    session_secret: str = dataclasses.field(repr=False, default="")


def get_settings() -> Settings:
    """컨테이너 또는 로컬 환경변수에서 애플리케이션 설정을 읽습니다.

    Returns:
        AI, 로그인, PostgreSQL 설정이 담긴 Settings 객체입니다.
    """
    return Settings(
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        gemini_vlm_model=os.getenv("GEMINI_VLM_MODEL", "gemini-3.5-flash"),
        gemini_embedding_model=os.getenv(
            "GEMINI_EMBEDDING_MODEL", "gemini-embedding-2"
        ),
        mvp_login_id=os.getenv("LOGIN_ID") or os.getenv("MVP_LOGIN_ID", ""),
        mvp_login_password=os.getenv("LOGIN_PASSWORD") or os.getenv("MVP_LOGIN_PASSWORD", ""),
        session_secret=os.getenv("SESSION_SECRET", ""),
        database=DatabaseSettings(
            name=os.getenv("POSTGRES_DB", "centagging"),
            username=os.getenv("POSTGRES_USER", "centagging"),
            password=os.getenv("POSTGRES_PASSWORD", "change-me"),
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
        ),
    )
