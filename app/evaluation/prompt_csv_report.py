"""프롬프트 평가의 압축 지표와 버전 비교를 CSV로 저장합니다."""

import csv
import pathlib
import threading
import typing
from collections.abc import Mapping, Sequence

from app.services.gemini_service import GeminiCallTelemetry

CsvRow = dict[str, object]

_SUMMARY_FIELDS = (
    "evaluated_at",
    "dataset_name",
    "model",
    "provider",
    "location",
    "prompt_type",
    "prompt_version",
    "metric_group",
    "metric",
    "value",
    "unit",
    "target",
    "direction",
    "passed",
)
_COMPARISON_FIELDS = (
    "dataset_name",
    "model",
    "prompt_type",
    "metric_group",
    "metric",
    "v1_value",
    "v2_value",
    "unit",
    "target",
    "direction",
    "delta",
    "change_percent",
    "winner",
)


class PromptTelemetryCollector:
    """병렬 프롬프트 호출의 토큰·재시도 계측값을 수집합니다."""

    def __init__(self) -> None:
        """빈 계측값 목록과 동시성 보호 잠금을 생성합니다."""
        self._records: list[GeminiCallTelemetry] = []
        self._lock = threading.Lock()

    def record(self, telemetry: GeminiCallTelemetry) -> None:
        """한 번의 생성 호출 계측값을 안전하게 추가합니다."""
        with self._lock:
            self._records.append(telemetry)

    def records(self) -> tuple[GeminiCallTelemetry, ...]:
        """현재까지 수집한 계측값의 불변 복사본을 반환합니다."""
        with self._lock:
            return tuple(self._records)


def summarize_telemetry(
    records: Sequence[GeminiCallTelemetry],
    operation_name: str,
) -> dict[str, float | int]:
    """지정된 프롬프트 호출의 실제 토큰과 재시도를 집계합니다."""
    selected = [
        record for record in records if record.operation_name == operation_name
    ]
    call_count = len(selected)
    successful = sum(record.generation_succeeded for record in selected)
    retried_calls = sum(record.attempt_count > 1 for record in selected)
    retry_count = sum(max(record.attempt_count - 1, 0) for record in selected)
    token_reported = sum(record.total_tokens > 0 for record in selected)
    return {
        "call_count": call_count,
        "generation_success_count": successful,
        "retried_call_count": retried_calls,
        "retry_count": retry_count,
        "input_tokens": sum(record.input_tokens for record in selected),
        "output_tokens": sum(record.output_tokens for record in selected),
        "total_tokens": sum(record.total_tokens for record in selected),
        "token_reported_count": token_reported,
        "retry_rate": _ratio(retried_calls, call_count),
        "token_usage_coverage": _ratio(token_reported, successful),
    }


