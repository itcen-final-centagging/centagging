"""resource/crawl을 data/catalog/answer/sku.json으로 만드는 진입점.

실행

    python -m scripts.catalog.build_sku_json

처리 순서

    1. product.json 읽기
    2. metadata_builder: 원본 + 규칙으로 속성 초안 생성
    3. vlm_assist 결과가 있으면 규칙이 못 채운 속성에만 병합
    4. confidence 기준으로 자동 채택 / 검수 대상 분리
    5. sku_builder: 현재 자동 확정값으로 SKU 생성
    6. validator: catalog_spec 기준 검증
    7. 저장

사람 검수는 이 단계에서 수행하지 않는다.
생성된 metadata_draft.json을 xlsx로 변환한 뒤 사람이 검수하고,
검수 완료 xlsx를 별도 파이프라인에서 다시 읽어 최종 sku.json을 생성한다.

출력

    data/catalog/answer/sku.json
        현재 자동 생성된 SKU 카탈로그

    data/catalog/draft/metadata_draft.json
        속성별 출처·확신도·검수 대상이 담긴 메타데이터 초안
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

AUTO_ACCEPT = 0.9

@dataclasses.dataclass
class RuleQuality:
    """VLM 없이 규칙만으로 얼마나 채웠는지 집계한다.

    Attributes:
        filled: 규칙 단계에서 채워진 속성 수입니다.
        schema_total: 스키마상 채워야 할 속성 총수입니다.
    """

    filled: int = 0
    schema_total: int = 0


@dataclasses.dataclass
class ReviewLoad:
    """사람이 확인해야 하는 양을 집계한다.

    Attributes:
        attributes: 검수 대상 속성 수입니다.
        unresolved: 그중 값 자체가 없는 속성 수입니다.
        products: 값 없는 속성이 남은 상품 수입니다.
    """

    attributes: int = 0
    unresolved: int = 0
    products: int = 0


@dataclasses.dataclass
class DraftSummary:
    """초안 전체를 훑어 모은 집계값.

    Attributes:
        sources: 최종 속성 출처별 개수입니다.
        rule: 규칙 커버리지 집계입니다.
        review: 검수 부담 집계입니다.
    """

    sources: dict[str, int] = dataclasses.field(default_factory=dict)
    rule: RuleQuality = dataclasses.field(default_factory=RuleQuality)
    review: ReviewLoad = dataclasses.field(
        default_factory=ReviewLoad
    )


@dataclasses.dataclass
class ProductOutcome:
    """상품 1건의 변환 결과.

    Attributes:
        rows: 만들어진 SKU row 목록입니다.
        entry: 메타데이터 초안 항목입니다.
        warnings: 이 상품에서 나온 경고 목록입니다.
    """

    rows: list[dict] = dataclasses.field(default_factory=list)
    entry: dict[str, Any] | None = None
    warnings: list[str] = dataclasses.field(default_factory=list)


def build_product(
    product: dict,
    vlm: dict[str, Any],
) -> ProductOutcome:
    """상품 1건의 SKU row 목록과 메타데이터 초안 항목을 만든다.

    처리 순서:
    1. 원본 + 규칙으로 메타데이터 초안 생성
    2. 규칙으로 못 채운 값만 VLM 보조
    3. confidence 기준으로 검수 대상 분리
    4. 검수 대상과 확정된 값을 draft에 기록
    5. 현재 확정값으로 SKU 생성

    사람 검수값은 이 단계에서 적용하지 않는다.
    사람 검수는 xlsx에서 수행한 뒤 별도 파이프라인에서
    최종 sku.json으로 변환한다.
    """

    category, sub_category, warnings = (
        metadata_builder.resolve_category(product)
    )

    if category is None:
        return ProductOutcome(warnings=warnings)

    # 1. 원본 + 규칙
    draft = metadata_builder.build_draft(
        product,
        category,
        sub_category,
    )

    rule_only = {
        name: field["value"]
        for name, field in draft.items()
    }

    # 2. 규칙으로 못 채운 값만 VLM 보조
    merged = metadata_builder.apply_vlm(
        draft,
        vlm.get("attributes"),
    )

    # 3. confidence 기준으로 검수 대상 분리
    #
    # accept()를 사용하지 않고,
    # 현재 merged 값 자체를 SKU 생성의 임시 기준으로 사용한다.
    review: list[dict[str, Any]] = []

    schema_keys = catalog_spec.attribute_names(category)

    for key in schema_keys:
        field = merged.get(key)

        # 값이 아예 없는 경우
        if field is None or field.get("value") is None:
            review.append(
                {
                    "attribute": key,
                    "reason": "값 없음",
                }
            )
            continue

        # confidence가 검수 기준보다 낮은 경우
        confidence = float(field.get("confidence", 0.0))

        if confidence < AUTO_ACCEPT:
            review.append(
                {
                    "attribute": key,
                    "value": field["value"],
                    "source": field.get("source"),
                    "confidence": confidence,
                    "reason": "confidence 기준 미달",
                }
            )

    # 4. 상품 공통 정보
    context = sku_builder.ProductContext(
        category=category,
        sub_category=sub_category,
        product_name=rules.clean_product_name(
            product.get("name")
        ),
        key_features=metadata_builder.build_key_features(
            product
        ),
    )

    # 5. 현재 단계에서는 merged의 값으로 SKU 생성
    base_attributes = {
        name: field["value"]
        for name, field in merged.items()
        if field.get("value") is not None
        and name in schema_keys
    }

    rows = sku_builder.build_skus(
        product=product,
        context=context,
        base_attributes=base_attributes,
        option_spec={},
    )

    goods_id = int(product.get("goods_id") or 0)

    entry = {
        "goods_id": goods_id,
        "product_name": context.product_name,
        "category": category,
        "sub_category": sub_category,
        "schema_size": len(schema_keys),
        "rule_only": rule_only,
        "attributes": merged,
        "needs_review": review,
    }

    return ProductOutcome(
        rows=rows,
        entry=entry,
        warnings=warnings,
    )


def build(
    products: list[dict],
    vlm_all: dict[str, Any],
) -> tuple[list[dict], dict[str, Any], list[str]]:
    """상품 목록을 SKU row와 메타데이터 초안으로 만든다.

    Args:
        products: 크롤링한 상품 딕셔너리 목록입니다.
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

        outcome = build_product(
            product,
            vlm_all.get(key) or {},
        )

        warnings.extend(
            f"[{goods_id}] {text}"
            for text in outcome.warnings
        )

        if outcome.entry is None:
            continue

        drafts[key] = outcome.entry
        rows.extend(outcome.rows)

    # 전체 상품을 합친 뒤 SKU ID를 부여한다.
    for index, row in enumerate(rows, start=1):
        row["sku_id"] = index

    return rows, drafts, warnings


