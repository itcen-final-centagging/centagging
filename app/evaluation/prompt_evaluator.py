"""정답 데이터셋으로 Gemini 탐지·속성 프롬프트를 평가합니다."""

# pylint: disable=too-many-lines

import argparse
import concurrent.futures
import csv
import dataclasses
import datetime
import pathlib
import sys
import threading
import time
import typing
from collections.abc import Mapping, Sequence

from PIL import Image
from pydantic import BaseModel, Field, field_validator, model_validator

from app.core import config
from app.evaluation import prompt_csv_report, prompt_metrics
from app.schemas.furniture_attribute import FurnitureAttributeResult
from app.schemas.gemini_detection import (
    GeminiBoundingBox,
    GeminiDetectionResult,
)
from app.services.gemini_service import (
    GeminiCallTelemetry,
    GeminiService,
    PromptVersion,
)
from app.services.image_processing_service import decode_image, get_crop_image

_PROMPT_VERSIONS: tuple[PromptVersion, ...] = ("v1", "v2")
_EVALUATION_RETRY_DELAYS_SECONDS = (5.0, 15.0, 30.0)
_EVALUATION_RETRY_JITTER_SECONDS = 2.0


class ExpectedObject(BaseModel):
    """사람이 검수한 장면 이미지 내 정답 객체입니다."""

    category: str = Field(min_length=1)
    bbox_coord: GeminiBoundingBox
    sub_category: str | None = None
    attributes: dict[str, str] = Field(default_factory=dict)


class PromptEvaluationCase(BaseModel):
    """이미지 한 장과 해당 이미지의 정답 객체 목록입니다."""

    case_id: str = Field(min_length=1)
    image_path: str = Field(min_length=1)
    verified: bool = False
    notes: str = ""
    expected_objects: list[ExpectedObject] = Field(min_length=1)


class EvaluationThresholds(BaseModel):
    """리포트 성공 여부를 결정할 최소 품질과 최대 처리시간입니다."""

    min_detection_f1: float | None = Field(default=None, ge=0, le=1)
    min_detection_mean_iou: float | None = Field(default=None, ge=0, le=1)
    min_attribute_f1: float | None = Field(default=None, ge=0, le=1)
    min_korean_evidence_rate: float | None = Field(
        default=None,
        ge=0,
        le=1,
    )
    max_detection_p95_ms: float | None = Field(default=None, gt=0)
    max_attribute_batch_p95_ms: float | None = Field(default=None, gt=0)


class PromptEvaluationDataset(BaseModel):
    """프롬프트 평가 데이터셋과 통과 기준입니다."""

    dataset_name: str = Field(min_length=1)
    image_root: str = "."
    thresholds: EvaluationThresholds = Field(
        default_factory=EvaluationThresholds
    )
    cases: list[PromptEvaluationCase] = Field(min_length=1)