# 지표 정의를 한 함수에서 대조할 수 있도록 지역 계산값을 함께 유지합니다.
# pylint: disable-next=too-many-locals
def build_summary_rows(
    report: Mapping[str, object],
    runtime: Mapping[str, str],
) -> list[CsvRow]:
    """한 프롬프트 버전 리포트를 압축 지표 행으로 변환합니다."""
    summary = _mapping(report, "summary")
    detection = _mapping(summary, "detection")
    attribute = _mapping(summary, "attribute")
    performance = _mapping(summary, "performance")
    calls = _mapping(summary, "calls")
    telemetry = _mapping(summary, "telemetry")
    detection_time = _mapping(performance, "detection")
    attribute_time = _mapping(performance, "attribute_call")
    attribute_batch_time = _mapping(performance, "attribute_batch")
    detection_telemetry = _mapping(telemetry, "detection")
    attribute_telemetry = _mapping(telemetry, "attribute")
    thresholds = _acceptance_checks(report)

    detection_calls = _number(calls, "detection_service_calls")
    attribute_calls = _number(calls, "attribute_service_calls")
    detection_failures = _number(calls, "failed_detection_calls")
    attribute_failures = _number(calls, "failed_attribute_calls")
    detection_successes = detection_calls - detection_failures
    attribute_successes = attribute_calls - attribute_failures
    detection_tokens = _number(detection_telemetry, "total_tokens")
    attribute_tokens = _number(attribute_telemetry, "total_tokens")
    true_positives = _number(detection, "true_positive_count")
    correct_pairs = _number(attribute, "correct_pair_count")
    expected_pairs = _number(attribute, "expected_pair_count")
    actual_pairs = _number(attribute, "actual_pair_count")
    common_keys = _number(attribute, "common_key_count")
    detection_total_ms = _duration_total(detection_time)
    attribute_total_ms = _duration_total(attribute_time)

    common_detection = (
        ("success_rate", _ratio(detection_successes, detection_calls), "ratio"),
        ("p95_ms", _number(detection_time, "p95_ms"), "ms"),
        ("total_tokens", detection_tokens, "tokens"),
        (
            "tokens_per_success",
            _ratio(detection_tokens, detection_successes),
            "tokens/success",
        ),
        ("retry_rate", _number(detection_telemetry, "retry_rate"), "ratio"),
        (
            "token_usage_coverage",
            _number(detection_telemetry, "token_usage_coverage"),
            "ratio",
        ),
    )
    quality_detection = (
        ("f1", _number(detection, "f1"), "ratio"),
        ("mean_iou", _number(detection, "mean_iou"), "ratio"),
        (
            "miss_rate",
            _ratio(
                _number(detection, "false_negative_count"),
                _number(detection, "expected_count"),
            ),
            "ratio",
        ),
        (
            "korean_evidence_rate",
            _number(detection, "korean_evidence_rate"),
            "ratio",
        ),
        (
            "confidence_present_rate",
            _number(detection, "confidence_present_rate"),
            "ratio",
        ),
    )
    efficiency_detection = (
        (
            "correct_objects_per_1k_tokens",
            _per_thousand(true_positives, detection_tokens),
            "objects/1k_tokens",
        ),
        (
            "ms_per_correct_object",
            _ratio(detection_total_ms, true_positives),
            "ms/object",
        ),
    )

    common_attribute = (
        ("success_rate", _ratio(attribute_successes, attribute_calls), "ratio"),
        ("batch_p95_ms", _number(attribute_batch_time, "p95_ms"), "ms"),
        ("total_tokens", attribute_tokens, "tokens"),
        (
            "tokens_per_success",
            _ratio(attribute_tokens, attribute_successes),
            "tokens/success",
        ),
        ("retry_rate", _number(attribute_telemetry, "retry_rate"), "ratio"),
        (
            "token_usage_coverage",
            _number(attribute_telemetry, "token_usage_coverage"),
            "ratio",
        ),
    )
    quality_attribute = (
        ("f1", _number(attribute, "f1"), "ratio"),
        (
            "missing_rate",
            _ratio(max(expected_pairs - common_keys, 0), expected_pairs),
            "ratio",
        ),
        (
            "incorrect_pair_rate",
            _ratio(max(actual_pairs - correct_pairs, 0), actual_pairs),
            "ratio",
        ),
        (
            "category_accuracy",
            _number(attribute, "category_accuracy"),
            "ratio",
        ),
        (
            "sub_category_accuracy",
            _number(attribute, "sub_category_accuracy"),
            "ratio",
        ),
    )
    efficiency_attribute = (
        (
            "correct_pairs_per_1k_tokens",
            _per_thousand(correct_pairs, attribute_tokens),
            "pairs/1k_tokens",
        ),
        (
            "ms_per_correct_pair",
            _ratio(attribute_total_ms, correct_pairs),
            "ms/pair",
        ),
    )

    rows: list[CsvRow] = []
    for prompt_type, metric_group, definitions in (
        ("detection", "common", common_detection),
        ("detection", "quality", quality_detection),
        ("detection", "efficiency", efficiency_detection),
        ("attribute", "common", common_attribute),
        ("attribute", "quality", quality_attribute),
        ("attribute", "efficiency", efficiency_attribute),
    ):
        rows.extend(
            _metric_rows(
                report,
                runtime,
                thresholds,
                prompt_type,
                metric_group,
                definitions,
            )
        )
    return rows


