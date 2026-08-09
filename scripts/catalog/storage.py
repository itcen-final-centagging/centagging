"""카탈로그 파이프라인의 파일 경로와 JSON 입출력 도우미.

진입점(`build_sku_json`, `vlm_assist`)이 저마다 경로를 다시 계산하지 않도록
경로 상수와 읽기·쓰기 함수를 한곳에 모아 둔다.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

# 이 파일(scripts/catalog/storage.py) 기준 두 단계 위가 저장소 루트다.
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]

CRAWL_DIR = PROJECT_ROOT / "resource" / "crawl"
CATALOG_DIR = PROJECT_ROOT / "data" / "catalog"

# 사람이 확정한 속성값. 코드와 같은 폴더에 두고 함께 리뷰한다.
VERIFIED_PATH = pathlib.Path(__file__).with_name("verified_attrs.json")

VLM_PATH = CATALOG_DIR / "draft" / "vlm_assist.json"
DRAFT_PATH = CATALOG_DIR / "draft" / "metadata_draft.json"
OUTPUT_PATH = CATALOG_DIR / "answer" / "sku.json"


def load_json(path: pathlib.Path, default: Any) -> Any:
    """JSON 파일을 읽되 파일이 없으면 기본값을 돌려준다.

    Args:
        path: 읽을 JSON 파일 경로입니다.
        default: 파일이 없을 때 돌려줄 기본값입니다.

    Returns:
        파싱된 JSON 값 또는 `default`입니다.
    """
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def dump_json(path: pathlib.Path, payload: Any) -> None:
    """UTF-8 JSON으로 저장한다. 상위 폴더가 없으면 만든다.

    Args:
        path: 저장할 파일 경로입니다.
        payload: 직렬화할 값입니다.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")


def load_products(crawl_dir: pathlib.Path = CRAWL_DIR) -> list[dict]:
    """크롤링 폴더에서 product.json을 모두 읽는다.

    Args:
        crawl_dir: `resource/crawl` 경로입니다.

    Returns:
        goods_id 오름차순으로 정렬된 상품 딕셔너리 목록입니다.
    """
    products = []
    for path in sorted(crawl_dir.glob("*/product.json")):
        with path.open(encoding="utf-8") as file:
            products.append(json.load(file))
    return sorted(products, key=lambda item: item.get("goods_id", 0))
