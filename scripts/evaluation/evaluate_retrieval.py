"""SKU 추천 결과의 Top-K 정확도를 계산합니다.

입력 JSON 예시:
{
  "pipeline_version": "2026-08-21.1",
  "cases": [
    {"case_id": "scene-001-object-0", "expected_sku_code": "SKU-1",
     "candidate_sku_codes": ["SKU-1", "SKU-2"]}
  ]
}

실행:
    python -m scripts.evaluation.evaluate_retrieval results.json
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
from typing import Any


@dataclasses.dataclass(frozen=True)
class RetrievalCase:
    """객체 한 건의 정답 SKU와 추천 후보입니다."""

    case_id: str
    expected_sku_code: str
    candidate_sku_codes: list[str]


@dataclasses.dataclass(frozen=True)
class RetrievalMetrics:
    """추천 평가 집계값입니다."""

    total: int
    top1_hits: int
    top5_hits: int
    missing_candidates: int

    @property
    def top1_accuracy(self) -> float:
        return _rate(self.top1_hits, self.total)

    @property
    def top5_accuracy(self) -> float:
        return _rate(self.top5_hits, self.total)

    @property
    def candidate_miss_rate(self) -> float:
        return _rate(self.missing_candidates, self.total)


def evaluate(cases: list[RetrievalCase]) -> RetrievalMetrics:
    """정답 SKU가 후보 1위·상위 5위 안에 있는 비율을 계산합니다."""
    top1_hits = sum(
        bool(case.candidate_sku_codes)
        and case.candidate_sku_codes[0] == case.expected_sku_code
        for case in cases
    )
    top5_hits = sum(
        case.expected_sku_code in case.candidate_sku_codes[:5] for case in cases
    )
    return RetrievalMetrics(
        total=len(cases),
        top1_hits=top1_hits,
        top5_hits=top5_hits,
        missing_candidates=len(cases) - top5_hits,
    )


def load_cases(path: pathlib.Path) -> tuple[str | None, list[RetrievalCase]]:
    """평가 결과 JSON을 검증 가능한 내부 모델로 읽습니다."""
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    cases = [
        RetrievalCase(
            case_id=str(item["case_id"]),
            expected_sku_code=str(item["expected_sku_code"]),
            candidate_sku_codes=[
                str(code) for code in item["candidate_sku_codes"]
            ],
        )
        for item in payload["cases"]
    ]
    return _optional_text(payload.get("pipeline_version")), cases


def format_report(
    metrics: RetrievalMetrics,
    pipeline_version: str | None,
) -> str:
    """파이프라인 버전 비교에 쓰기 쉬운 고정 형식 리포트를 만듭니다."""
    version = pipeline_version or "미지정"
    return "\n".join(
        [
            "=== SKU 추천 평가 ===",
            f"파이프라인 버전: {version}",
            f"평가 객체 수: {metrics.total}",
            f"Top-1 정확도: {metrics.top1_accuracy:.2%} ({metrics.top1_hits}/{metrics.total})",
            f"Top-5 정확도: {metrics.top5_accuracy:.2%} ({metrics.top5_hits}/{metrics.total})",
            f"후보 누락률: {metrics.candidate_miss_rate:.2%} ({metrics.missing_candidates}/{metrics.total})",
        ]
    )


def parse_args() -> argparse.Namespace:
    """CLI 인자를 읽습니다."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result_file", type=pathlib.Path)
    return parser.parse_args()


def main() -> None:
    """평가 결과 JSON을 읽어 표준 출력에 지표를 표시합니다."""
    args = parse_args()
    version, cases = load_cases(args.result_file)
    print(format_report(evaluate(cases), version))


def _optional_text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


if __name__ == "__main__":
    main()