def build_comparison_rows(
    v1_rows: Sequence[CsvRow],
    v2_rows: Sequence[CsvRow],
) -> list[CsvRow]:
    """동일 지표의 v1·v2 값과 변화율 및 우세 버전을 생성합니다."""
    v1_index = {_row_key(row): row for row in v1_rows}
    v2_index = {_row_key(row): row for row in v2_rows}
    rows: list[CsvRow] = []
    for key in sorted(v1_index.keys() & v2_index.keys()):
        v1_row = v1_index[key]
        v2_row = v2_index[key]
        v1_value = _row_number(v1_row, "value")
        v2_value = _row_number(v2_row, "value")
        direction = str(v2_row["direction"])
        delta = v2_value - v1_value
        change_percent: float | str = ""
        if v1_value != 0:
            change_percent = round(delta / v1_value * 100, 2)
        rows.append(
            {
                "dataset_name": v2_row["dataset_name"],
                "model": v2_row["model"],
                "prompt_type": v2_row["prompt_type"],
                "metric_group": v2_row["metric_group"],
                "metric": v2_row["metric"],
                "v1_value": _round(v1_value),
                "v2_value": _round(v2_value),
                "unit": v2_row["unit"],
                "target": v2_row["target"],
                "direction": direction,
                "delta": _round(delta),
                "change_percent": change_percent,
                "winner": _winner(v1_value, v2_value, direction),
            }
        )
    return rows


def write_csv_reports(
    output_directory: pathlib.Path,
    summary_rows: Sequence[CsvRow],
    comparison_rows: Sequence[CsvRow],
) -> tuple[pathlib.Path, pathlib.Path]:
    """압축 지표와 버전 비교를 UTF-8 BOM CSV 파일로 저장합니다."""
    output_directory.mkdir(parents=True, exist_ok=True)
    summary_path = output_directory / "prompt_metrics_summary.csv"
    comparison_path = output_directory / "prompt_version_comparison.csv"
    _write_csv(summary_path, _SUMMARY_FIELDS, summary_rows)
    _write_csv(comparison_path, _COMPARISON_FIELDS, comparison_rows)
    return summary_path, comparison_path


# CSV 행의 공통 메타데이터와 지표 정의를 명시적으로 구분해 전달합니다.
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def _metric_rows(
    report: Mapping[str, object],
    runtime: Mapping[str, str],
    thresholds: Mapping[str, Mapping[str, object]],
    prompt_type: str,
    metric_group: str,
    definitions: Sequence[tuple[str, float, str]],
) -> list[CsvRow]:
    """지표 정의를 공통 메타데이터가 포함된 CSV 행으로 변환합니다."""
    version = str(report["prompt_version"])
    rows = []
    for metric, value, unit in definitions:
        acceptance_name = _acceptance_name(prompt_type, metric)
        threshold = thresholds.get(acceptance_name, {})
        direction = str(
            threshold.get("direction") or _default_direction(metric)
        )
        rows.append(
            {
                "evaluated_at": report["generated_at"],
                "dataset_name": report["dataset_name"],
                "model": runtime["model"],
                "provider": runtime["provider"],
                "location": runtime["location"],
                "prompt_type": prompt_type,
                "prompt_version": version,
                "metric_group": metric_group,
                "metric": metric,
                "value": _round(value),
                "unit": unit,
                "target": threshold.get("target", ""),
                "direction": direction,
                "passed": threshold.get("passed", ""),
            }
        )
    return rows


