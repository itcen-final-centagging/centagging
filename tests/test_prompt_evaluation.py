"""프롬프트 평가 지표와 외부 호출 없는 평가 흐름을 검증합니다."""

# pylint: disable=protected-access

import copy
import csv
import pathlib
import tempfile
import types
import typing
import unittest
from unittest import mock

from PIL import Image

from app.core import config
from app.evaluation import prompt_evaluator, prompt_metrics
from app.schemas.furniture_attribute import FurnitureAttributeResult
from app.schemas.gemini_detection import (
    GeminiBoundingBox,
    GeminiDetectionResult,
    GeminiRawDetection,
)
from app.services import furniture_attribute_rules
from app.services.gemini_service import GeminiCallTelemetry, GeminiService


def _test_settings() -> config.Settings:
    """프롬프트 조립 테스트에 사용할 외부 호출 없는 설정을 생성합니다."""
    return config.Settings(
        gemini_api_key="test-key",
        gemini_vlm_model="gemini-test",
        gemini_embedding_model="embedding-test",
        mvp_login_id="",
        mvp_login_password="",
        image_storage_root="unused",
        sku_image_root="unused",
        database=config.DatabaseSettings(
            name="",
            username="",
            password="",
            host="",
            port=5432,
        ),
    )


def _object(
    category: str,
    bbox_coord: dict[str, float],
    **extra: object,
) -> dict[str, object]:
    """평가 지표 테스트에 사용할 객체를 만듭니다."""
    return {
        "category": category,
        "bbox_coord": bbox_coord,
        **extra,
    }


def _check_calculate_iou_for_partially_overlapping_boxes() -> None:
    """일부가 겹치는 두 박스의 IoU를 계산합니다."""
    first = {"xmin": 0, "ymin": 0, "xmax": 100, "ymax": 100}
    second = {"xmin": 50, "ymin": 0, "xmax": 150, "ymax": 100}

    assert round(prompt_metrics.calculate_iou(first, second), 4) == 0.3333


def _check_evaluate_detection_response_reports_quality_rates() -> None:
    """탐지 결과의 박스·카테고리·근거·신뢰도 지표를 계산합니다."""
    expected = [
        _object(
            "의자",
            {"xmin": 0, "ymin": 0, "xmax": 100, "ymax": 100},
        )
    ]
    actual = [
        _object(
            "의자",
            {"xmin": 0, "ymin": 0, "xmax": 100, "ymax": 100},
            confidence=0.9,
            evidence="등받이와 좌판이 보이는 의자입니다.",
        ),
        _object(
            "소파",
            {"xmin": 500, "ymin": 500, "xmax": 700, "ymax": 700},
            confidence=0.8,
            evidence="sofa",
        ),
    ]

    metrics = prompt_metrics.evaluate_detection_response(expected, actual)

    assert metrics["mean_iou"] == 1.0
    assert metrics["precision"] == 0.5
    assert metrics["recall"] == 1.0
    assert round(float(metrics["f1"]), 4) == 0.6667
    assert metrics["confidence_present_rate"] == 1.0
    assert metrics["korean_evidence_rate"] == 0.5


def _check_evaluate_attribute_response_reports_pair_accuracy() -> None:
    """동적 속성 key/value 쌍의 정확도와 커버리지를 계산합니다."""
    expected = {
        "category": "의자",
        "sub_category": "인테리어의자",
        "attributes": {"color": "블랙", "material": "가죽"},
    }
    actual = {
        "category": "의자",
        "sub_category": "인테리어의자",
        "attributes": {
            "color": "블랙",
            "material": "패브릭",
            "style": "모던",
        },
    }

    metrics = prompt_metrics.evaluate_attribute_response(expected, actual)

    assert metrics["category_correct_count"] == 1
    assert metrics["sub_category_correct_count"] == 1
    assert metrics["correct_pair_count"] == 1
    assert round(float(metrics["precision"]), 4) == 0.3333
    assert metrics["recall"] == 0.5
    assert metrics["key_coverage"] == 1.0
    assert metrics["value_accuracy"] == 0.5


