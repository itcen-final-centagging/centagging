"""resource/crawl을 data/catalog/answer/sku.json으로 만드는 진입점.

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

    data/catalog/answer/sku.json             최종 정답 카탈로그 (임베딩 입력)
    data/catalog/draft/metadata_draft.json   속성별 출처·확신도·검수 대상
"""

from __future__ import annotations

import argparse
import dataclasses
import pathlib
from typing import Any

from app.core import catalog_spec
from scripts.catalog import metadata_builder, sku_builder, storage
from scripts.catalog import text_rules as rules
from scripts.catalog import validator


@dataclasses.dataclass
class RuleQuality:
    """VLM 없이 규칙만으로 얼마나 채웠고 얼마나 맞았는지.

    Attributes:
        filled: 규칙이 채운 속성 수입니다.
        schema_total: 스키마상 채워야 할 속성 총수입니다.
        agree: 규칙값과 사람 확정값이 같은 건수입니다.
        conflicts: 규칙값과 사람 확정값이 다른 건수입니다.
    """

    filled: int = 0
    schema_total: int = 0
    agree: int = 0
    conflicts: int = 0


@dataclasses.dataclass
class ReviewLoad:
    """사람이 확인해야 하는 양.

    Attributes:
        attributes: 검수 대상 속성 수입니다.
        unresolved: 그중 값 자체가 없는 속성 수입니다.
        products: 값 없는 속성이 남은 상품 수(VLM 보조 후보)입니다.
    """

    attributes: int = 0
    unresolved: int = 0
    products: int = 0


@dataclasses.dataclass
class DraftSummary:
    """초안 전체를 훑어 모은 집계값.

    Attributes:
        sources: 최종 속성 출처별 개수입니다.
        rule: 규칙 품질 집계입니다.
        review: 검수 부담 집계입니다.
    """

    sources: dict[str, int] = dataclasses.field(default_factory=dict)
    rule: RuleQuality = dataclasses.field(default_factory=RuleQuality)
    review: ReviewLoad = dataclasses.field(default_factory=ReviewLoad)


def find_conflicts(
    rule_only: dict[str, Any], verified_attrs: dict[str, Any]
) -> list[dict[str, Any]]:
    """규칙값과 사람 확정값이 갈린 지점을 모은다.

    규칙을 고칠 근거가 되므로 초안에 그대로 남긴다.

    Args:
        rule_only: 규칙 단계까지의 `{속성: 값}`입니다.
        verified_attrs: 사람이 확정한 `{속성: 값}`입니다.

    Returns:
        `{attribute, rule, human}` 목록입니다.
    """
    return [
        {
            "attribute": name,
            "rule": value,
            "human": verified_attrs.get(name),
        }
        for name, value in rule_only.items()
        if name in verified_attrs and verified_attrs[name] != value
    ]


@dataclasses.dataclass
class ProductOutcome:
    """상품 1건의 변환 결과.

    Attributes:
        rows: 만들어진 SKU row 목록입니다.
        entry: 초안 항목입니다. 카테고리 매핑에 실패하면 None입니다.
        warnings: 이 상품에서 나온 경고 목록입니다.
    """

    rows: list[dict] = dataclasses.field(default_factory=list)
    entry: dict[str, Any] | None = None
    warnings: list[str] = dataclasses.field(default_factory=list)


def build_product(
    product: dict, verified: dict[str, Any], vlm: dict[str, Any]
) -> ProductOutcome:
    """상품 1건을 SKU row 목록과 초안 항목으로 만든다.

    Args:
        product: 크롤링한 product.json 딕셔너리입니다.
        verified: verified_attrs.json의 해당 상품 항목입니다.
        vlm: vlm_assist.json의 해당 상품 항목입니다.

    Returns:
        변환 결과를 담은 `ProductOutcome`입니다.
    """
    category, sub_category, warnings = metadata_builder.resolve_category(
        product
    )
    if category is None:
        return ProductOutcome(warnings=warnings)

    # 2~3단계: 원본·규칙 초안 + (있으면) VLM 보조
    draft = metadata_builder.build_draft(product, category, sub_category)
    rule_only = {name: field["value"] for name, field in draft.items()}
    draft = metadata_builder.apply_vlm(draft, vlm.get("attributes"))

    # 4단계: 사람 확정값 우선
    merged = metadata_builder.apply_verified(draft, verified.get("attrs"))

    # 5단계: confidence로 채택 / 검수 분리
    accepted, review = metadata_builder.accept(merged, category)

    context = sku_builder.ProductContext(
        category=category,
        sub_category=sub_category,
        product_name=rules.clean_product_name(product.get("name")),
        key_features=metadata_builder.build_key_features(product),
    )
    rows = sku_builder.build_skus(
        product=product,
        context=context,
        base_attributes=accepted,
        option_spec=verified,
    )

    entry = {
        "product_name": context.product_name,
        "category": category,
        "sub_category": sub_category,
        "schema_size": len(catalog_spec.attribute_names(category)),
        "rule_only": rule_only,
        "attributes": merged,
        "needs_review": review,
        # 규칙값과 사람 확정값이 다른 지점 - 규칙을 고칠 근거가 된다
        "rule_vs_human": find_conflicts(rule_only, verified.get("attrs") or {}),
    }
    return ProductOutcome(rows=rows, entry=entry, warnings=warnings)