class PromptEvaluationCsvRow(BaseModel):
    """정답 데이터셋 CSV의 한 속성 행입니다."""

    dataset_name: str = Field(min_length=1)
    image_root: str = "."
    min_detection_f1: float | None = Field(default=None, ge=0, le=1)
    min_detection_mean_iou: float | None = Field(default=None, ge=0, le=1)
    min_attribute_f1: float | None = Field(default=None, ge=0, le=1)
    min_korean_evidence_rate: float | None = Field(default=None, ge=0, le=1)
    max_detection_p95_ms: float | None = Field(default=None, gt=0)
    max_attribute_batch_p95_ms: float | None = Field(default=None, gt=0)
    case_id: str = Field(min_length=1)
    image_path: str = Field(min_length=1)
    verified: bool = False
    notes: str = ""
    object_idx: int = Field(ge=0)
    category: str = Field(min_length=1)
    sub_category: str | None = None
    bbox_xmin: float = Field(ge=0, le=1000)
    bbox_ymin: float = Field(ge=0, le=1000)
    bbox_xmax: float = Field(ge=0, le=1000)
    bbox_ymax: float = Field(ge=0, le=1000)
    gt_bbox_xmin: float | None = Field(default=None, ge=0, le=1000)
    gt_bbox_ymin: float | None = Field(default=None, ge=0, le=1000)
    gt_bbox_xmax: float | None = Field(default=None, ge=0, le=1000)
    gt_bbox_ymax: float | None = Field(default=None, ge=0, le=1000)
    attribute_key: str | None = None
    attribute_value: str | None = None

    @field_validator(
        "min_detection_f1",
        "min_detection_mean_iou",
        "min_attribute_f1",
        "min_korean_evidence_rate",
        "max_detection_p95_ms",
        "max_attribute_batch_p95_ms",
        "sub_category",
        "gt_bbox_xmin",
        "gt_bbox_ymin",
        "gt_bbox_xmax",
        "gt_bbox_ymax",
        "attribute_key",
        "attribute_value",
        mode="before",
    )
    @classmethod
    def empty_string_to_none(cls, value: object) -> object:
        """빈 CSV 셀을 선택 필드의 None으로 변환합니다."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def validate_attribute_pair(self) -> "PromptEvaluationCsvRow":
        """속성 키와 값이 함께 입력되었는지 검증합니다."""
        if (self.attribute_key is None) != (self.attribute_value is None):
            raise ValueError(
                "attribute_key와 attribute_value를 함께 입력하세요."
            )
        ground_truth_values = (
            self.gt_bbox_xmin,
            self.gt_bbox_ymin,
            self.gt_bbox_xmax,
            self.gt_bbox_ymax,
        )
        if any(value is not None for value in ground_truth_values) and any(
            value is None for value in ground_truth_values
        ):
            raise ValueError("gt_bbox 좌표 네 개를 모두 입력하세요.")
        return self


@dataclasses.dataclass
class _CsvObjectAccumulator:
    """여러 CSV 속성 행을 하나의 정답 객체로 모읍니다."""

    category: str
    sub_category: str | None
    bbox_coord: GeminiBoundingBox
    attributes: dict[str, str]


@dataclasses.dataclass
class _CsvCaseAccumulator:
    """여러 CSV 객체 행을 하나의 평가 케이스로 모읍니다."""

    image_path: str
    verified: bool
    notes: str
    objects: dict[int, _CsvObjectAccumulator]


class EvaluationOptions(BaseModel):
    """한 번의 평가 실행에 적용할 반복·매칭 옵션입니다."""

    repetitions: int = Field(default=1, ge=1)
    iou_threshold: float = Field(default=0.5, ge=0, le=1)
    allow_unverified: bool = False
    request_interval_seconds: float = Field(default=0.0, ge=0)
    max_concurrent_attribute_calls: int = Field(default=1, ge=1)
    max_request_interval_seconds: float = Field(default=60.0, ge=0)
    rate_limit_cooldown_seconds: float = Field(default=60.0, ge=0)
    recovery_success_count: int = Field(default=3, ge=1)
    max_rate_limit_events: int = Field(default=3, ge=0)

    @model_validator(mode="after")
    def validate_adaptive_interval(self) -> "EvaluationOptions":
        """최대 호출 간격이 기본 호출 간격 이상인지 확인합니다."""
        if self.max_request_interval_seconds < self.request_interval_seconds:
            raise ValueError(
                "max_request_interval_seconds는 "
                "request_interval_seconds 이상이어야 합니다."
            )
        return self


class EvaluationRateLimitExceededError(RuntimeError):
    """평가 중 허용한 429 발생 횟수를 초과한 경우의 오류입니다."""


class _RequestPacer:  # pylint: disable=too-many-instance-attributes
    """평가 호출 간격과 429 이후의 전체 cooldown을 제어합니다."""

    def __init__(
        self,
        interval_seconds: float,
        *,
        max_interval_seconds: float | None = None,
        rate_limit_cooldown_seconds: float = 0.0,
        recovery_success_count: int = 3,
        max_rate_limit_events: int = 0,
    ) -> None:
        """기본 간격과 429 대응 정책을 저장합니다."""
        self._base_interval_seconds = interval_seconds
        self._current_interval_seconds = interval_seconds
        self._max_interval_seconds = (
            interval_seconds
            if max_interval_seconds is None
            else max_interval_seconds
        )
        self._rate_limit_cooldown_seconds = rate_limit_cooldown_seconds
        self._recovery_success_count = recovery_success_count
        self._max_rate_limit_events = max_rate_limit_events
        self._next_allowed_at = 0.0
        self._blocked_until = 0.0
        self._rate_limit_events = 0
        self._consecutive_successes = 0
        self._lock = threading.Lock()

    def wait(self) -> None:
        """다음 호출을 시작할 수 있을 때까지 필요한 시간만 기다립니다."""
        while True:
            with self._lock:
                self.raise_if_exhausted()
                now = time.monotonic()
                delay_seconds = max(
                    0.0,
                    self._next_allowed_at - now,
                    self._blocked_until - now,
                )
                if delay_seconds <= 0:
                    self._next_allowed_at = now + self._current_interval_seconds
                    return
            time.sleep(delay_seconds)

    def record_rate_limit(self, retry_delay_seconds: float) -> float:
        """429 발생 시 전체 호출을 멈추고 실제 대기시간을 반환합니다."""
        with self._lock:
            now = time.monotonic()
            cooldown_seconds = max(
                retry_delay_seconds,
                self._rate_limit_cooldown_seconds,
            )
            self._rate_limit_events += 1
            self._consecutive_successes = 0
            self._current_interval_seconds = min(
                self._max_interval_seconds,
                max(
                    self._base_interval_seconds,
                    self._current_interval_seconds * 2,
                ),
            )
            self._blocked_until = max(
                self._blocked_until,
                now + cooldown_seconds,
            )
            return cooldown_seconds

    def record_call_completed(self, telemetry: GeminiCallTelemetry) -> None:
        """재시도 없는 연속 성공 후 호출 간격을 점진적으로 복구합니다."""
        if not telemetry.generation_succeeded or telemetry.attempt_count > 1:
            return
        with self._lock:
            self._consecutive_successes += 1
            if self._consecutive_successes < self._recovery_success_count:
                return
            self._current_interval_seconds = max(
                self._base_interval_seconds,
                self._current_interval_seconds / 2,
            )
            self._consecutive_successes = 0

    def snapshot(self) -> dict[str, float | int]:
        """리포트에 기록할 adaptive pacing 상태를 반환합니다."""
        with self._lock:
            return {
                "rate_limit_events": self._rate_limit_events,
                "final_request_interval_seconds": (
                    self._current_interval_seconds
                ),
            }

    def raise_if_exhausted(self) -> None:
        """허용한 429 발생 횟수를 넘으면 다음 호출 전에 중단합니다."""
        if (
            self._max_rate_limit_events > 0
            and self._rate_limit_events > self._max_rate_limit_events
        ):
            raise EvaluationRateLimitExceededError(
                "Vertex AI 429 발생 횟수가 평가 허용치를 초과했습니다: "
                f"{self._rate_limit_events}회"
            )


class PromptEvaluationService(typing.Protocol):
    """평가 러너가 사용하는 Gemini 서비스 인터페이스입니다."""

    def detect_furniture(self, image: Image.Image) -> GeminiDetectionResult:
        """장면 이미지에서 가구 객체를 탐지합니다."""

    def extract_furniture_attributes(
        self,
        image: Image.Image,
        category: str,
    ) -> FurnitureAttributeResult:
        """Crop 이미지에서 가구 속성을 추출합니다."""


def _dataset_signature(row: PromptEvaluationCsvRow) -> tuple[object, ...]:
    """모든 CSV 행에서 동일해야 하는 데이터셋 설정을 반환합니다."""
    return (
        row.dataset_name,
        row.image_root,
        row.min_detection_f1,
        row.min_detection_mean_iou,
        row.min_attribute_f1,
        row.min_korean_evidence_rate,
        row.max_detection_p95_ms,
        row.max_attribute_batch_p95_ms,
    )


def _object_signature(row: PromptEvaluationCsvRow) -> tuple[object, ...]:
    """같은 객체 인덱스에서 동일해야 하는 객체 정답을 반환합니다."""
    bbox_coord = _ground_truth_bbox(row)
    return (
        row.category,
        row.sub_category,
        bbox_coord.xmin,
        bbox_coord.ymin,
        bbox_coord.xmax,
        bbox_coord.ymax,
    )


def _ground_truth_bbox(row: PromptEvaluationCsvRow) -> GeminiBoundingBox:
    """수동 정답 좌표를 우선하고 없으면 기존 좌표를 반환합니다."""
    if row.gt_bbox_xmin is not None:
        return GeminiBoundingBox(
            xmin=row.gt_bbox_xmin,
            ymin=typing.cast(float, row.gt_bbox_ymin),
            xmax=typing.cast(float, row.gt_bbox_xmax),
            ymax=typing.cast(float, row.gt_bbox_ymax),
        )

    return GeminiBoundingBox(
        xmin=row.bbox_xmin,
        ymin=row.bbox_ymin,
        xmax=row.bbox_xmax,
        ymax=row.bbox_ymax,
    )


def _append_csv_row(
    cases: dict[str, _CsvCaseAccumulator],
    row: PromptEvaluationCsvRow,
) -> None:
    """검증된 CSV 행을 케이스와 객체 단위로 결합합니다."""
    case = cases.setdefault(
        row.case_id,
        _CsvCaseAccumulator(
            image_path=row.image_path,
            verified=row.verified,
            notes=row.notes,
            objects={},
        ),
    )
    if (case.image_path, case.verified, case.notes) != (
        row.image_path,
        row.verified,
        row.notes,
    ):
        raise ValueError(
            f"동일 case_id의 값이 일치하지 않습니다: {row.case_id}"
        )

    object_item = case.objects.get(row.object_idx)
    if object_item is None:
        object_item = _CsvObjectAccumulator(
            category=row.category,
            sub_category=row.sub_category,
            bbox_coord=_ground_truth_bbox(row),
            attributes={},
        )
        case.objects[row.object_idx] = object_item
    elif _object_signature(row) != (
        object_item.category,
        object_item.sub_category,
        object_item.bbox_coord.xmin,
        object_item.bbox_coord.ymin,
        object_item.bbox_coord.xmax,
        object_item.bbox_coord.ymax,
    ):
        raise ValueError(
            "동일 객체 인덱스의 값이 일치하지 않습니다: "
            f"{row.case_id}/{row.object_idx}"
        )

    if row.attribute_key is None or row.attribute_value is None:
        return
    existing_value = object_item.attributes.get(row.attribute_key)
    if existing_value is not None and existing_value != row.attribute_value:
        raise ValueError(
            "동일 속성 키에 서로 다른 값이 있습니다: "
            f"{row.case_id}/{row.object_idx}/{row.attribute_key}"
        )
    object_item.attributes[row.attribute_key] = row.attribute_value


def load_dataset(dataset_path: pathlib.Path) -> PromptEvaluationDataset:
    """CSV 파일에서 프롬프트 평가 데이터셋을 읽습니다.

    Args:
        dataset_path: 평가 데이터셋 CSV 경로입니다.

    Returns:
        검증된 평가 데이터셋 모델입니다.
    """
    with dataset_path.open(encoding="utf-8-sig", newline="") as source:
        rows = [
            PromptEvaluationCsvRow.model_validate(row)
            for row in csv.DictReader(source)
        ]
    if not rows:
        raise ValueError("평가 데이터셋 CSV에 데이터 행이 없습니다.")

    dataset_signature = _dataset_signature(rows[0])
    cases: dict[str, _CsvCaseAccumulator] = {}
    for row in rows:
        if _dataset_signature(row) != dataset_signature:
            raise ValueError(
                "CSV 행별 데이터셋 설정과 임계값이 일치하지 않습니다."
            )
        _append_csv_row(cases, row)

    first = rows[0]
    return PromptEvaluationDataset(
        dataset_name=first.dataset_name,
        image_root=first.image_root,
        thresholds=EvaluationThresholds(
            min_detection_f1=first.min_detection_f1,
            min_detection_mean_iou=first.min_detection_mean_iou,
            min_attribute_f1=first.min_attribute_f1,
            min_korean_evidence_rate=first.min_korean_evidence_rate,
            max_detection_p95_ms=first.max_detection_p95_ms,
            max_attribute_batch_p95_ms=first.max_attribute_batch_p95_ms,
        ),
        cases=[
            PromptEvaluationCase(
                case_id=case_id,
                image_path=case.image_path,
                verified=case.verified,
                notes=case.notes,
                expected_objects=[
                    ExpectedObject(
                        category=item.category,
                        sub_category=item.sub_category,
                        bbox_coord=item.bbox_coord,
                        attributes=item.attributes,
                    )
                    for _, item in sorted(case.objects.items())
                ],
            )
            for case_id, case in cases.items()
        ],
    )


def _resolve_image_path(
    dataset_path: pathlib.Path,
    dataset: PromptEvaluationDataset,
    case: PromptEvaluationCase,
) -> pathlib.Path:
    """데이터셋 루트를 벗어나지 않는 이미지 경로를 계산합니다."""
    image_root = (dataset_path.parent / dataset.image_root).resolve()
    image_path = (image_root / case.image_path).resolve()
    try:
        image_path.relative_to(image_root)
    except ValueError as error:
        raise ValueError(
            f"평가 이미지가 image_root를 벗어났습니다: {case.case_id}"
        ) from error
    if not image_path.is_file():
        raise FileNotFoundError(f"평가 이미지를 찾을 수 없습니다: {image_path}")
    return image_path


def _elapsed_ms(started_at: float) -> float:
    """perf_counter 시작값으로부터 경과 밀리초를 계산합니다."""
    return round((time.perf_counter() - started_at) * 1000, 2)


def _float_value(value: object, field_name: str) -> float:
    """리포트 객체의 숫자 값을 안전하게 실수로 변환합니다."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} 지표가 숫자가 아닙니다.")
    return float(value)