def _check_duration_statistics_reports_median_and_p95() -> None:
    """반복 호출 처리시간의 평균·중앙값·P95를 계산합니다."""
    metrics = prompt_metrics.duration_statistics([10, 20, 30, 40])

    assert metrics == {
        "count": 4,
        "min_ms": 10,
        "average_ms": 25.0,
        "median_ms": 25.0,
        "p95_ms": 40,
        "max_ms": 40,
    }


class _FakePromptService:
    """외부 Gemini 호출 없이 완전 일치 응답을 반환합니다."""

    def detect_furniture(self, image: Image.Image) -> GeminiDetectionResult:
        """정답과 같은 의자 한 개를 반환합니다."""
        del image
        return GeminiDetectionResult(
            detections=[
                GeminiRawDetection(
                    category="의자",
                    bbox_coord=GeminiBoundingBox(
                        xmin=100,
                        ymin=100,
                        xmax=900,
                        ymax=900,
                    ),
                    evidence="등받이와 좌판이 보이는 의자입니다.",
                    confidence=0.95,
                )
            ],
            processing_time_ms=10,
        )

    def extract_furniture_attributes(
        self,
        image: Image.Image,
        category: str,
    ) -> FurnitureAttributeResult:
        """정답과 같은 속성을 반환합니다."""
        del image
        return FurnitureAttributeResult(
            category=category,
            sub_category="인테리어의자",
            attributes={"color": "블랙", "material": "가죽"},
        )


class _TrackingPromptService(_FakePromptService):
    """호출된 프롬프트 버전과 작업 순서를 기록합니다."""

    def __init__(self, version: str, calls: list[str]) -> None:
        """기록할 버전과 공유 호출 목록을 저장합니다."""
        self._version = version
        self._calls = calls

    def detect_furniture(self, image: Image.Image) -> GeminiDetectionResult:
        """탐지 호출 순서를 기록하고 완전 일치 응답을 반환합니다."""
        self._calls.append(f"{self._version}:detect")
        return super().detect_furniture(image)

    def extract_furniture_attributes(
        self,
        image: Image.Image,
        category: str,
    ) -> FurnitureAttributeResult:
        """속성 호출 순서를 기록하고 완전 일치 응답을 반환합니다."""
        self._calls.append(f"{self._version}:attribute")
        return super().extract_furniture_attributes(image, category)


def _check_evaluate_dataset_builds_quality_time_and_call_report() -> None:
    """평가 러너가 품질·시간·호출 횟수 리포트를 함께 생성합니다."""
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = pathlib.Path(temporary_directory)
        image_path = root / "scene.png"
        Image.new("RGB", (100, 100), "white").save(image_path)
        dataset_path = root / "dataset.csv"
        dataset = prompt_evaluator.PromptEvaluationDataset(
            dataset_name="unit-test",
            thresholds=prompt_evaluator.EvaluationThresholds(
                min_detection_f1=1.0,
                min_detection_mean_iou=1.0,
                min_attribute_f1=1.0,
                min_korean_evidence_rate=1.0,
            ),
            cases=[
                prompt_evaluator.PromptEvaluationCase(
                    case_id="chair-1",
                    image_path="scene.png",
                    verified=True,
                    expected_objects=[
                        prompt_evaluator.ExpectedObject(
                            category="의자",
                            sub_category="인테리어의자",
                            bbox_coord=GeminiBoundingBox(
                                xmin=100,
                                ymin=100,
                                xmax=900,
                                ymax=900,
                            ),
                            attributes={
                                "color": "블랙",
                                "material": "가죽",
                            },
                        )
                    ],
                )
            ],
        )

        report = prompt_evaluator.evaluate_dataset(
            dataset,
            dataset_path,
            _FakePromptService(),
            prompt_evaluator.EvaluationOptions(repetitions=2),
        )

    summary = report["summary"]
    assert isinstance(summary, dict)
    assert summary["detection"]["f1"] == 1.0
    assert summary["attribute"]["f1"] == 1.0
    assert summary["calls"] == {
        "detection_service_calls": 2,
        "attribute_service_calls": 2,
        "gemini_generate_content_calls": 4,
        "failed_detection_calls": 0,
        "failed_attribute_calls": 0,
    }
    acceptance = typing.cast(dict[str, object], report["acceptance"])
    assert acceptance["passed"] is True


