"""VLM 보조 — 규칙으로 못 채운 속성만, 상품당 1회 물어본다.

이 모듈은 메타데이터 전체를 VLM으로 추출하지 않는다.
metadata_builder에서 원본과 규칙으로 먼저 값을 채운 뒤,
아직 값이 없는 속성만 이미지 기반으로 보완한다.

결과는 초안이다. `data/catalog/draft/vlm_assist.json`에 저장되고,
build_sku_json이 이 값을 규칙으로 못 채운 자리에만 채워 넣는다. confidence는
0.85를 넘지 못하게 잘라 두어서 자동 채택되지 않고 항상 검수를 거친다.

실행

    python -m scripts.catalog.vlm_assist              # 필요한 상품만
    python -m scripts.catalog.vlm_assist 1341125      # 특정 상품
    python -m scripts.catalog.vlm_assist --limit 10   # 호출 수 상한
    python -m scripts.catalog.vlm_assist --dry-run    # 호출 없이 계획만
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

load_dotenv(storage.PROJECT_ROOT / ".env", override=True)

# 모델 이름은 배포 환경마다 달라 .env로 주입한다. API 키는 코드에 두지 않는다.
MODEL_NAME = os.getenv("GEMINI_VLM_MODEL", "gemini-3.5-flash")

# 상품당 보낼 이미지 수 (메인 + 각도컷). 상세컷은 배너가 많아 제외한다.
MAX_IMAGES = 3

# 이미지로는 판정할 수 없는 치수 계열 속성. VLM이 추론하지 못하게 뺀다.
EXCLUDED_ATTRS = {"size", "length", "width", "depth", "height"}

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}

PROMPT = """상품 이미지를 보고 아래 속성만 판정하세요.

이 상품의 카테고리는 이미 확정되어 있습니다: {category} > {sub_category}
카테고리는 다시 판정하지 마세요.

## 이미 확정된 정보 (참고용, 다시 답하지 마세요)
{known}

## 판정할 속성과 허용값
{targets}

## 규칙
1. 허용값에 없는 값을 만들지 마세요.
2. 이미지에서 확인할 수 없으면 value를 null로 두세요. 추측 금지.
3. boolean 속성은 true 또는 false로 답하세요.
4. confidence는 0.0~1.0이며, 근거가 약하면 낮게 주세요.
5. reason에는 이미지에서 실제로 본 것만 쓰세요.