def build(
    products: list[dict],
    verified_all: dict[str, Any],
    vlm_all: dict[str, Any],
) -> tuple[list[dict], dict[str, Any], list[str]]:
    """상품 목록을 SKU row와 초안으로 만든다.

    Args:
        products: 크롤링한 상품 딕셔너리 목록입니다.
        verified_all: goods_id별 사람 확정값입니다.
        vlm_all: goods_id별 VLM 보조 결과입니다.

    Returns:
        `(SKU row 목록, goods_id별 초안, 경고 목록)`입니다.
    """
    rows: list[dict] = []
    drafts: dict[str, Any] = {}
    warnings: list[str] = []

    for product in products:
        goods_id = product.get("goods_id")
        key = str(goods_id)

        verified = verified_all.get(key) or {}
        outcome = build_product(product, verified, vlm_all.get(key) or {})
        warnings.extend(f"[{goods_id}] {text}" for text in outcome.warnings)
        if outcome.entry is None:
            continue

        drafts[key] = outcome.entry
        rows.extend(outcome.rows)

        if not verified:
            warnings.append(
                f"[{goods_id}] verified_attrs.json에 확정값 없음 "
                f"— 규칙 추출값만 사용됨(검수 필요)"
            )

    for index, row in enumerate(rows, start=1):
        row["sku_id"] = index

    return rows, drafts, warnings


def summarize(drafts: dict[str, Any]) -> DraftSummary:
    """초안 전체를 훑어 통계를 모은다.

    Args:
        drafts: goods_id별 초안입니다.

    Returns:
        집계 결과입니다.
    """
    summary = DraftSummary()
    for draft in drafts.values():
        for field in draft["attributes"].values():
            source = field["source"]
            summary.sources[source] = summary.sources.get(source, 0) + 1

        summary.review.attributes += len(draft["needs_review"])
        summary.review.unresolved += sum(
            1 for item in draft["needs_review"] if item["reason"] == "값 없음"
        )
        summary.rule.conflicts += len(draft["rule_vs_human"])
        summary.rule.filled += len(draft["rule_only"])
        summary.rule.schema_total += draft["schema_size"]

        human_attrs = {
            name: field["value"]
            for name, field in draft["attributes"].items()
            if field["source"] == "human"
        }
        summary.rule.agree += sum(
            1
            for name, value in draft["rule_only"].items()
            if human_attrs.get(name) == value
        )
        if any(item["reason"] == "값 없음" for item in draft["needs_review"]):
            summary.review.products += 1
    return summary


def print_coverage(summary: DraftSummary, result: dict[str, Any]) -> None:
    """채움률·규칙 커버리지·출처 분포를 출력한다.

    Args:
        summary: `summarize`가 만든 집계 결과입니다.
        result: `validator.validate_rows` 결과입니다.
    """
    total = sum(summary.sources.values()) or 1
    rule = summary.rule
    checked = rule.agree + rule.conflicts

    print(
        f"attributes 채움률 {result['fill_rate']:.1%} "
        f"({result['filled']}/{result['expected']})"
    )
    print(
        f"규칙 커버리지 {rule.filled}/{rule.schema_total} "
        f"= {rule.filled / (rule.schema_total or 1):.1%} "
        f"(VLM 없이 원본·규칙만으로 채운 속성)"
    )
    if checked:
        print(
            f"규칙 정확도 {rule.agree}/{checked} "
            f"= {rule.agree / checked:.1%} "
            f"(사람 확정값과 비교, 불일치 {rule.conflicts}건은 규칙 개선 "
            f"후보)"
        )
    print("최종 속성 출처(상품 단위):")
    for source, count in sorted(summary.sources.items(), key=lambda x: -x[1]):
        print(f"  - {source}: {count}건 ({count / total:.0%})")
    print(
        f"검수 대상 속성 {summary.review.attributes}건 "
        f"(그중 값 자체가 없는 것 {summary.review.unresolved}건) / "
        f"VLM 보조 후보 상품 {summary.review.products}건"
    )


def print_validation(result: dict[str, Any]) -> None:
    """검증 결과와 미기재 속성을 출력한다.

    Args:
        result: `validator.validate_rows` 결과입니다.
    """
    if result["missing"]:
        top = list(result["missing"].items())[:10]
        summary_text = ", ".join(f"{key} {count}" for key, count in top)
        print(f"미기재 속성(상위): {summary_text}")

    if result["duplicate_codes"]:
        print(f"sku_code 중복: {result['duplicate_codes']}")

    if result["errors"]:
        print(f"검증 오류 {len(result['errors'])}건:")
        for code, messages in list(result["errors"].items())[:10]:
            print(f"  - {code}: {'; '.join(messages)}")
    else:
        print("검증 오류 없음")


def parse_args() -> argparse.Namespace:
    """명령행 인자를 읽는다.

    Returns:
        파싱된 인자 네임스페이스입니다.
    """
    parser = argparse.ArgumentParser(
        description="원본·규칙 우선으로 SKU 카탈로그 JSON을 만든다."
    )
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=storage.OUTPUT_PATH,
        help="결과 JSON 경로 (기본: data/catalog/answer/sku.json)",
    )
    return parser.parse_args()


def main() -> None:
    """sku.json과 메타데이터 초안을 생성한다."""
    args = parse_args()

    products = storage.load_products()
    verified_all = storage.load_json(storage.VERIFIED_PATH, {})
    vlm_all = storage.load_json(storage.VLM_PATH, {})

    rows, drafts, warnings = build(products, verified_all, vlm_all)
    result = validator.validate_rows(rows)

    storage.dump_json(args.output, rows)
    storage.dump_json(storage.DRAFT_PATH, drafts)

    print(f"상품 {len(products)}건 -> SKU {len(rows)}건")
    print_coverage(summarize(drafts), result)
    print_validation(result)
    for warning in warnings:
        print(f"경고: {warning}")
    print(f"저장 완료: {args.output.relative_to(storage.PROJECT_ROOT)}")
    print(f"초안 저장: {storage.DRAFT_PATH.relative_to(storage.PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