def _acceptance_checks(
    report: Mapping[str, object],
) -> dict[str, Mapping[str, object]]:
    """완료 기준 목록을 지표명 기반 조회 객체로 변환합니다."""
    acceptance = _mapping(report, "acceptance")
    checks = acceptance.get("checks", [])
    if not isinstance(checks, list):
        return {}
    result: dict[str, Mapping[str, object]] = {}
    for check in checks:
        if not isinstance(check, Mapping):
            continue
        metric = check.get("metric")
        if not isinstance(metric, str):
            continue
        result[metric] = {
            "target": check.get("target", ""),
            "direction": (
                "higher" if check.get("comparison") == "min" else "lower"
            ),
            "passed": check.get("passed", ""),
        }
    return result


def _acceptance_name(prompt_type: str, metric: str) -> str:
    """CSV 지표에 대응하는 완료 기준 이름을 반환합니다."""
    names = {
        ("detection", "f1"): "detection_f1",
        ("detection", "mean_iou"): "detection_mean_iou",
        ("detection", "korean_evidence_rate"): "korean_evidence_rate",
        ("detection", "p95_ms"): "detection_p95_ms",
        ("attribute", "f1"): "attribute_f1",
        ("attribute", "batch_p95_ms"): "attribute_batch_p95_ms",
    }
    return names.get((prompt_type, metric), "")


def _default_direction(metric: str) -> str:
    """지표명이 나타내는 기본 개선 방향을 반환합니다."""
    lower_metrics = {
        "batch_p95_ms",
        "incorrect_pair_rate",
        "miss_rate",
        "missing_rate",
        "ms_per_correct_object",
        "ms_per_correct_pair",
        "p95_ms",
        "retry_rate",
        "tokens_per_success",
        "total_tokens",
    }
    return "lower" if metric in lower_metrics else "higher"


def _mapping(source: Mapping[str, object], key: str) -> Mapping[str, object]:
    """중첩 지표가 매핑인지 검증해 반환합니다."""
    value = source.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} 지표가 객체가 아닙니다.")
    return value


def _number(source: Mapping[str, object], key: str) -> float:
    """지표 매핑에서 불리언이 아닌 숫자를 반환합니다."""
    value = source.get(key, 0)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} 지표가 숫자가 아닙니다.")
    return float(value)


def _row_number(row: Mapping[str, object], key: str) -> float:
    """CSV 행에서 불리언이 아닌 숫자 값을 반환합니다."""
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} CSV 값이 숫자가 아닙니다.")
    return float(value)


def _ratio(numerator: float, denominator: float) -> float:
    """분모가 0일 때 0을 반환하는 비율을 계산합니다."""
    return numerator / denominator if denominator else 0.0


def _per_thousand(numerator: float, denominator: float) -> float:
    """분모 1,000단위당 결과 수를 계산합니다."""
    return _ratio(numerator * 1000, denominator)


def _duration_total(statistics: Mapping[str, object]) -> float:
    """처리시간 통계의 평균과 개수로 전체 밀리초를 계산합니다."""
    return _number(statistics, "average_ms") * _number(statistics, "count")


def _row_key(row: Mapping[str, object]) -> tuple[str, str, str]:
    """버전과 무관한 CSV 지표 식별자를 반환합니다."""
    return (
        str(row["prompt_type"]),
        str(row["metric_group"]),
        str(row["metric"]),
    )


def _winner(v1_value: float, v2_value: float, direction: str) -> str:
    """개선 방향을 기준으로 우세 버전 또는 동률을 반환합니다."""
    if v1_value == v2_value:
        return "tie"
    if direction == "lower":
        return "v2" if v2_value < v1_value else "v1"
    return "v2" if v2_value > v1_value else "v1"


def _round(value: float) -> float:
    """CSV의 숫자를 비교 가능한 소수점 여섯 자리로 정리합니다."""
    return round(value, 6)


def _write_csv(
    path: pathlib.Path,
    fields: Sequence[str],
    rows: Sequence[CsvRow],
) -> None:
    """Excel 한글 호환 UTF-8 BOM 형식으로 CSV를 기록합니다."""
    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(typing.cast(Sequence[dict[str, object]], rows))