def _check_balanced_evaluation_alternates_leading_version() -> None:
    """연속 케이스에서 v1과 v2의 선행 실행 순서를 교차합니다."""
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = pathlib.Path(temporary_directory)
        image_path = root / "scene.png"
        Image.new("RGB", (100, 100), "white").save(image_path)
        expected_object = prompt_evaluator.ExpectedObject(
            category="의자",
            sub_category="인테리어의자",
            bbox_coord=GeminiBoundingBox(
                xmin=100,
                ymin=100,
                xmax=900,
                ymax=900,
            ),
            attributes={"color": "블랙", "material": "가죽"},
        )
        dataset = prompt_evaluator.PromptEvaluationDataset(
            dataset_name="balanced-test",
            cases=[
                prompt_evaluator.PromptEvaluationCase(
                    case_id=f"chair-{case_index}",
                    image_path="scene.png",
                    verified=True,
                    expected_objects=[expected_object],
                )
                for case_index in range(2)
            ],
        )
        calls: list[str] = []
        services = {
            "v1": _TrackingPromptService("v1", calls),
            "v2": _TrackingPromptService("v2", calls),
        }
        reports = prompt_evaluator._evaluate_balanced_versions(
            dataset,
            root / "dataset.csv",
            services,
            prompt_evaluator.EvaluationOptions(repetitions=1),
            prompt_evaluator._RequestPacer(0.0),
        )

    assert calls == [
        "v1:detect",
        "v1:attribute",
        "v2:detect",
        "v2:attribute",
        "v2:detect",
        "v2:attribute",
        "v1:detect",
        "v1:attribute",
    ]
    for report in reports.values():
        summary = typing.cast(dict[str, object], report["summary"])
        assert summary["calls"] == {
            "detection_service_calls": 2,
            "attribute_service_calls": 2,
            "gemini_generate_content_calls": 4,
            "failed_detection_calls": 0,
            "failed_attribute_calls": 0,
        }


def _evaluation_report(prompt_version: str) -> dict[str, object]:
    """CSV 출력 테스트에 사용할 완전 일치 평가 리포트를 생성합니다."""
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = pathlib.Path(temporary_directory)
        image_path = root / "scene.png"
        Image.new("RGB", (100, 100), "white").save(image_path)
        dataset_path = root / "dataset.csv"
        dataset = prompt_evaluator.PromptEvaluationDataset(
            dataset_name="unit-test",
            thresholds=prompt_evaluator.EvaluationThresholds(
                min_detection_f1=0.8,
                min_detection_mean_iou=0.6,
                min_attribute_f1=0.7,
            ),
            cases=[
                prompt_evaluator.PromptEvaluationCase(
                    case_id="chair-1",
                    image_path="scene.png",
                    verified=True,
                    expected_objects=[
                        prompt_evaluator.ExpectedObject(
                            category="의자",
                            sub_category="인테리어의자",
                            bbox_coord=GeminiBoundingBox(
                                xmin=100,
                                ymin=100,
                                xmax=900,
                                ymax=900,
                            ),
                            attributes={
                                "color": "블랙",
                                "material": "가죽",
                            },
                        )
                    ],
                )
            ],
        )
        return prompt_evaluator.evaluate_dataset(
            dataset,
            dataset_path,
            _FakePromptService(),
            prompt_evaluator.EvaluationOptions(repetitions=1),
            prompt_version=prompt_version,
        )


