"""resource/crawl -> data/catalog/answer/sku.json 생성(진입점 파일)

실행
    python -m scripts.catalog.build_sku_json

처리 순서

    1. product.json 읽기
    2. metadata_builder: 원본 + 규칙으로 속성 초안 (VLM 호출 없음)
    3. vlm_assist 결과가 있으면 규칙이 못 채운 속성에만 병합
    4. verified_attrs.json(사람 확정)으로 덮어쓰기
    5. confidence >= 0.9 자동 채택 / 미만은 검수 대상
    6. sku_builder: 옵션별 SKU 생성
    7. validator: catalog_spec 기준 검증
    8. 저장 — 최종 sku.json + 근거가 담긴 초안 파일

출력

    data/catalog/answer/sku.json      최종 정답 카탈로그 (임베딩 입력)
    data/catalog/draft/metadata_draft.json   속성별 출처·확신도·검수 대상
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.catalog import metadata_builder
from scripts.catalog import sku_builder
from scripts.catalog import text_rules as rules
from scripts.catalog import validator

CRAWL_DIR = PROJECT_ROOT / "resource" / "crawl"
VERIFIED_PATH = pathlib.Path(__file__).with_name("verified_attrs.json")
VLM_PATH = PROJECT_ROOT / "data" / "catalog" / "draft" / "vlm_assist.json"
OUTPUT_PATH = PROJECT_ROOT / "data" / "catalog" / "answer" / "sku.json"
DRAFT_PATH = PROJECT_ROOT / "data" / "catalog" / "draft" / "metadata_draft.json"


def load_json(path: pathlib.Path, default: Any) -> Any:
    """JSON 파일을 읽되 없으면 기본값을 돌려준다."""
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def load_products(crawl_dir: pathlib.Path) -> list[dict]:
    """크롤링 폴더에서 product.json을 모두 읽는다."""
    products = []
    for path in sorted(crawl_dir.glob("*/product.json")):
        with path.open(encoding="utf-8") as file:
            products.append(json.load(file))
    return sorted(products, key=lambda item: item.get("goods_id", 0))


def build(
    products: list[dict],
    verified_all: dict[str, Any],
    vlm_all: dict[str, Any],
) -> tuple[list[dict], dict[str, Any], list[str]]:
    """상품 목록을 SKU row와 초안으로 만든다."""
    rows: list[dict] = []
    drafts: dict[str, Any] = {}
    warnings: list[str] = []

    for product in products:
        goods_id = product.get("goods_id")
        key = str(goods_id)

        category, sub_category, category_warnings = (
            metadata_builder.resolve_category(product)
        )
        warnings.extend(f"[{goods_id}] {text}" for text in category_warnings)
        if category is None:
            continue

        # 2~3단계: 원본·규칙 초안 + (있으면) VLM 보조
        draft = metadata_builder.build_draft(product, category, sub_category)
        rule_only = {name: field["value"] for name, field in draft.items()}
        draft = metadata_builder.apply_vlm(
            draft, (vlm_all.get(key) or {}).get("attributes")
        )

        # 4단계: 사람 확정값 우선
        verified = verified_all.get(key) or {}
        merged = metadata_builder.apply_verified(draft, verified.get("attrs"))

        # 5단계: confidence로 채택 / 검수 분리
        accepted, review = metadata_builder.accept(merged, category)

        # 규칙값과 사람 확정값이 다른 지점 - 규칙을 고칠 근거가 된다
        conflicts = [
            {
                "attribute": name,
                "rule": rule_only[name],
                "human": verified.get("attrs", {}).get(name),
            }
            for name in rule_only
            if name in (verified.get("attrs") or {})
            and verified["attrs"][name] != rule_only[name]
        ]

        product_name = rules.clean_product_name(product.get("name"))
        key_features = metadata_builder.build_key_features(product)

        rows.extend(sku_builder.build_skus(
            product=product,
            category=category,
            sub_category=sub_category,
            product_name=product_name,
            key_features=key_features,
            base_attributes=accepted,
            option_spec=verified,
        ))

        drafts[key] = {
            "product_name": product_name,
            "category": category,
            "sub_category": sub_category,
            "schema_size": len(
                metadata_builder.catalog_spec.attribute_names(category)
            ),
            "rule_only": rule_only,
            "attributes": merged,
            "needs_review": review,
            "rule_vs_human": conflicts,
        }

        if not verified:
            warnings.append(
                f"[{goods_id}] verified_attrs.json에 확정값 없음 "
                f"— 규칙 추출값만 사용됨(검수 필요)"
            )

    for index, row in enumerate(rows, start=1):
        row["sku_id"] = index

    return rows, drafts, warnings


def report(
    products: list[dict],
    rows: list[dict],
    drafts: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """생성 결과를 콘솔에 요약한다."""
    sources: dict[str, int] = {}
    review_count = 0
    unresolved = 0
    vlm_needed = 0
    conflicts = 0
    rule_filled = 0
    schema_total = 0
    agree = 0

    for draft in drafts.values():
        for field in draft["attributes"].values():
            sources[field["source"]] = sources.get(field["source"], 0) + 1
        review_count += len(draft["needs_review"])
        unresolved += sum(
            1 for item in draft["needs_review"] if item["reason"] == "값 없음"
        )
        conflicts += len(draft["rule_vs_human"])
        rule_filled += len(draft["rule_only"])
        schema_total += draft["schema_size"]
        human_attrs = {
            name: field["value"]
            for name, field in draft["attributes"].items()
            if field["source"] == "human"
        }
        agree += sum(
            1
            for name, value in draft["rule_only"].items()
            if human_attrs.get(name) == value
        )
        if any(item["reason"] == "값 없음" for item in draft["needs_review"]):
            vlm_needed += 1

    total = sum(sources.values()) or 1
    checked = agree + conflicts

    print(f"상품 {len(products)}건 -> SKU {len(rows)}건")
    print(
        f"attributes 채움률 {result['fill_rate']:.1%} "
        f"({result['filled']}/{result['expected']})"
    )
    print(
        f"규칙 커버리지 {rule_filled}/{schema_total} "
        f"= {rule_filled / (schema_total or 1):.1%} "
        f"(VLM 없이 원본·규칙만으로 채운 속성)"
    )
    if checked:
        print(
            f"규칙 정확도 {agree}/{checked} = {agree / checked:.1%} "
            f"(사람 확정값과 비교, 불일치 {conflicts}건은 규칙 개선 후보)"
        )
    print("최종 속성 출처(상품 단위):")
    for source, count in sorted(sources.items(), key=lambda item: -item[1]):
        print(f"  - {source}: {count}건 ({count / total:.0%})")
    print(
        f"검수 대상 속성 {review_count}건 "
        f"(그중 값 자체가 없는 것 {unresolved}건) / "
        f"VLM 보조 후보 상품 {vlm_needed}건"
    )

    if result["missing"]:
        top = list(result["missing"].items())[:10]
        summary = ", ".join(f"{key} {count}" for key, count in top)
        print(f"미기재 속성(상위): {summary}")

    if result["duplicate_codes"]:
        print(f"sku_code 중복: {result['duplicate_codes']}")

    if result["errors"]:
        print(f"검증 오류 {len(result['errors'])}건:")
        for code, messages in list(result["errors"].items())[:10]:
            print(f"  - {code}: {'; '.join(messages)}")
    else:
        print("검증 오류 없음")


def main() -> None:
    """sku3.json과 메타데이터 초안을 생성한다."""
    parser = argparse.ArgumentParser(description="원본·규칙 우선으로 SKU 카탈로그 JSON을 만든다.")
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=OUTPUT_PATH,
        help="결과 JSON 경로 (기본: data/catalog/answer/sku.json)",
    )
    args = parser.parse_args()

    products = load_products(CRAWL_DIR)
    verified_all = load_json(VERIFIED_PATH, {})
    vlm_all = load_json(VLM_PATH, {})

    rows, drafts, warnings = build(products, verified_all, vlm_all)
    result = validator.validate_rows(rows)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as file:
        json.dump(rows, file, ensure_ascii=False, indent=2)
        file.write("\n")

    DRAFT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DRAFT_PATH.open("w", encoding="utf-8") as file:
        json.dump(drafts, file, ensure_ascii=False, indent=2)
        file.write("\n")

    report(products, rows, drafts, result)
    for warning in warnings:
        print(f"경고: {warning}")
    print(f"저장 완료: {args.output.relative_to(PROJECT_ROOT)}")
    print(f"초안 저장: {DRAFT_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