def _expected_payloads(
    expected_objects: Sequence[ExpectedObject],
) -> list[dict[str, object]]:
    """정답 객체 모델을 지표 계산용 JSON 객체로 변환합니다."""
    return [
        typing.cast(
            dict[str, object],
            item.model_dump(mode="json", exclude_none=True),
        )
        for item in expected_objects
    ]


def _run_detection(
    service: PromptEvaluationService,
    image: Image.Image,
    expected: Sequence[Mapping[str, object]],
    iou_threshold: float,
    request_pacer: _RequestPacer,
) -> tuple[dict[str, object], prompt_metrics.MetricResult, float]:
    """객체 탐지를 한 번 실행하고 응답·품질·시간을 반환합니다."""
    request_pacer.wait()
    started_at = time.perf_counter()
    try:
        result = service.detect_furniture(image.copy())
        duration_ms = _elapsed_ms(started_at)
        actual = [
            typing.cast(
                dict[str, object],
                item.model_dump(mode="json"),
            )
            for item in result.detections
        ]
        metrics = prompt_metrics.evaluate_detection_response(
            expected,
            actual,
            iou_threshold,
        )
        response: dict[str, object] = {
            "objects": actual,
            "service_processing_time_ms": result.processing_time_ms,
            "error": None,
        }
    except Exception as error:  # pylint: disable=broad-exception-caught
        duration_ms = _elapsed_ms(started_at)
        metrics = prompt_metrics.evaluate_detection_response(
            expected,
            [],
            iou_threshold,
        )
        response = {
            "objects": [],
            "service_processing_time_ms": None,
            "error": f"{type(error).__name__}: {error}",
        }
    return response, metrics, duration_ms


