"""SKU 추천 정확도 평가 지표 테스트입니다."""

from scripts.evaluation import evaluate_retrieval


def test_evaluate_calculates_top1_top5_and_candidate_miss_rate() -> None:
    """정답 순위에 따라 Top-1·Top-5·누락 지표를 분리한다."""
    metrics = evaluate_retrieval.evaluate(
        [
            evaluate_retrieval.RetrievalCase("a", "SKU-1", ["SKU-1"]),
            evaluate_retrieval.RetrievalCase("b", "SKU-2", ["SKU-3", "SKU-2"]),
            evaluate_retrieval.RetrievalCase(
                "c", "SKU-4", ["SKU-1", "SKU-2", "SKU-3", "SKU-5", "SKU-6"]
            ),
        ]
    )

    assert metrics.total == 3
    assert metrics.top1_hits == 1
    assert metrics.top5_hits == 2
    assert metrics.missing_candidates == 1
    assert metrics.top1_accuracy == 1 / 3
    assert metrics.top5_accuracy == 2 / 3


def test_format_report_includes_pipeline_version_and_rates() -> None:
    """리포트에 버전과 핵심 지표가 고정 형식으로 포함된다."""
    report = evaluate_retrieval.format_report(
        evaluate_retrieval.RetrievalMetrics(10, 7, 9, 1),
        "2026-08-21.1",
    )

    assert "파이프라인 버전: 2026-08-21.1" in report
    assert "Top-1 정확도: 70.00% (7/10)" in report
    assert "Top-5 정확도: 90.00% (9/10)" in report
    assert "후보 누락률: 10.00% (1/10)" in report