def _check_csv_report_contains_compact_metrics_and_comparison() -> None:
    """원시 응답 대신 압축 지표와 v1·v2 비교 CSV를 생성합니다."""
    v1_report = _evaluation_report("v1")
    v2_report = copy.deepcopy(v1_report)
    v2_report["prompt_version"] = "v2"
    telemetry = [
        GeminiCallTelemetry(
            operation_name="detect_furniture",
            prompt_version="v1",
            attempt_count=2,
            input_tokens=80,
            output_tokens=20,
            total_tokens=100,
            generation_succeeded=True,
        ),
        GeminiCallTelemetry(
            operation_name="extract_furniture_attributes",
            prompt_version="v1",
            attempt_count=1,
            input_tokens=120,
            output_tokens=30,
            total_tokens=150,
            generation_succeeded=True,
        ),
    ]
    prompt_evaluator._attach_telemetry(v1_report, telemetry)
    prompt_evaluator._attach_telemetry(v2_report, telemetry)
    runtime = {
        "model": "gemini-test",
        "provider": "vertex_ai",
        "location": "global",
    }
    v1_rows = prompt_evaluator.prompt_csv_report.build_summary_rows(
        v1_report,
        runtime,
    )
    v2_rows = prompt_evaluator.prompt_csv_report.build_summary_rows(
        v2_report,
        runtime,
    )
    comparison = prompt_evaluator.prompt_csv_report.build_comparison_rows(
        v1_rows,
        v2_rows,
    )

    detection_efficiency = next(
        row
        for row in v1_rows
        if row["metric"] == "correct_objects_per_1k_tokens"
    )
    retry_rate = next(
        row
        for row in v1_rows
        if row["prompt_type"] == "detection" and row["metric"] == "retry_rate"
    )
    assert detection_efficiency["value"] == 10.0
    assert retry_rate["value"] == 1.0
    assert comparison
    assert all(row["winner"] == "tie" for row in comparison)

    with tempfile.TemporaryDirectory() as temporary_directory:
        summary_path, comparison_path = (
            prompt_evaluator.prompt_csv_report.write_csv_reports(
                pathlib.Path(temporary_directory),
                [*v1_rows, *v2_rows],
                comparison,
            )
        )
        with summary_path.open(encoding="utf-8-sig", newline="") as source:
            summary_records = list(csv.DictReader(source))
        with comparison_path.open(encoding="utf-8-sig", newline="") as source:
            comparison_records = list(csv.DictReader(source))

    assert summary_records
    assert comparison_records
    assert not any("objects" in row for row in summary_records)


def _check_csv_dataset_groups_dynamic_attributes() -> None:
    """긴 형식 CSV의 속성 행을 동일 객체의 동적 딕셔너리로 결합합니다."""
    base_row = {
        "dataset_name": "csv-unit-test",
        "image_root": ".",
        "min_detection_f1": "0.8",
        "min_detection_mean_iou": "0.6",
        "min_attribute_f1": "0.7",
        "min_korean_evidence_rate": "1.0",
        "max_detection_p95_ms": "20000",
        "max_attribute_batch_p95_ms": "20000",
        "case_id": "chair-case",
        "image_path": "scene.png",
        "verified": "true",
        "notes": "사람 검수 완료",
        "object_idx": "0",
        "category": "의자",
        "sub_category": "인테리어의자",
        "bbox_xmin": "100",
        "bbox_ymin": "100",
        "bbox_xmax": "900",
        "bbox_ymax": "900",
        "gt_bbox_xmin": "110",
        "gt_bbox_ymin": "120",
        "gt_bbox_xmax": "880",
        "gt_bbox_ymax": "890",
    }
    rows = [
        {**base_row, "attribute_key": "color", "attribute_value": "블랙"},
        {
            **base_row,
            "attribute_key": "material",
            "attribute_value": "가죽",
        },
    ]

    with tempfile.TemporaryDirectory() as temporary_directory:
        dataset_path = pathlib.Path(temporary_directory) / "dataset.csv"
        with dataset_path.open("w", encoding="utf-8-sig", newline="") as target:
            writer = csv.DictWriter(
                target,
                fieldnames=list(
                    prompt_evaluator.PromptEvaluationCsvRow.model_fields
                ),
            )
            writer.writeheader()
            writer.writerows(rows)
        dataset = prompt_evaluator.load_dataset(dataset_path)

    assert dataset.dataset_name == "csv-unit-test"
    assert getattr(dataset.thresholds, "min_detection_f1") == 0.8
    assert len(dataset.cases) == 1
    assert dataset.cases[0].verified is True
    assert dataset.cases[0].expected_objects[0].bbox_coord.model_dump() == {
        "xmin": 110.0,
        "ymin": 120.0,
        "xmax": 880.0,
        "ymax": 890.0,
    }
    assert dataset.cases[0].expected_objects[0].attributes == {
        "color": "블랙",
        "material": "가죽",
    }