def summarize(
    drafts: dict[str, Any],
) -> DraftSummary:
    """초안 전체를 훑어 통계를 모은다.

    Args:
        drafts: goods_id별 메타데이터 초안입니다.

    Returns:
        집계 결과입니다.
    """

    summary = DraftSummary()

    for draft in drafts.values():

        # -----------------------------------------------------
        # 속성 출처 집계
        # -----------------------------------------------------
        for field in draft["attributes"].values():
            source = field["source"]

            summary.sources[source] = (
                summary.sources.get(source, 0) + 1
            )

        # -----------------------------------------------------
        # 검수 대상 집계
        # -----------------------------------------------------
        needs_review = draft["needs_review"]

        summary.review.attributes += len(needs_review)

        summary.review.unresolved += sum(
            1
            for item in needs_review
            if item["reason"] == "값 없음"
        )

        if any(
            item["reason"] == "값 없음"
            for item in needs_review
        ):
            summary.review.products += 1

        # -----------------------------------------------------
        # 규칙 커버리지 집계
        # -----------------------------------------------------
        summary.rule.filled += len(draft["rule_only"])
        summary.rule.schema_total += draft["schema_size"]

    return summary


def print_coverage(
    summary: DraftSummary,
    result: dict[str, Any],
) -> None:
    """채움률·규칙 커버리지·출처 분포를 출력한다."""

    total = sum(summary.sources.values()) or 1
    rule = summary.rule

    print(
        f"attributes 채움률 "
        f"{result['fill_rate']:.1%} "
        f"({result['filled']}/{result['expected']})"
    )

    print(
        f"규칙 커버리지 "
        f"{rule.filled}/{rule.schema_total} "
        f"= "
        f"{rule.filled / (rule.schema_total or 1):.1%} "
        f"(VLM 없이 원본·규칙만으로 채운 속성)"
    )

    print("최종 속성 출처(상품 단위):")

    for source, count in sorted(
        summary.sources.items(),
        key=lambda x: -x[1],
    ):
        print(
            f"  - {source}: "
            f"{count}건 "
            f"({count / total:.0%})"
        )

    print(
        f"검수 대상 속성 "
        f"{summary.review.attributes}건 "
        f"(그중 값 자체가 없는 것 "
        f"{summary.review.unresolved}건) / "
        f"검수 필요 상품 "
        f"{summary.review.products}건"
    )


def print_validation(
    result: dict[str, Any],
) -> None:
    """검증 결과와 미기재 속성을 출력한다."""

    if result["missing"]:
        top = list(result["missing"].items())[:10]

        summary_text = ", ".join(
            f"{key} {count}"
            for key, count in top
        )

        print(
            f"미기재 속성(상위): "
            f"{summary_text}"
        )

    if result["duplicate_codes"]:
        print(
            f"sku_code 중복: "
            f"{result['duplicate_codes']}"
        )

    if result["errors"]:
        print(
            f"검증 오류 "
            f"{len(result['errors'])}건:"
        )

        for code, messages in list(
            result["errors"].items()
        )[:10]:
            print(
                f"  - {code}: "
                f"{'; '.join(messages)}"
            )
    else:
        print("검증 오류 없음")


def parse_args() -> argparse.Namespace:
    """명령행 인자를 읽는다."""

    parser = argparse.ArgumentParser(
        description=(
            "원본·규칙·VLM 우선으로 "
            "SKU 카탈로그 초안을 만든다."
        )
    )

    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=storage.OUTPUT_PATH,
        help=(
            "결과 JSON 경로 "
            "(기본: data/catalog/answer/sku.json)"
        ),
    )

    return parser.parse_args()


def main() -> None:
    """자동 SKU와 메타데이터 초안을 생성한다."""

    args = parse_args()

    products = storage.load_products()
    vlm_all = storage.load_json(
        storage.VLM_PATH,
        {},
    )

    rows, drafts, warnings = build(
        products,
        vlm_all,
    )

    result = validator.validate_rows(rows)

    storage.dump_json(
        args.output,
        rows,
    )

    storage.dump_json(
        storage.DRAFT_PATH,
        drafts,
    )

    print(
        f"상품 {len(products)}건 "
        f"-> SKU {len(rows)}건"
    )

    print_coverage(
        summarize(drafts),
        result,
    )

    print_validation(result)

    for warning in warnings:
        print(f"경고: {warning}")

    print(
        f"저장 완료: "
        f"{args.output.relative_to(storage.PROJECT_ROOT)}"
    )

    print(
        f"초안 저장: "
        f"{storage.DRAFT_PATH.relative_to(storage.PROJECT_ROOT)}"
    )


if __name__ == "__main__":
    main()