def _run_attribute(
    service: PromptEvaluationService,
    crop_image: Image.Image,
    expected: ExpectedObject,
    request_pacer: _RequestPacer,
) -> tuple[dict[str, object], prompt_metrics.MetricResult, float]:
    """객체 속성 추출을 한 번 실행하고 응답·품질·시간을 반환합니다."""
    expected_payload = typing.cast(
        dict[str, object],
        expected.model_dump(mode="json", exclude_none=True),
    )
    request_pacer.wait()
    started_at = time.perf_counter()
    try:
        result = service.extract_furniture_attributes(
            crop_image.copy(),
            expected.category,
        )
        duration_ms = _elapsed_ms(started_at)
        actual = typing.cast(
            dict[str, object],
            result.model_dump(mode="json", exclude_none=True),
        )
        metrics = prompt_metrics.evaluate_attribute_response(
            expected_payload,
            actual,
        )
        response: dict[str, object] = {
            "actual": actual,
            "error": None,
        }
    except Exception as error:  # pylint: disable=broad-exception-caught
        duration_ms = _elapsed_ms(started_at)
        actual = {"category": "", "attributes": {}}
        metrics = prompt_metrics.evaluate_attribute_response(
            expected_payload,
            actual,
        )
        response = {
            "actual": None,
            "error": f"{type(error).__name__}: {error}",
        }
    return response, metrics, duration_ms


def _run_attribute_batch(
    service: PromptEvaluationService,
    image: Image.Image,
    expected_objects: Sequence[ExpectedObject],
    request_pacer: _RequestPacer,
    max_concurrent_calls: int,
) -> tuple[list[dict[str, object]], list[prompt_metrics.MetricResult], float]:
    """지정된 동시성 범위에서 객체별 속성 호출을 실행합니다."""
    crops = [
        get_crop_image(
            image,
            expected.bbox_coord.model_dump(mode="json"),
        )
        for expected in expected_objects
    ]
    started_at = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(max_concurrent_calls, len(expected_objects))
    ) as executor:
        futures = [
            executor.submit(
                _run_attribute,
                service,
                crop,
                expected,
                request_pacer,
            )
            for crop, expected in zip(crops, expected_objects)
        ]
        results = [future.result() for future in futures]

    batch_duration_ms = _elapsed_ms(started_at)
    responses = [
        {
            "category": expected.category,
            "duration_ms": duration_ms,
            **response,
        }
        for expected, (response, _, duration_ms) in zip(
            expected_objects,
            results,
        )
    ]
    metrics = [result_metrics for _, result_metrics, _ in results]
    return responses, metrics, batch_duration_ms


def _sum_errors(
    case_reports: Sequence[Mapping[str, object]],
    section: str,
) -> int:
    """케이스 리포트의 탐지 또는 속성 오류 개수를 합산합니다."""
    error_count = 0
    for case_report in case_reports:
        runs = case_report.get(section, [])
        if not isinstance(runs, list):
            continue
        if section == "detection_runs":
            error_count += sum(bool(run.get("error")) for run in runs)
            continue
        error_count += sum(
            bool(item.get("error"))
            for run in runs
            for item in run.get("objects", [])
        )
    return error_count


