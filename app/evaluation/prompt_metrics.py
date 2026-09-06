"""가구 탐지와 속성 추출 프롬프트의 정량 지표를 계산합니다."""

import math
import statistics
import typing
from collections.abc import Mapping, Sequence

MetricValue = float | int
MetricResult = dict[str, MetricValue]


class _Box(typing.NamedTuple):
    """IoU 계산에 사용하는 바운딩 박스 좌표입니다."""

    xmin: float
    ymin: float
    xmax: float
    ymax: float


def _number(value: object, field_name: str) -> float:
    """좌표 값을 실수로 변환합니다."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} 좌표가 숫자가 아닙니다.")
    return float(value)


def _bbox(item: Mapping[str, object]) -> Mapping[str, object]:
    """평가 객체에서 바운딩 박스를 가져옵니다."""
    bbox = item.get("bbox_coord")
    if not isinstance(bbox, Mapping):
        raise ValueError("평가 객체에 bbox_coord가 없습니다.")
    return bbox


def _box_coordinates(box: Mapping[str, object]) -> _Box:
    """바운딩 박스 Mapping을 숫자 좌표 객체로 변환합니다."""
    return _Box(
        xmin=_number(box.get("xmin"), "xmin"),
        ymin=_number(box.get("ymin"), "ymin"),
        xmax=_number(box.get("xmax"), "xmax"),
        ymax=_number(box.get("ymax"), "ymax"),
    )


def calculate_iou(
    first: Mapping[str, object],
    second: Mapping[str, object],
) -> float:
    """두 바운딩 박스의 Intersection over Union을 계산합니다.

    Args:
        first: 첫 번째 0~1000 정규화 바운딩 박스입니다.
        second: 두 번째 0~1000 정규화 바운딩 박스입니다.

    Returns:
        0~1 범위의 IoU 값입니다.
    """
    first_box = _box_coordinates(first)
    second_box = _box_coordinates(second)

    intersection_width = max(
        0.0,
        min(first_box.xmax, second_box.xmax)
        - max(first_box.xmin, second_box.xmin),
    )
    intersection_height = max(
        0.0,
        min(first_box.ymax, second_box.ymax)
        - max(first_box.ymin, second_box.ymin),
    )
    intersection = intersection_width * intersection_height

    first_area = max(0.0, first_box.xmax - first_box.xmin) * max(
        0.0, first_box.ymax - first_box.ymin
    )
    second_area = max(0.0, second_box.xmax - second_box.xmin) * max(
        0.0, second_box.ymax - second_box.ymin
    )
    union = first_area + second_area - intersection
    return intersection / union if union > 0 else 0.0


def match_objects_by_iou(
    expected: Sequence[Mapping[str, object]],
    actual: Sequence[Mapping[str, object]],
    iou_threshold: float,
) -> list[tuple[int, int, float]]:
    """IoU가 높은 순서대로 정답 객체와 탐지 객체를 일대일 매칭합니다."""
    if not 0 <= iou_threshold <= 1:
        raise ValueError("iou_threshold는 0~1 범위여야 합니다.")

    candidates = [
        (calculate_iou(_bbox(expected_item), _bbox(actual_item)), left, right)
        for left, expected_item in enumerate(expected)
        for right, actual_item in enumerate(actual)
    ]
    candidates.sort(reverse=True)

    expected_used: set[int] = set()
    actual_used: set[int] = set()
    matches: list[tuple[int, int, float]] = []
    for iou, expected_index, actual_index in candidates:
        if iou < iou_threshold:
            break
        if expected_index in expected_used or actual_index in actual_used:
            continue
        expected_used.add(expected_index)
        actual_used.add(actual_index)
        matches.append((expected_index, actual_index, iou))
    return matches


def _ratio(numerator: int | float, denominator: int | float) -> float:
    """분모가 0인 경우 0을 반환하는 비율 계산 함수입니다."""
    return float(numerator / denominator) if denominator else 0.0


def _f1_score(precision: float, recall: float) -> float:
    """precision과 recall로 F1 점수를 계산합니다."""
    return (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )


def _contains_hangul(value: object) -> bool:
    """문자열에 한글 완성형 문자가 포함되어 있는지 확인합니다."""
    return isinstance(value, str) and any(
        "가" <= character <= "힣" for character in value
    )


def evaluate_detection_response(
    expected: Sequence[Mapping[str, object]],
    actual: Sequence[Mapping[str, object]],
    iou_threshold: float = 0.5,
) -> MetricResult:
    """한 번의 객체 탐지 응답을 정답 객체 목록과 비교합니다."""
    matches = match_objects_by_iou(expected, actual, iou_threshold)
    category_correct = sum(
        expected[expected_index].get("category")
        == actual[actual_index].get("category")
        for expected_index, actual_index, _ in matches
    )
    expected_count = len(expected)
    actual_count = len(actual)
    precision = _ratio(category_correct, actual_count)
    recall = _ratio(category_correct, expected_count)
    confidence_count = sum(
        isinstance(item.get("confidence"), (int, float))
        and not isinstance(item.get("confidence"), bool)
        for item in actual
    )
    korean_evidence_count = sum(
        _contains_hangul(item.get("evidence")) for item in actual
    )

    return {
        "expected_count": expected_count,
        "actual_count": actual_count,
        "spatial_match_count": len(matches),
        "category_correct_count": category_correct,
        "true_positive_count": category_correct,
        "false_positive_count": actual_count - category_correct,
        "false_negative_count": expected_count - category_correct,
        "iou_sum": sum(iou for _, _, iou in matches),
        "mean_iou": _ratio(sum(iou for _, _, iou in matches), len(matches)),
        "category_accuracy": _ratio(category_correct, len(matches)),
        "precision": precision,
        "recall": recall,
        "f1": _f1_score(precision, recall),
        "confidence_present_count": confidence_count,
        "confidence_present_rate": _ratio(confidence_count, actual_count),
        "korean_evidence_count": korean_evidence_count,
        "korean_evidence_rate": _ratio(korean_evidence_count, actual_count),
    }


def evaluate_attribute_response(
    expected: Mapping[str, object],
    actual: Mapping[str, object],
) -> MetricResult:
    """한 객체의 속성 추출 응답을 정답 속성과 비교합니다."""
    expected_attributes = expected.get("attributes", {})
    actual_attributes = actual.get("attributes", {})
    if not isinstance(expected_attributes, Mapping) or not isinstance(
        actual_attributes, Mapping
    ):
        raise ValueError("attributes는 객체여야 합니다.")

    expected_pairs = set(expected_attributes.items())
    actual_pairs = set(actual_attributes.items())
    correct_pairs = expected_pairs & actual_pairs
    common_keys = set(expected_attributes) & set(actual_attributes)
    expected_pair_count = len(expected_pairs)
    actual_pair_count = len(actual_pairs)
    precision = _ratio(len(correct_pairs), actual_pair_count)
    recall = _ratio(len(correct_pairs), expected_pair_count)

    expected_sub_category = expected.get("sub_category")
    sub_category_evaluated = int(isinstance(expected_sub_category, str))
    sub_category_correct = int(
        bool(sub_category_evaluated)
        and expected_sub_category == actual.get("sub_category")
    )

    return {
        "category_evaluated_count": 1,
        "category_correct_count": int(
            expected.get("category") == actual.get("category")
        ),
        "sub_category_evaluated_count": sub_category_evaluated,
        "sub_category_correct_count": sub_category_correct,
        "attribute_evaluated_count": int(bool(expected_pairs)),
        "expected_pair_count": expected_pair_count,
        "actual_pair_count": actual_pair_count,
        "correct_pair_count": len(correct_pairs),
        "common_key_count": len(common_keys),
        "precision": precision,
        "recall": recall,
        "f1": _f1_score(precision, recall),
        "key_coverage": _ratio(len(common_keys), expected_pair_count),
        "value_accuracy": _ratio(len(correct_pairs), len(common_keys)),
    }


def duration_statistics(values: Sequence[float]) -> dict[str, float | int]:
    """밀리초 처리시간 목록의 기초 통계를 계산합니다."""
    if not values:
        return {
            "count": 0,
            "min_ms": 0.0,
            "average_ms": 0.0,
            "median_ms": 0.0,
            "p95_ms": 0.0,
            "max_ms": 0.0,
        }

    ordered = sorted(values)
    p95_index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return {
        "count": len(ordered),
        "min_ms": round(ordered[0], 2),
        "average_ms": round(statistics.fmean(ordered), 2),
        "median_ms": round(statistics.median(ordered), 2),
        "p95_ms": round(ordered[p95_index], 2),
        "max_ms": round(ordered[-1], 2),
    }


def aggregate_detection_metrics(
    results: Sequence[MetricResult],
) -> MetricResult:
    """여러 탐지 실행 결과를 하나의 품질 지표로 합칩니다."""
    totals = {
        key: sum(float(result.get(key, 0)) for result in results)
        for key in (
            "expected_count",
            "actual_count",
            "spatial_match_count",
            "category_correct_count",
            "true_positive_count",
            "false_positive_count",
            "false_negative_count",
            "iou_sum",
            "confidence_present_count",
            "korean_evidence_count",
        )
    }
    precision = _ratio(totals["true_positive_count"], totals["actual_count"])
    recall = _ratio(totals["true_positive_count"], totals["expected_count"])
    return {
        **totals,
        "run_count": len(results),
        "mean_iou": _ratio(totals["iou_sum"], totals["spatial_match_count"]),
        "category_accuracy": _ratio(
            totals["category_correct_count"],
            totals["spatial_match_count"],
        ),
        "precision": precision,
        "recall": recall,
        "f1": _f1_score(precision, recall),
        "confidence_present_rate": _ratio(
            totals["confidence_present_count"], totals["actual_count"]
        ),
        "korean_evidence_rate": _ratio(
            totals["korean_evidence_count"], totals["actual_count"]
        ),
    }


def aggregate_attribute_metrics(
    results: Sequence[MetricResult],
) -> MetricResult:
    """여러 속성 추출 결과를 하나의 품질 지표로 합칩니다."""
    totals = {
        key: sum(float(result.get(key, 0)) for result in results)
        for key in (
            "category_evaluated_count",
            "category_correct_count",
            "sub_category_evaluated_count",
            "sub_category_correct_count",
            "attribute_evaluated_count",
            "expected_pair_count",
            "actual_pair_count",
            "correct_pair_count",
            "common_key_count",
        )
    }
    precision = _ratio(
        totals["correct_pair_count"], totals["actual_pair_count"]
    )
    recall = _ratio(totals["correct_pair_count"], totals["expected_pair_count"])
    return {
        **totals,
        "result_count": len(results),
        "category_accuracy": _ratio(
            totals["category_correct_count"],
            totals["category_evaluated_count"],
        ),
        "sub_category_accuracy": _ratio(
            totals["sub_category_correct_count"],
            totals["sub_category_evaluated_count"],
        ),
        "precision": precision,
        "recall": recall,
        "f1": _f1_score(precision, recall),
        "key_coverage": _ratio(
            totals["common_key_count"], totals["expected_pair_count"]
        ),
        "value_accuracy": _ratio(
            totals["correct_pair_count"], totals["common_key_count"]
        ),
    }
