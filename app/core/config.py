"""환경변수 기반 애플리케이션 설정입니다. / Environment-based application settings."""

import dataclasses
import os


@dataclasses.dataclass(frozen=True)
class Settings:
    """실행 환경에서 읽는 설정값입니다. / Settings read from the runtime environment."""

    gemini_api_key: str
    gemini_vlm_model: str
    gemini_embedding_model: str


def get_settings() -> Settings:
    """컨테이너 또는 로컬 환경변수에서 Gemini 설정을 읽습니다.

    Returns:
        Gemini API 키와 모델명이 담긴 Settings 객체입니다.
    """
    return Settings(
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        gemini_vlm_model=os.getenv("GEMINI_VLM_MODEL", "gemini-3.5-flash"),
        gemini_embedding_model=os.getenv(
            "GEMINI_EMBEDDING_MODEL", "gemini-embedding-2"
        ),
    )
