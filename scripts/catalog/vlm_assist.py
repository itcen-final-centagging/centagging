"""VLM 보조 — 규칙으로 못 채운 이미지 기반 속성만 보완한다.

처리 순서:

1. 원본 데이터 + 규칙으로 메타데이터 초안을 생성한다.
2. 초안에서 값이 None인 속성만 확인한다.
3. 그중 이미지에서 확인 가능한 속성만 VLM에게 요청한다.
4. 메인 이미지 1장만 VLM에 전달한다.
5. 이미지에서 확인할 수 없으면 null로 처리한다.
6. 허용값에 없는 응답은 저장하지 않는다.

VLM은 상품의 전체 메타데이터를 추출하지 않는다.

VLM에게 맡기지 않는 정보:
- color
- brand
- selling_price
- size
- length
- width
- depth
- height
- material

실행:

    python -m scripts.catalog.vlm_assist
    python -m scripts.catalog.vlm_assist 1341125
    python -m scripts.catalog.vlm_assist --limit 10
    python -m scripts.catalog.vlm_assist --dry-run
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import json
import os
import pathlib
from typing import Any

from dotenv import load_dotenv

from app.core import catalog_spec
from scripts.catalog import metadata_builder, storage

# 환경 설정

load_dotenv(
    storage.PROJECT_ROOT / ".env",
    override=True,
)

MODEL_NAME = os.getenv(
    "GEMINI_VLM_MODEL",
    "gemini-3.5-flash",
)

# 이미지 설정

# 상품당 메인 이미지 1장만 사용한다.
MAX_IMAGES = 1

IMAGE_SUFFIXES = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}

# VLM 제외 속성

# 이미지로 정확하게 판단하기 어렵거나
# 굳이 VLM에게 맡길 필요가 없는 속성이다.
EXCLUDED_ATTRS = {
    "color",
    "brand",
    "selling_price",
    "size",
    "length",
    "width",
    "depth",
    "height",
    "material",
}

# 카테고리별 이미지 판정 가능 속성
# ---------------------------------------------------------------------------

# "이미지를 보고 형태/구조를 확인할 수 있는 속성"만 VLM에게 요청한다.
#
# style / pattern은 주관적인 판단이 들어갈 수 있으므로
# 여기서는 제외한다.
#
# material도 사진만 보고 확정하기 어려우므로 제외한다.
#
# 즉 VLM의 역할을 최대한 좁혀서
# "상품의 형태/구조/존재 여부"만 확인하도록 한다.

IMAGE_INFERABLE_ATTRS: dict[str, set[str]] = {
    "침대": {
        "bed_type",
        "has_headboard",
        "frame_type",
        "wood_tone",
        "head_type",
        "base_type",
        "product_type",
    },

    "매트리스": {
        # 현재 매트리스는 이미지에서 안정적으로 판단할
        # 구조 속성이 거의 없으므로 비워둔다.
    },

    "테이블·식탁·책상": {
        "shape",
        "leg_type",
        "has_storage",
        "wood_tone",
        "seating_capacity",
    },

    "소파": {
        "sofa_type",
        "has_legs",
        "has_armrest",
        "has_headrest",
        "has_stool",
    },

    "서랍·수납장": {
        "storage_type",
        "drawer_count",
        "wood_tone",
        "door_type",
        "has_legs",
        "has_wheels",
        "has_drawer",
    },

    "거실장·TV장": {
        "tv_stand_type",
        "level_count",
        "has_legs",
    },

    "선반": {
        "shelf_type",
        "shelf_count",
    },

    "진열장·책장": {
        "storage_type",
        "door_type",
    },

    "의자": {
        "chair_type",
        "has_wheels",
        "has_backrest",
        "has_armrest",
    },

    "행거·옷장": {
        "wardrobe_type",
        "layout_type",
        "mobility_type",
        "door_type",
        "storage_features",
    },

    "거울": {
        "installation_type",
        "shape",
        "has_frame",
    },

    "화장대·콘솔": {
        "vanity_type",
        "has_mirror",
        "storage_type",
    },
}

# VLM Prompt

PROMPT = """상품의 메인 이미지를 보고 아래 속성만 판정하세요.