## 응답 형식 (JSON 객체 하나만)
{{
  "속성명": {{"value": 값, "confidence": 0.0, "reason": "관찰 근거"}}
}}
"""


def load_images(goods_dir: pathlib.Path, limit: int = MAX_IMAGES) -> list[str]:
    """상품 폴더에서 메인·각도 이미지를 고른다.

    Args:
        goods_dir: `resource/crawl/{goods_id}` 경로입니다.
        limit: 최대 이미지 장수입니다.

    Returns:
        이미지 경로 목록입니다.

    Raises:
        FileNotFoundError: 쓸 수 있는 이미지가 없는 경우입니다.
    """
    image_dir = goods_dir / "images"
    paths = sorted(
        path
        for path in image_dir.glob("*")
        if path.suffix.lower() in IMAGE_SUFFIXES
        and "detail" not in path.name.lower()
    )
    if not paths:
        raise FileNotFoundError(f"이미지가 없습니다: {image_dir}")
    return [str(path) for path in paths[:limit]]


def plan_targets(
    product: dict, verified: dict[str, Any]
) -> tuple[str | None, str | None, dict[str, Any], list[str]]:
    """이 상품에서 VLM에게 물어볼 속성만 골라낸다.

    원본·규칙·사람 검수로 이미 알 수 있는 속성은 빼고, 아직 값이 없는 속성만
    targets에 넣는다.

    Args:
        product: 크롤링한 product.json 딕셔너리입니다.
        verified: verified_attrs.json의 해당 상품 항목입니다.

    Returns:
        `(대분류, 소분류, 이미 아는 값, 물어볼 속성 목록)`입니다. 카테고리
        매핑에 실패하면 대분류와 소분류가 None입니다.
    """
    category, sub_category, _warnings = metadata_builder.resolve_category(
        product
    )
    if category is None:
        return None, None, {}, []

    # 원본 + 규칙으로 먼저 채운 값이 곧 "이미 아는 값"이다.
    draft = metadata_builder.build_draft(product, category, sub_category)
    known = {name: field["value"] for name, field in draft.items()}
    # 사람이 검수한 값이 있으면 그쪽을 우선한다.
    known.update(verified.get("attrs") or {})

    targets = [
        key
        for key in catalog_spec.attribute_names(category)
        if key not in known and key not in EXCLUDED_ATTRS
    ]
    return category, sub_category, known, targets


def build_prompt(
    category: str,
    sub_category: str | None,
    known: dict[str, Any],
    targets: list[str],
) -> str:
    """미해결 속성만 담은 프롬프트를 만든다.

    허용값 목록을 함께 넣어 "아무 값이나 만들지 말고 이 중에서 고르라"고
    제한한다.

    Args:
        category: 고정 대분류입니다.
        sub_category: 고정 소분류입니다.
        known: 이미 확정된 `{속성: 값}`입니다.
        targets: 물어볼 속성 목록입니다.

    Returns:
        완성된 프롬프트 문자열입니다.
    """
    # VLM에게 "아무 값이나 만들어내지 말고 이 목록 중에서만 골라라"라고
    # 제한하기 위해 허용값까지 함께 넘긴다.
    allowed = {
        key: catalog_spec.allowed_values(category, key) for key in targets
    }
    # 위에서 만든 정보를 실제 프롬프트 템플릿에 끼워 넣는다.
    return PROMPT.format(
        category=category,
        sub_category=sub_category or "미상",
        known=json.dumps(known, ensure_ascii=False, indent=2),
        targets=json.dumps(allowed, ensure_ascii=False, indent=2),
    )


def call_gemini(prompt: str, image_paths: list[str]) -> dict[str, Any]:
    """Gemini VLM을 1회 호출하고 JSON 응답을 파싱한다.

    Args:
        prompt: 전송할 프롬프트입니다.
        image_paths: 함께 보낼 이미지 경로 목록입니다.

    Returns:
        파싱된 응답 딕셔너리입니다.

    Raises:
        RuntimeError: Vertex AI API 키가 없거나 응답이 비어 있는 경우입니다.
    """
    # VLM을 쓸 때만 필요한 의존성이라 함수 안에서 임포트한다.
    from google import genai  # pylint: disable=import-outside-toplevel
    from PIL import Image  # pylint: disable=import-outside-toplevel

    # 키 값 자체는 로그·예외 메시지에 남기지 않는다.
    api_key = os.getenv("VERTEX_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("VERTEX_API_KEY가 설정되지 않았습니다.")

    client = genai.Client(vertexai=True, api_key=api_key)
    images = [Image.open(path) for path in image_paths]
    # 프롬프트와 이미지를 한 리스트에 담아야 해서 원소 타입을 Any로 둔다.
    contents: list[Any] = [prompt, *images]

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
            config={"response_mime_type": "application/json"},
        )
        if not response.text:
            raise RuntimeError("Gemini 응답이 비어 있습니다.")
        parsed: dict[str, Any] = json.loads(response.text)
        return parsed
    finally:
        for image in images:
            image.close()


def filter_response(
    response: dict[str, Any], category: str, targets: list[str]
) -> dict[str, Any]:
    """허용값 밖이거나 물어보지 않은 속성을 버린다.

    Args:
        response: VLM 응답입니다.
        category: 고정 대분류입니다.
        targets: 물어본 속성 목록입니다.

    Returns:
        검증을 통과한 `{속성: {value, confidence, reason}}`입니다.
    """
    picked: dict[str, Any] = {}
    for key, payload in response.items():
        # 요청하지 않은 속성은 저장하지 않는다.
        if key not in targets:
            continue

        value = payload.get("value") if isinstance(payload, dict) else payload
        if value is None:
            continue

        # 허용값 검증 - VLM의 환각·표기 흔들림을 한 번 걸러 준다.
        allowed = catalog_spec.allowed_values(category, key)
        if allowed and value not in allowed:
            continue

        picked[key] = {
            "value": value,
            "confidence": (
                payload.get("confidence", 0.5)
                if isinstance(payload, dict)
                else 0.5
            ),
            "reason": (
                payload.get("reason") if isinstance(payload, dict) else None
            ),
        }
    return picked


def target_dirs(goods_ids: list[str]) -> list[pathlib.Path]:
    """처리할 상품 폴더 목록을 정한다.

    Args:
        goods_ids: 명령행에서 지정한 goods_id 목록입니다. 비어 있으면 전체를
            대상으로 합니다.

    Returns:
        상품 폴더 경로 목록입니다.
    """
    if goods_ids:
        return [storage.CRAWL_DIR / goods_id for goods_id in goods_ids]
    return sorted(path for path in storage.CRAWL_DIR.iterdir() if path.is_dir())


@dataclasses.dataclass(frozen=True)
class AskResult:
    """상품 1건에 대한 VLM 보조 처리 결과.

    Attributes:
        payload: vlm_assist.json에 저장할 결과입니다. 호출하지 않았거나
            실패했으면 None입니다.
        enough: 규칙·확정값만으로 충분해 물어볼 속성이 없었으면 True입니다.
    """

    payload: dict[str, Any] | None = None
    enough: bool = False


def ask_product(
    goods_dir: pathlib.Path, verified: dict[str, Any], dry_run: bool
) -> AskResult:
    """상품 1건에 대해 계획을 세우고 필요하면 VLM을 호출한다.

    Args:
        goods_dir: `resource/crawl/{goods_id}` 경로입니다.
        verified: verified_attrs.json의 해당 상품 항목입니다.
        dry_run: True면 무엇을 물어볼지만 출력하고 호출하지 않습니다.

    Returns:
        처리 결과를 담은 `AskResult`입니다.
    """
    key = goods_dir.name
    product_path = goods_dir / "product.json"
    if not product_path.exists():
        print(f"[{key}] product.json 없음 — 건너뜀")
        return AskResult()

    with product_path.open(encoding="utf-8") as file:
        product = json.load(file)

    category, sub_category, known, targets = plan_targets(product, verified)
    if category is None:
        print(f"[{key}] 카테고리 매핑 실패 — 건너뜀")
        return AskResult()
    if not targets:
        return AskResult(enough=True)

    print(f"[{key}] 물어볼 속성 {len(targets)}개: {', '.join(targets)}")
    if dry_run:
        return AskResult()

    try:
        response = call_gemini(
            build_prompt(category, sub_category, known, targets),
            load_images(goods_dir),
        )
    # 상품 1건의 실패로 전체 실행을 멈추지 않는다. 원인은 그대로 출력한다.
    except (RuntimeError, FileNotFoundError, ValueError) as error:
        print(f"  실패: {error}")
        return AskResult()

    return AskResult(
        payload={
            "asked": targets,
            "model": MODEL_NAME,
            "created_at": datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat(),
            "attributes": filter_response(response, category, targets),
        }
    )


def parse_args() -> argparse.Namespace:
    """명령행 인자를 읽는다.

    Returns:
        파싱된 인자 네임스페이스입니다.
    """
    parser = argparse.ArgumentParser(
        description="규칙으로 못 채운 속성만 Gemini에게 물어본다."
    )
    parser.add_argument(
        "goods_ids",
        nargs="*",
        help="대상 goods_id (생략하면 필요한 상품 전체)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="최대 호출 수 (0이면 제한 없음)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="호출하지 않고 어떤 상품에 무엇을 물어볼지만 출력",
    )
    return parser.parse_args()


def main() -> None:
    """미해결 속성이 남은 상품에만 VLM 보조를 돌린다."""
    args = parse_args()

    verified_all = storage.load_json(storage.VERIFIED_PATH, {})
    results = storage.load_json(storage.VLM_PATH, {})

    calls = 0
    skipped = 0
    for goods_dir in target_dirs(args.goods_ids):
        if args.limit and calls >= args.limit:
            print(f"호출 상한({args.limit}) 도달 — 남은 상품은 다음 실행으로")
            break

        result = ask_product(
            goods_dir, verified_all.get(goods_dir.name) or {}, args.dry_run
        )
        skipped += int(result.enough)
        if result.payload is None:
            continue

        calls += 1
        results[goods_dir.name] = result.payload
        print(f"  응답 채택 {len(result.payload['attributes'])}개")

    if calls:
        storage.dump_json(storage.VLM_PATH, results)
        saved_path = storage.VLM_PATH.relative_to(storage.PROJECT_ROOT)
        print(f"저장 완료: {saved_path}")
        print(
            "이 결과는 초안입니다. 사람이 확인한 값만 "
            "scripts/catalog/verified_attrs.json에 옮겨 적으세요."
        )
    print(
        f"VLM 호출 {calls}회 / 규칙·확정값으로 충분해 건너뛴 상품 {skipped}건"
    )


if __name__ == "__main__":
    main()