def _check_prompt_versions_build_distinct_inputs() -> None:
    """v1·v2 서비스가 서로 다른 탐지·속성 프롬프트를 조립합니다."""
    image = Image.new("RGB", (20, 20), "white")
    attribute_schema = furniture_attribute_rules.build_allowed_attribute_schema(
        "의자"
    )
    v1_service = GeminiService(_test_settings(), prompt_version="v1")
    v2_service = GeminiService(_test_settings(), prompt_version="v2")

    v1_detection = v1_service._build_detection_contents(image)
    v2_detection = v2_service._build_detection_contents(image)
    v1_attribute = v1_service._build_attribute_contents(
        image,
        attribute_schema,
    )
    v2_attribute = v2_service._build_attribute_contents(
        image,
        attribute_schema,
    )

    assert len(v1_detection) == 2
    assert len(v2_detection) == 2
    assert "가구 인스턴스 탐지 모델" in str(v1_detection[1])
    assert "최소 가시 비율: 약 50%" in str(v1_detection[1])
    assert "바운딩 박스 중심점" in str(v1_detection[1])
    assert "테이블·식탁·책상" in str(v1_detection[1])
    assert "판정 우선순위" in str(v2_detection[1])
    assert len(v1_attribute) == 2
    assert len(v2_attribute) == 2
    assert "가구 속성 추출 모델" in str(v1_attribute[1])
    assert '"has_armrest"' in str(v1_attribute[1])
    assert "시각적 속성을 분류하는 모델" in str(v2_attribute[1])
    assert '"has_armrest"' in str(v2_attribute[1])


def _check_gemini_service_records_usage_metadata() -> None:
    """Gemini 응답의 실제 토큰과 시도 횟수를 계측값으로 전달합니다."""
    records: list[GeminiCallTelemetry] = []
    service = GeminiService(
        _test_settings(),
        prompt_version="v2",
        telemetry_callback=records.append,
    )
    response = types.SimpleNamespace(
        usage_metadata=types.SimpleNamespace(
            prompt_token_count=120,
            candidates_token_count=30,
            total_token_count=150,
        )
    )

    service._record_telemetry(
        operation_name="detect_furniture",
        response=typing.cast(typing.Any, response),
        attempt_count=2,
        generation_succeeded=True,
    )

    assert records == [
        GeminiCallTelemetry(
            operation_name="detect_furniture",
            prompt_version="v2",
            attempt_count=2,
            input_tokens=120,
            output_tokens=30,
            total_tokens=150,
            generation_succeeded=True,
        )
    ]


def _check_request_pacer_spaces_concurrent_calls() -> None:
    """평가 호출 시작 사이에 설정한 최소 간격을 적용합니다."""
    pacer = prompt_evaluator._RequestPacer(3.0)

    with (
        mock.patch(
            "app.evaluation.prompt_evaluator.time.monotonic",
            side_effect=[10.0, 11.0, 13.0],
        ),
        mock.patch("app.evaluation.prompt_evaluator.time.sleep") as sleep,
    ):
        pacer.wait()
        pacer.wait()

    sleep.assert_called_once_with(2.0)


