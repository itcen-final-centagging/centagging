"""임베딩 파이프라인의 경로·환경설정 도우미.

기존 scripts/catalog/storage.py와 같은 역할을 이 파이프라인 범위에서 담당한다.
"""

from __future__ import annotations

import pathlib

from dotenv import load_dotenv

from app.core import config

# 이 파일(scripts/embedding/storage.py) 기준 두 단계 위가 저장소 루트다.
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]

SKU_JSON_PATH = PROJECT_ROOT / "data" / "catalog" / "answer" / "sku.json"
IMAGES_DIR = PROJECT_ROOT / "data" / "images"

load_dotenv(PROJECT_ROOT / ".env", override=True)


def get_settings() -> config.Settings:
    """환경변수에서 애플리케이션 설정(Gemini·DB)을 읽는다."""
    return config.get_settings()


def main_image_path(sku_id: int) -> pathlib.Path | None:
    """SKU의 대표(MAIN) 이미지 경로를 찾는다.

    `data/images/{sku_id}/main.*` 형태만 다룬다.
    ANGLE·DETAIL·STYLING 등 추가 이미지 타입은 아직 다루지 않는다.

    Args:
        sku_id: sku_catalog.sku_id입니다.

    Returns:
        이미지 파일 경로입니다. 폴더나 파일이 없으면 None입니다.
    """
    folder = IMAGES_DIR / str(sku_id)
    if not folder.is_dir():
        return None
    for candidate in sorted(folder.glob("main.*")):
        if candidate.is_file():
            return candidate
    return None