def _threshold_report(
    summary: Mapping[str, object],
    thresholds: EvaluationThresholds,
) -> dict[str, object]:
    """데이터셋의 완료 기준과 집계 지표를 비교합니다."""
    detection = typing.cast(Mapping[str, object], summary["detection"])
    attribute = typing.cast(Mapping[str, object], summary["attribute"])
    performance = typing.cast(Mapping[str, object], summary["performance"])
    detection_time = typing.cast(Mapping[str, object], performance["detection"])
    attribute_batch_time = typing.cast(
        Mapping[str, object], performance["attribute_batch"]
    )
    definitions = (
        (
            "detection_f1",
            detection.get("f1"),
            thresholds.min_detection_f1,
            "min",
        ),
        (
            "detection_mean_iou",
            detection.get("mean_iou"),
            thresholds.min_detection_mean_iou,
            "min",
        ),
        (
            "attribute_f1",
            attribute.get("f1"),
            thresholds.min_attribute_f1,
            "min",
        ),
        (
            "korean_evidence_rate",
            detection.get("korean_evidence_rate"),
            thresholds.min_korean_evidence_rate,
            "min",
        ),
        (
            "detection_p95_ms",
            detection_time.get("p95_ms"),
            thresholds.max_detection_p95_ms,
            "max",
        ),
        (
            "attribute_batch_p95_ms",
            attribute_batch_time.get("p95_ms"),
            thresholds.max_attribute_batch_p95_ms,
            "max",
        ),
    )
    checks = []
    for name, actual, target, comparison in definitions:
        if target is None:
            continue
        passed = (
            _float_value(actual, name) >= target
            if comparison == "min"
            else _float_value(actual, name) <= target
        )
        checks.append(
            {
                "metric": name,
                "actual": actual,
                "target": target,
                "comparison": comparison,
                "passed": passed,
            }
        )
    return {
        "passed": all(bool(check["passed"]) for check in checks),
        "checks": checks,
    }


# 케이스별 원시 응답과 집계 지표를 함께 조립하므로 지역 변수를 유지합니다.
# pylint: disable-next=too-many-locals,too-many-arguments
def evaluate_dataset(
    dataset: PromptEvaluationDataset,
    dataset_path: pathlib.Path,
    service: PromptEvaluationService,
    options: EvaluationOptions | None = None,
    *,
    prompt_version: str = "test",
    request_pacer: _RequestPacer | None = None,
) -> dict[str, object]:
    """데이터셋 전체에 대해 탐지·속성 품질과 처리시간을 측정합니다.

    Args:
        dataset: 사람이 정답을 작성한 평가 데이터셋입니다.
        dataset_path: 이미지 루트 계산에 사용할 데이터셋 파일 경로입니다.
        service: 실제 또는 테스트용 Gemini 서비스입니다.
        options: 반복 횟수, IoU 기준과 미검수 케이스 허용 여부입니다.
        prompt_version: 리포트에 기록할 프롬프트 버전입니다.
        request_pacer: 여러 버전이 공유할 평가 호출 제어기입니다.

    Returns:
        품질, 호출 횟수, 처리시간과 케이스별 응답이 담긴 리포트입니다.

    Raises:
        ValueError: 검수된 평가 케이스가 없는 경우입니다.
    """
    run_options = options or EvaluationOptions()
    cases = [
        case
        for case in dataset.cases
        if case.verified or run_options.allow_unverified
    ]
    if not cases:
        raise ValueError(
            "사람이 검수한 평가 케이스가 없습니다. "
            "CSV의 verified를 true로 바꾸거나 구조 확인용 실행에는 "
            "--allow-unverified를 지정하세요."
        )

    case_reports: list[dict[str, object]] = []
    detection_metrics: list[prompt_metrics.MetricResult] = []
    attribute_metrics: list[prompt_metrics.MetricResult] = []
    detection_durations: list[float] = []
    attribute_durations: list[float] = []
    attribute_batch_durations: list[float] = []
    active_request_pacer = request_pacer or _RequestPacer(
        run_options.request_interval_seconds,
        max_interval_seconds=run_options.max_request_interval_seconds,
        rate_limit_cooldown_seconds=(run_options.rate_limit_cooldown_seconds),
        recovery_success_count=run_options.recovery_success_count,
        max_rate_limit_events=run_options.max_rate_limit_events,
    )

    for case in cases:
        image_path = _resolve_image_path(dataset_path, dataset, case)
        image = decode_image(image_path.read_bytes())
        expected_payloads = _expected_payloads(case.expected_objects)
        detection_runs = []
        attribute_runs = []
        for repetition in range(1, run_options.repetitions + 1):
            response, metrics, duration_ms = _run_detection(
                service,
                image,
                expected_payloads,
                run_options.iou_threshold,
                active_request_pacer,
            )
            detection_metrics.append(metrics)
            detection_durations.append(duration_ms)
            detection_runs.append(
                {
                    "repetition": repetition,
                    "duration_ms": duration_ms,
                    "metrics": metrics,
                    **response,
                }
            )

            responses, metrics_list, batch_duration_ms = _run_attribute_batch(
                service,
                image,
                case.expected_objects,
                active_request_pacer,
                run_options.max_concurrent_attribute_calls,
            )
            attribute_metrics.extend(metrics_list)
            attribute_durations.extend(
                _float_value(response["duration_ms"], "duration_ms")
                for response in responses
            )
            attribute_batch_durations.append(batch_duration_ms)
            attribute_runs.append(
                {
                    "repetition": repetition,
                    "duration_ms": batch_duration_ms,
                    "objects": responses,
                }
            )

        case_reports.append(
            {
                "case_id": case.case_id,
                "image_path": str(image_path),
                "expected_object_count": len(case.expected_objects),
                "detection_runs": detection_runs,
                "attribute_runs": attribute_runs,
            }
        )

    detection_calls = len(cases) * run_options.repetitions
    attribute_calls = sum(len(case.expected_objects) for case in cases) * (
        run_options.repetitions
    )
    summary: dict[str, object] = {
        "detection": prompt_metrics.aggregate_detection_metrics(
            detection_metrics
        ),
        "attribute": prompt_metrics.aggregate_attribute_metrics(
            attribute_metrics
        ),
        "performance": {
            "detection": prompt_metrics.duration_statistics(
                detection_durations
            ),
            "attribute_call": prompt_metrics.duration_statistics(
                attribute_durations
            ),
            "attribute_batch": prompt_metrics.duration_statistics(
                attribute_batch_durations
            ),
        },
        "calls": {
            "detection_service_calls": detection_calls,
            "attribute_service_calls": attribute_calls,
            "gemini_generate_content_calls": detection_calls + attribute_calls,
            "failed_detection_calls": _sum_errors(
                case_reports,
                "detection_runs",
            ),
            "failed_attribute_calls": _sum_errors(
                case_reports,
                "attribute_runs",
            ),
        },
    }
    report: dict[str, object] = {
        "schema_version": 1,
        "generated_at": datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(),
        "dataset_name": dataset.dataset_name,
        "prompt_version": prompt_version,
        "evaluation_config": {
            "repetitions": run_options.repetitions,
            "iou_threshold": run_options.iou_threshold,
            "request_interval_seconds": (run_options.request_interval_seconds),
            "max_concurrent_attribute_calls": (
                run_options.max_concurrent_attribute_calls
            ),
            "max_request_interval_seconds": (
                run_options.max_request_interval_seconds
            ),
            "rate_limit_cooldown_seconds": (
                run_options.rate_limit_cooldown_seconds
            ),
            "recovery_success_count": run_options.recovery_success_count,
            "max_rate_limit_events": run_options.max_rate_limit_events,
            "verified_case_count": sum(case.verified for case in cases),
            "executed_case_count": len(cases),
        },
        "summary": summary,
        "acceptance": _threshold_report(summary, dataset.thresholds),
        "cases": case_reports,
    }
    return report