def _check_request_pacer_adapts_and_stops_after_rate_limits() -> None:
    """429 이후 간격을 늘리고 허용 횟수 초과 시 평가를 중단합니다."""
    pacer = prompt_evaluator._RequestPacer(
        10.0,
        max_interval_seconds=60.0,
        rate_limit_cooldown_seconds=60.0,
        recovery_success_count=2,
        max_rate_limit_events=1,
    )
    telemetry = GeminiCallTelemetry(
        operation_name="detect_furniture",
        prompt_version="v1",
        attempt_count=1,
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        generation_succeeded=True,
    )

    with mock.patch(
        "app.evaluation.prompt_evaluator.time.monotonic",
        side_effect=[100.0, 200.0],
    ):
        assert pacer.record_rate_limit(5.0) == 60.0
        assert pacer.snapshot() == {
            "rate_limit_events": 1,
            "final_request_interval_seconds": 20.0,
        }
        pacer.record_call_completed(telemetry)
        pacer.record_call_completed(telemetry)
        assert pacer.snapshot()["final_request_interval_seconds"] == 10.0
        pacer.record_rate_limit(5.0)

    try:
        pacer.wait()
    except prompt_evaluator.EvaluationRateLimitExceededError:
        pass
    else:
        raise AssertionError(
            "429 허용 횟수 초과 시 평가가 중단되지 않았습니다."
        )


def _check_version_order_can_be_reversed() -> None:
    """독립 평가 실행마다 v1·v2 선행 순서를 선택할 수 있습니다."""
    assert prompt_evaluator._version_order("v1-first") == ("v1", "v2")
    assert prompt_evaluator._version_order("v2-first") == ("v2", "v1")
    assert prompt_evaluator._balanced_version_order(0) == ("v1", "v2")
    assert prompt_evaluator._balanced_version_order(1) == ("v2", "v1")


class PromptEvaluationTest(unittest.TestCase):
    """프롬프트 평가 모듈의 외부 호출 없는 단위 테스트입니다."""

    def test_calculate_iou(self) -> None:
        """일부가 겹치는 박스의 IoU를 검증합니다."""
        _check_calculate_iou_for_partially_overlapping_boxes()

    def test_detection_metrics(self) -> None:
        """탐지 품질 지표를 검증합니다."""
        _check_evaluate_detection_response_reports_quality_rates()

    def test_attribute_metrics(self) -> None:
        """속성 품질 지표를 검증합니다."""
        _check_evaluate_attribute_response_reports_pair_accuracy()

    def test_duration_statistics(self) -> None:
        """처리시간 통계를 검증합니다."""
        _check_duration_statistics_reports_median_and_p95()

    def test_prompt_versions(self) -> None:
        """v1·v2가 각각의 탐지·속성 프롬프트를 사용함을 검증합니다."""
        _check_prompt_versions_build_distinct_inputs()

    def test_usage_metadata(self) -> None:
        """실제 토큰과 재시도 시도 횟수의 계측을 검증합니다."""
        _check_gemini_service_records_usage_metadata()

    def test_request_pacer(self) -> None:
        """평가 호출 시작 간격이 제한되는지 검증합니다."""
        _check_request_pacer_spaces_concurrent_calls()

    def test_adaptive_request_pacer(self) -> None:
        """429에 따라 전체 호출 간격과 중단 기준이 조정되는지 검증합니다."""
        _check_request_pacer_adapts_and_stops_after_rate_limits()

    def test_version_order(self) -> None:
        """평가 버전 실행 순서를 바꿀 수 있는지 검증합니다."""
        _check_version_order_can_be_reversed()

    def test_dataset_report(self) -> None:
        """전체 평가 리포트 생성을 검증합니다."""
        _check_evaluate_dataset_builds_quality_time_and_call_report()

    def test_balanced_evaluation(self) -> None:
        """케이스마다 v1·v2의 선행 실행 순서가 교차되는지 검증합니다."""
        _check_balanced_evaluation_alternates_leading_version()

    def test_csv_report(self) -> None:
        """압축 지표와 v1·v2 비교 CSV 출력을 검증합니다."""
        _check_csv_report_contains_compact_metrics_and_comparison()

    def test_csv_dataset(self) -> None:
        """CSV 정답 데이터의 객체·동적 속성 결합을 검증합니다."""
        _check_csv_dataset_groups_dynamic_attributes()