상품의 카테고리와 소분류는 이미 확정되어 있습니다.

카테고리: {category}
소분류: {sub_category}

## 이미 규칙으로 확인된 정보

{known}

## 이미지에서 확인할 속성과 허용값

{targets}

## 판단 규칙

1. 반드시 제시된 허용값 중 하나만 선택하세요.
2. 이미지에서 명확하게 확인할 수 없는 경우 value는 null로 하세요.
3. 추측하지 마세요.
4. 상품명이나 일반적인 상품 지식으로 판단하지 마세요.
5. 이미지에서 실제로 보이는 형태와 구조만 근거로 판단하세요.
6. 색상, 브랜드, 가격, 사이즈, 치수, 재질은 판단하지 마세요.
7. 존재 여부 속성은 허용값에 있는 "있음" 또는 "없음"만 사용하세요.
8. 판단할 수 없으면 "모름"을 사용하지 말고 반드시 null을 사용하세요.
9. confidence는 0.0~1.0 사이로 작성하세요.
10. reason에는 이미지에서 실제로 확인한 근거만 간단히 작성하세요.

## 응답 형식

반드시 JSON 객체 하나만 반환하세요.

{{
  "속성명": {{
    "value": "허용값 또는 null",
    "confidence": 0.0,
    "reason": "이미지에서 확인한 근거"
  }}
}}
"""


# 이미지 로드

def load_images(
        goods_dir: pathlib.Path,
        limit: int = MAX_IMAGES,
) -> list[str]:
    """상품의 메인 이미지 1장을 반환한다."""

    image_dir = goods_dir / "images"

    main_image = image_dir / "000_main.jpg"

    if not main_image.exists():
        raise FileNotFoundError(
            f"메인 이미지가 없습니다: {main_image}"
        )

    return [str(main_image)]


# VLM 대상 선정

def plan_targets(
        product: dict,
) -> tuple[
    str | None,
    str | None,
    dict[str, Any],
    list[str],
]:
    """규칙으로 채우지 못한 이미지 기반 속성만 VLM 대상으로 선정한다.

    조건:

    1. 카탈로그에 정의된 속성이어야 한다.
    2. 이미지로 확인 가능한 속성이어야 한다.
    3. 제외 속성이 아니어야 한다.
    4. 현재 값이 None이어야 한다.

    사람 검수값은 사용하지 않는다.
    """

    category, sub_category, _warnings = (
        metadata_builder.resolve_category(product)
    )

    if category is None:
        return None, None, {}, []

    # 원본 데이터 + 규칙 기반 초안
    draft = metadata_builder.build_draft(
        product,
        category,
        sub_category,
    )

    # 현재까지 알고 있는 값
    known = {
        name: field["value"]
        for name, field in draft.items()
    }

    # 해당 카테고리에서 이미지로 판단 가능한 속성
    image_attrs = IMAGE_INFERABLE_ATTRS.get(
        category,
        set(),
    )

    targets: list[str] = []

    for key in catalog_spec.attribute_names(category):

        # 이미지로 판단하지 않는 속성
        if key not in image_attrs:
            continue

        # 명시적으로 제외한 속성
        if key in EXCLUDED_ATTRS:
            continue

        # 이미 규칙으로 값이 있으면 VLM에게 묻지 않는다.
        #
        # None인 경우에만 VLM 대상으로 선정한다.
        if known.get(key) is not None:
            continue

        targets.append(key)

    return (
        category,
        sub_category,
        known,
        targets,
    )


# Prompt 생성

def build_prompt(
        category: str,
        sub_category: str | None,
        known: dict[str, Any],
        targets: list[str],
) -> str:
    """VLM에 전달할 프롬프트를 생성한다."""

    allowed = {
        key: catalog_spec.allowed_values(
            category,
            key,
        )
        for key in targets
    }

    return PROMPT.format(
        category=category,
        sub_category=sub_category or "미상",
        known=json.dumps(
            known,
            ensure_ascii=False,
            indent=2,
        ),
        targets=json.dumps(
            allowed,
            ensure_ascii=False,
            indent=2,
        ),
    )


# Gemini 호출

def call_gemini(
        prompt: str,
        image_paths: list[str],
) -> dict[str, Any]:
    """Gemini VLM을 1회 호출하고 JSON 응답을 반환한다."""

    from google import genai
    from PIL import Image

    api_key = os.getenv(
        "VERTEX_API_KEY",
        "",
    ).strip()

    if not api_key:
        raise RuntimeError(
            "VERTEX_API_KEY가 설정되지 않았습니다."
        )

    client = genai.Client(
        vertexai=True,
        api_key=api_key,
    )

    images = [
        Image.open(path)
        for path in image_paths
    ]

    contents: list[Any] = [
        prompt,
        *images,
    ]

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
            config={
                "response_mime_type": "application/json",
            },
        )

        if not response.text:
            raise RuntimeError(
                "Gemini 응답이 비어 있습니다."
            )

        parsed: dict[str, Any] = json.loads(
            response.text
        )

        return parsed

    finally:
        for image in images:
            image.close()


# VLM 응답 검증

def filter_response(
        response: dict[str, Any],
        category: str,
        targets: list[str],
) -> dict[str, Any]:
    """VLM 응답에서 검증된 값만 저장한다.

    검증:

    - 요청하지 않은 속성 제거
    - null 제거
    - 허용값 외의 값 제거
    - confidence 0.85 상한
    """

    picked: dict[str, Any] = {}

    for key, payload in response.items():

        # 요청하지 않은 속성은 버린다.
        if key not in targets:
            continue

        if isinstance(payload, dict):
            value = payload.get("value")
            confidence = payload.get(
                "confidence",
                0.5,
            )
            reason = payload.get(
                "reason"
            )
        else:
            value = payload
            confidence = 0.5
            reason = None

        # VLM이 판단하지 못한 경우
        # 최종 데이터에서는 그대로 null로 남기면 되므로
        # VLM 보조 결과에는 저장하지 않는다.
        if value is None:
            continue

        # 허용값 확인
        allowed = catalog_spec.allowed_values(
            category,
            key,
        )

        if allowed and value not in allowed:
            continue

        # confidence 방어
        try:
            confidence = float(
                confidence
            )
        except (
                TypeError,
                ValueError,
        ):
            confidence = 0.5

        # VLM 결과는 초안이므로 자동 채택되지 않도록
        # confidence 상한을 둔다.
        confidence = max(
            0.0,
            min(
                confidence,
                0.85,
            ),
        )

        picked[key] = {
            "value": value,
            "confidence": confidence,
            "reason": reason,
        }

    return picked


# 대상 상품 폴더

def target_dirs(
        goods_ids: list[str],
) -> list[pathlib.Path]:
    """처리할 상품 폴더를 반환한다."""

    if goods_ids:
        return [
            storage.CRAWL_DIR / goods_id
            for goods_id in goods_ids
        ]

    return sorted(
        path
        for path in storage.CRAWL_DIR.iterdir()
        if path.is_dir()
    )


# 처리 결과

@dataclasses.dataclass(frozen=True)
class AskResult:
    """상품 1건의 VLM 보조 처리 결과."""

    payload: dict[str, Any] | None = None

    # 규칙만으로 충분하거나
    # 이미지 기반 VLM 대상이 없었던 경우
    enough: bool = False


# 상품 1건 처리

def ask_product(
        goods_dir: pathlib.Path,
        dry_run: bool,
) -> AskResult:
    """상품 1건에 대해 필요한 이미지 속성만 VLM으로 확인한다."""

    key = goods_dir.name

    product_path = goods_dir / "product.json"

    if not product_path.exists():
        print(
            f"[{key}] product.json 없음 — 건너뜀"
        )
        return AskResult()

    with product_path.open(
            encoding="utf-8"
    ) as file:
        product = json.load(file)

    (
        category,
        sub_category,
        known,
        targets,
    ) = plan_targets(product)

    if category is None:
        print(
            f"[{key}] 카테고리 매핑 실패 — 건너뜀"
        )
        return AskResult()

    if not targets:
        print(
            f"[{key}] "
            "이미지로 보완할 속성 없음"
        )
        return AskResult(
            enough=True,
        )

    print(
        f"[{key}] "
        f"물어볼 속성 {len(targets)}개: "
        f"{', '.join(targets)}"
    )

    if dry_run:
        return AskResult()

    try:
        response = call_gemini(
            build_prompt(
                category,
                sub_category,
                known,
                targets,
            ),
            load_images(goods_dir),
        )

    except Exception as error:
        print(
            f"  실패: "
            f"{type(error).__name__}: {error}"
        )
        return AskResult()

    attributes = filter_response(
        response,
        category,
        targets,
    )

    return AskResult(
        payload={
            "asked": targets,
            "model": MODEL_NAME,
            "created_at": (
                datetime.datetime.now(
                    datetime.timezone.utc
                ).isoformat()
            ),
            "attributes": attributes,
        }
    )


# CLI
def parse_args() -> argparse.Namespace:
    """명령행 인자를 읽는다."""

    parser = argparse.ArgumentParser(
        description=(
            "규칙으로 채우지 못한 "
            "이미지 기반 속성만 "
            "Gemini에게 물어본다."
        )
    )

    parser.add_argument(
        "goods_ids",
        nargs="*",
        help=(
            "대상 goods_id "
            "(생략하면 전체)"
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help=(
            "최대 VLM 호출 수 "
            "(0이면 제한 없음)"
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "호출하지 않고 "
            "무엇을 물어볼지만 출력"
        ),
    )

    return parser.parse_args()


# Main

def main() -> None:
    """미해결 이미지 속성이 있는 상품만 VLM 보조를 수행한다."""

    args = parse_args()

    # 기존 VLM 결과
    results = storage.load_json(
        storage.VLM_PATH,
        {},
    )

    calls = 0
    skipped = 0

    for goods_dir in target_dirs(
            args.goods_ids
    ):

        # 이미 VLM 처리한 상품은 다시 호출하지 않는다.
        if goods_dir.name in results:
            print(
                f"[{goods_dir.name}] "
                "이미 처리됨 — 건너뜀"
            )
            continue

        # 호출 제한
        if (
                args.limit
                and calls >= args.limit
        ):
            print(
                f"호출 상한({args.limit}) 도달 — "
                "남은 상품은 다음 실행으로"
            )
            break

        result = ask_product(
            goods_dir,
            args.dry_run,
        )

        skipped += int(
            result.enough
        )

        if result.payload is None:
            continue

        # VLM 결과 저장
        results[goods_dir.name] = (
            result.payload
        )

        calls += 1

        # 성공한 상품마다 즉시 저장
        storage.dump_json(
            storage.VLM_PATH,
            results,
        )

        print(
            "  응답 저장 완료 "
            f"{len(result.payload['attributes'])}개"
        )

    saved_path = (
        storage.VLM_PATH.relative_to(
            storage.PROJECT_ROOT
        )
    )

    print(
        f"VLM 호출 {calls}회 / "
        f"VLM 보완 불필요 {skipped}건"
    )

    print(
        f"저장 파일: {saved_path}"
    )


# Entry point
if __name__ == "__main__":
    main()