def _balanced_version_order(sequence_index: int) -> tuple[PromptVersion, ...]:
    """케이스·반복 순번에 따라 v1과 v2의 선행 순서를 교차합니다."""
    if sequence_index % 2 == 0:
        return _PROMPT_VERSIONS
    return tuple(reversed(_PROMPT_VERSIONS))


def _merge_case_reports(
    partial_reports: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """단일 케이스 리포트를 버전별 전체 케이스 리포트로 합칩니다."""
    merged: dict[str, dict[str, object]] = {}
    for report in partial_reports:
        for case_report in typing.cast(
            Sequence[Mapping[str, object]],
            report["cases"],
        ):
            case_id = str(case_report["case_id"])
            target = merged.setdefault(
                case_id,
                {
                    "case_id": case_id,
                    "image_path": case_report["image_path"],
                    "expected_object_count": case_report[
                        "expected_object_count"
                    ],
                    "detection_runs": [],
                    "attribute_runs": [],
                },
            )
            typing.cast(list[object], target["detection_runs"]).extend(
                typing.cast(Sequence[object], case_report["detection_runs"])
            )
            typing.cast(list[object], target["attribute_runs"]).extend(
                typing.cast(Sequence[object], case_report["attribute_runs"])
            )
    return list(merged.values())


def _partial_metric(
    report: Mapping[str, object],
    prompt_type: str,
) -> prompt_metrics.MetricResult:
    """단일 케이스 리포트에서 탐지 또는 속성 집계 지표를 가져옵니다."""
    summary = typing.cast(Mapping[str, object], report["summary"])
    return typing.cast(prompt_metrics.MetricResult, summary[prompt_type])


# 교차 실행의 부분 리포트와 원시 처리시간을 한 번에 합칩니다.
# pylint: disable-next=too-many-locals
def _merge_balanced_reports(
    dataset: PromptEvaluationDataset,
    cases: Sequence[PromptEvaluationCase],
    options: EvaluationOptions,
    prompt_version: PromptVersion,
    partial_reports: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """교차 실행된 단일 케이스 결과를 하나의 버전 리포트로 합칩니다."""
    case_reports = _merge_case_reports(partial_reports)
    detection_metrics = prompt_metrics.aggregate_detection_metrics(
        [_partial_metric(report, "detection") for report in partial_reports]
    )
    attribute_metrics = prompt_metrics.aggregate_attribute_metrics(
        [_partial_metric(report, "attribute") for report in partial_reports]
    )
    detection_metrics["run_count"] = sum(
        _partial_metric(report, "detection").get("run_count", 0)
        for report in partial_reports
    )
    attribute_metrics["result_count"] = sum(
        _partial_metric(report, "attribute").get("result_count", 0)
        for report in partial_reports
    )

    detection_durations = [
        _float_value(run["duration_ms"], "duration_ms")
        for case_report in case_reports
        for run in typing.cast(
            Sequence[Mapping[str, object]],
            case_report["detection_runs"],
        )
    ]
    attribute_runs = [
        run
        for case_report in case_reports
        for run in typing.cast(
            Sequence[Mapping[str, object]],
            case_report["attribute_runs"],
        )
    ]
    attribute_durations = [
        _float_value(item["duration_ms"], "duration_ms")
        for run in attribute_runs
        for item in typing.cast(
            Sequence[Mapping[str, object]],
            run["objects"],
        )
    ]
    attribute_batch_durations = [
        _float_value(run["duration_ms"], "duration_ms")
        for run in attribute_runs
    ]
    detection_calls = len(cases) * options.repetitions
    attribute_calls = sum(len(case.expected_objects) for case in cases) * (
        options.repetitions
    )
    summary: dict[str, object] = {
        "detection": detection_metrics,
        "attribute": attribute_metrics,
        "performance": {
            "detection": prompt_metrics.duration_statistics(
                detection_durations
            ),
            "attribute_call": prompt_metrics.duration_statistics(
                attribute_durations
            ),
            "attribute_batch": prompt_metrics.duration_statistics(
                attribute_batch_durations
            ),
        },
        "calls": {
            "detection_service_calls": detection_calls,
            "attribute_service_calls": attribute_calls,
            "gemini_generate_content_calls": detection_calls + attribute_calls,
            "failed_detection_calls": _sum_errors(
                case_reports,
                "detection_runs",
            ),
            "failed_attribute_calls": _sum_errors(
                case_reports,
                "attribute_runs",
            ),
        },
    }
    report: dict[str, object] = {
        "schema_version": 1,
        "generated_at": datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(),
        "dataset_name": dataset.dataset_name,
        "prompt_version": prompt_version,
        "evaluation_config": {
            "repetitions": options.repetitions,
            "iou_threshold": options.iou_threshold,
            "execution_schedule": "balanced",
            "request_interval_seconds": options.request_interval_seconds,
            "max_concurrent_attribute_calls": (
                options.max_concurrent_attribute_calls
            ),
            "max_request_interval_seconds": (
                options.max_request_interval_seconds
            ),
            "rate_limit_cooldown_seconds": (
                options.rate_limit_cooldown_seconds
            ),
            "recovery_success_count": options.recovery_success_count,
            "max_rate_limit_events": options.max_rate_limit_events,
            "verified_case_count": sum(case.verified for case in cases),
            "executed_case_count": len(cases),
        },
        "summary": summary,
        "acceptance": _threshold_report(summary, dataset.thresholds),
        "cases": case_reports,
    }
    return report


# 교차 순번과 버전별 부분 리포트를 함께 관리합니다.
# pylint: disable-next=too-many-locals
def _evaluate_balanced_versions(
    dataset: PromptEvaluationDataset,
    dataset_path: pathlib.Path,
    services: Mapping[PromptVersion, PromptEvaluationService],
    options: EvaluationOptions,
    request_pacer: _RequestPacer,
) -> dict[PromptVersion, dict[str, object]]:
    """케이스와 반복마다 선행 버전을 바꾸어 v1·v2를 평가합니다."""
    cases = [
        case
        for case in dataset.cases
        if case.verified or options.allow_unverified
    ]
    if not cases:
        raise ValueError("사람이 검수한 평가 케이스가 없습니다.")

    partial_options = options.model_copy(update={"repetitions": 1})
    partial_reports: dict[PromptVersion, list[dict[str, object]]] = {
        version: [] for version in _PROMPT_VERSIONS
    }
    for case_index, case in enumerate(cases):
        single_case_dataset = dataset.model_copy(update={"cases": [case]})
        for repetition in range(1, options.repetitions + 1):
            sequence_index = case_index * options.repetitions + repetition - 1
            for version in _balanced_version_order(sequence_index):
                report = evaluate_dataset(
                    single_case_dataset,
                    dataset_path,
                    services[version],
                    partial_options,
                    prompt_version=version,
                    request_pacer=request_pacer,
                )
                case_report = typing.cast(
                    list[dict[str, object]],
                    report["cases"],
                )[0]
                typing.cast(
                    list[dict[str, object]],
                    case_report["detection_runs"],
                )[0]["repetition"] = repetition
                typing.cast(
                    list[dict[str, object]],
                    case_report["attribute_runs"],
                )[0]["repetition"] = repetition
                partial_reports[version].append(report)

    request_pacer.raise_if_exhausted()
    return {
        version: _merge_balanced_reports(
            dataset,
            cases,
            options,
            version,
            partial_reports[version],
        )
        for version in _PROMPT_VERSIONS
    }


def _build_argument_parser() -> argparse.ArgumentParser:
    """프롬프트 평가 CLI 인자를 정의합니다."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=pathlib.Path,
        required=True,
        help="사람이 검수한 정답 데이터셋 CSV 경로입니다.",
    )
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--iou-threshold", type=float, default=0.5)
    parser.add_argument(
        "--request-interval-seconds",
        type=float,
        default=10.0,
        help="Gemini 호출 시작 사이의 최소 간격입니다.",
    )
    parser.add_argument(
        "--max-concurrent-attribute-calls",
        type=int,
        default=1,
        help="동시에 실행할 최대 속성 추출 호출 수입니다.",
    )
    parser.add_argument(
        "--max-request-interval-seconds",
        type=float,
        default=60.0,
        help="429 발생 후 늘릴 수 있는 최대 호출 간격입니다.",
    )
    parser.add_argument(
        "--rate-limit-cooldown-seconds",
        type=float,
        default=60.0,
        help="429 발생 시 모든 신규 호출을 중단할 최소 시간입니다.",
    )
    parser.add_argument(
        "--recovery-success-count",
        type=int,
        default=3,
        help="호출 간격을 완화하기 전에 필요한 연속 성공 횟수입니다.",
    )
    parser.add_argument(
        "--max-rate-limit-events",
        type=int,
        default=3,
        help="평가를 중단하기 전 허용할 429 응답 횟수입니다.",
    )
    parser.add_argument(
        "--version-cooldown-seconds",
        type=float,
        default=180.0,
        help="첫 번째 버전 평가 후 다음 버전까지 기다릴 시간입니다.",
    )
    parser.add_argument(
        "--version-order",
        choices=("balanced", "v1-first", "v2-first"),
        default="balanced",
        help="v1·v2를 교차하거나 한 버전을 먼저 실행합니다.",
    )
    parser.add_argument("--allow-unverified", action="store_true")
    parser.add_argument("--fail-on-threshold", action="store_true")
    parser.add_argument(
        "--confirm-live-calls",
        action="store_true",
        help="실제 Gemini 호출과 비용 발생을 확인합니다.",
    )
    return parser


def _attach_telemetry(
    report: dict[str, object],
    records: Sequence[GeminiCallTelemetry],
) -> None:
    """평가 리포트에 탐지·속성의 실제 호출 계측값을 추가합니다."""
    summary = report.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("summary 지표가 객체가 아닙니다.")
    summary["telemetry"] = {
        "detection": prompt_csv_report.summarize_telemetry(
            records,
            "detect_furniture",
        ),
        "attribute": prompt_csv_report.summarize_telemetry(
            records,
            "extract_furniture_attributes",
        ),
    }


def _runtime(settings: config.Settings) -> dict[str, str]:
    """CSV에 반복 기록할 모델 실행 환경을 반환합니다."""
    return {
        "model": settings.gemini_vlm_model,
        "provider": (
            "vertex_ai"
            if settings.gcp_project_id or settings.vertex_api_key
            else "gemini_developer_api"
        ),
        "location": settings.vertex_ai_location,
    }


def _create_evaluation_service(
    settings: config.Settings,
    prompt_version: PromptVersion,
    request_pacer: _RequestPacer,
) -> tuple[GeminiService, prompt_csv_report.PromptTelemetryCollector]:
    """평가 전용 재시도·계측 정책이 연결된 Gemini 서비스를 만듭니다."""
    collector = prompt_csv_report.PromptTelemetryCollector()

    def record_telemetry(telemetry: GeminiCallTelemetry) -> None:
        collector.record(telemetry)
        request_pacer.record_call_completed(telemetry)

    service = GeminiService(
        settings,
        prompt_version=prompt_version,
        telemetry_callback=record_telemetry,
        rate_limit_retry_delays_seconds=(_EVALUATION_RETRY_DELAYS_SECONDS),
        rate_limit_retry_jitter_seconds=(_EVALUATION_RETRY_JITTER_SECONDS),
        rate_limit_callback=request_pacer.record_rate_limit,
    )
    return service, collector


def _version_order(version_order: str) -> tuple[PromptVersion, ...]:
    """CLI의 실행 순서를 실제 프롬프트 버전 튜플로 변환합니다."""
    if version_order == "v1-first":
        return _PROMPT_VERSIONS
    if version_order == "v2-first":
        return tuple(reversed(_PROMPT_VERSIONS))
    raise ValueError(f"지원하지 않는 버전 실행 순서입니다: {version_order}")


def main(  # pylint: disable=too-many-locals
    argv: Sequence[str] | None = None,
) -> int:
    """실제 Gemini 프롬프트 평가를 실행합니다."""
    parser = _build_argument_parser()
    args = parser.parse_args(argv)
    if not args.confirm_live_calls:
        raise SystemExit(
            "실제 Gemini 호출에는 비용이 발생합니다. "
            "--confirm-live-calls를 지정하세요."
        )
    if args.version_cooldown_seconds < 0:
        parser.error("--version-cooldown-seconds는 0 이상이어야 합니다.")

    dataset_path = args.dataset.resolve()
    dataset = load_dataset(dataset_path)
    settings = config.get_settings()
    options = EvaluationOptions(
        repetitions=args.repetitions,
        iou_threshold=args.iou_threshold,
        allow_unverified=args.allow_unverified,
        request_interval_seconds=args.request_interval_seconds,
        max_concurrent_attribute_calls=(args.max_concurrent_attribute_calls),
        max_request_interval_seconds=args.max_request_interval_seconds,
        rate_limit_cooldown_seconds=args.rate_limit_cooldown_seconds,
        recovery_success_count=args.recovery_success_count,
        max_rate_limit_events=args.max_rate_limit_events,
    )
    runtime = _runtime(settings)
    request_pacer = _RequestPacer(
        options.request_interval_seconds,
        max_interval_seconds=options.max_request_interval_seconds,
        rate_limit_cooldown_seconds=options.rate_limit_cooldown_seconds,
        recovery_success_count=options.recovery_success_count,
        max_rate_limit_events=options.max_rate_limit_events,
    )
    service_runtimes = {
        version: _create_evaluation_service(
            settings,
            version,
            request_pacer,
        )
        for version in _PROMPT_VERSIONS
    }
    services: dict[PromptVersion, PromptEvaluationService] = {
        version: service for version, (service, _) in service_runtimes.items()
    }
    try:
        if args.version_order == "balanced":
            reports = _evaluate_balanced_versions(
                dataset,
                dataset_path,
                services,
                options,
                request_pacer,
            )
        else:
            reports = {}
            ordered_versions = _version_order(args.version_order)
            for version_index, version in enumerate(ordered_versions):
                reports[version] = evaluate_dataset(
                    dataset,
                    dataset_path,
                    services[version],
                    options,
                    prompt_version=version,
                    request_pacer=request_pacer,
                )
                request_pacer.raise_if_exhausted()
                if version_index < len(ordered_versions) - 1:
                    time.sleep(args.version_cooldown_seconds)
    except EvaluationRateLimitExceededError as error:
        print(f"평가를 중단했습니다: {error}", file=sys.stderr)
        return 2

    pacing_snapshot = request_pacer.snapshot()
    for version, report in reports.items():
        _, collector = service_runtimes[version]
        _attach_telemetry(report, collector.records())
        evaluation_config = typing.cast(
            dict[str, object],
            report["evaluation_config"],
        )
        evaluation_config.update(pacing_snapshot)
    rows_by_version = {
        version: prompt_csv_report.build_summary_rows(report, runtime)
        for version, report in reports.items()
    }
    summary_rows = [
        row for version in _PROMPT_VERSIONS for row in rows_by_version[version]
    ]
    comparison_rows = prompt_csv_report.build_comparison_rows(
        rows_by_version["v1"],
        rows_by_version["v2"],
    )
    summary_path, comparison_path = prompt_csv_report.write_csv_reports(
        args.output_dir.resolve(),
        summary_rows,
        comparison_rows,
    )
    print(summary_path)
    print(comparison_path)

    if args.fail_on_threshold:
        for report in reports.values():
            acceptance = typing.cast(
                Mapping[str, object],
                report["acceptance"],
            )
            if not acceptance.get("passed"):
                return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
