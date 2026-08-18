"""임베딩 파이프라인의 경로·환경설정 도우미.

기존 scripts/catalog/storage.py와 같은 역할을 이 파이프라인 범위에서 담당한다.
"""

from __future__ import annotations

import dataclasses
import pathlib
import re

from dotenv import load_dotenv

from app.core import config

# 이 파일(scripts/embedding/storage.py) 기준 두 단계 위가 저장소 루트다.
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]

SKU_JSON_PATH = PROJECT_ROOT / "data" / "catalog" / "answer" / "sku.json"
IMAGES_DIR = PROJECT_ROOT / "data" / "images"
INCOMING_IMAGES_DIR = IMAGES_DIR / "incomming"

load_dotenv(PROJECT_ROOT / ".env", override=True)


def get_settings() -> config.Settings:
    """환경변수에서 애플리케이션 설정(Gemini·DB)을 읽는다."""
    return config.get_settings()


# ============================================================
# data/images/incomming 파일명 규칙
# ============================================================
#
#   {goods_id}_{sku_code}_{color}_{type}_{sequence}.{ext}
#
#   예: 13147_DRW-B3C60F7D_WHITE_m_001.jpg
#
#   type 토큰은 sku_image.image_type(스키마의 CHECK (MAIN|ANGLE))에
#   대응한다. 모르는 토큰이 붙은 파일은 조용히 건너뛴다 — 파일명 자체의
#   규칙 위반·오탈자 검수는 scripts.catalog.validate_sku_images가 맡는다.

IMAGE_TYPE_TOKENS: dict[str, str] = {
    "m": "MAIN",
    "a": "ANGLE",
}

_FILENAME_PATTERN = re.compile(
    r"^(?P<goods_id>\d+)_(?P<sku_code>[A-Za-z0-9\-]+)_"
    r"(?P<color>[A-Za-z]+)_(?P<type_token>[A-Za-z]+)_"
    r"(?P<sequence>\d{3})\.(?P<ext>[A-Za-z]+)$"
)


@dataclasses.dataclass(frozen=True)
class IncomingImage:
    """data/images/incomming의 파일명 1건을 파싱한 결과입니다."""

    path: pathlib.Path
    goods_id: str
    sku_code: str
    color: str
    image_type: str
    sequence: str


def list_incoming_images() -> list[IncomingImage]:
    """data/images/incomming을 스캔해 파일명 규칙에 맞는 이미지만 돌려준다.

    Returns:
        파일명 규칙과 image_type 토큰이 유효한 이미지 목록입니다.
        goods_id_sku_code_color_sequence 순 정렬입니다.
    """
    if not INCOMING_IMAGES_DIR.is_dir():
        return []

    images: list[IncomingImage] = []
    for path in sorted(INCOMING_IMAGES_DIR.glob("*")):
        if not path.is_file():
            continue

        match = _FILENAME_PATTERN.match(path.name)
        if match is None:
            continue

        image_type = IMAGE_TYPE_TOKENS.get(match.group("type_token").lower())
        if image_type is None:
            continue

        images.append(
            IncomingImage(
                path=path,
                goods_id=match.group("goods_id"),
                sku_code=match.group("sku_code"),
                color=match.group("color"),
                image_type=image_type,
                sequence=match.group("sequence"),
            )
        )
    return images
