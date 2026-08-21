"""실제 이미지 한 쌍으로 XAI 프롬프트 계약을 점검합니다."""

import argparse
import csv
import datetime
import io
import pathlib
import sys
import time
import typing

from PIL import Image

from app.core.config import get_settings
from app.services.xai_scoring_service import (
    RubricScoreResult,
    ScoringCandidate,
    ScoringCrop,
    XaiPromptVersion,
    XaiScoringService,
)

_CRITERIA_LIMITS = {
    "구조": 30,
    "색상": 30,
    "디테일": 20,
    "맥락": 20,
}

_CSV_FIELDS = (
    "evaluated_at",
    "case_id",
    "prompt_version",
    "model",
    "success",
    "duration_ms",
    "crop_coverage_rate",
    "sku_exact_once_rate",
    "criteria_complete_rate",
    "criteria_range_valid_rate",
    "score_sum_valid_rate",
    "status_threshold_valid_rate",
    "object_label_present_rate",
    "object_label_match_rate",
    "mood_present_rate",
    "total_score",
    "match_status",
    "error",
)


def _jpeg_bytes(image_path: pathlib.Path) -> bytes:
    """입력 이미지를 Gemini에 전달할 JPEG 바이트로 변환합니다."""
    with Image.open(image_path) as image:
        output = io.BytesIO()
        image.convert("RGB").save(output, format="JPEG", quality=95)
    return output.getvalue()


def _normalized_crop_bytes(
    image_path: pathlib.Path,
    row: dict[str, str],
) -> bytes:
    """정규화 좌표로 장면 이미지에서 평가용 Crop을 생성합니다."""
    coordinate_names = (
        "bbox_xmin",
        "bbox_ymin",
        "bbox_xmax",
        "bbox_ymax",
    )
    try:
        coordinates = [float(row[name]) for name in coordinate_names]
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            f"평가 케이스의 바운딩 박스가 올바르지 않습니다: {row}"
        ) from error

    with Image.open(image_path) as image:
        rgb_image = image.convert("RGB")
        width, height = rgb_image.size
        left, top, right, bottom = coordinates
        crop_box = (
            max(0, min(width - 1, round(left / 1000 * width))),
            max(0, min(height - 1, round(top / 1000 * height))),
            max(1, min(width, round(right / 1000 * width))),
            max(1, min(height, round(bottom / 1000 * height))),
        )
        if crop_box[2] <= crop_box[0] or crop_box[3] <= crop_box[1]:
            raise ValueError(f"Crop 좌표가 비어 있습니다: {crop_box}")
        output = io.BytesIO()
        rgb_image.crop(crop_box).save(output, format="JPEG", quality=95)
    return output.getvalue()


def _resolve_dataset_path(
    dataset_path: pathlib.Path,
    raw_path: str,
) -> pathlib.Path:
    """데이터셋 행의 절대·상대 파일 경로를 해석합니다."""
    path = pathlib.Path(raw_path)
    return path if path.is_absolute() else dataset_path.parent / path


def _load_samples(args: argparse.Namespace) -> list[dict[str, object]]:
    """단일 입력 또는 XAI 배치 데이터셋을 공통 샘플 목록으로 변환합니다."""
    if args.dataset:
        with args.dataset.open(encoding="utf-8-sig", newline="") as source:
            rows = list(csv.DictReader(source))
        if not rows:
            raise ValueError("XAI 평가 데이터셋에 데이터 행이 없습니다.")
        samples: list[dict[str, object]] = []
        required = {
            "case_id",
            "scene_image",
            "sku_code",
            "sku_image",
            "bbox_xmin",
            "bbox_ymin",
            "bbox_xmax",
            "bbox_ymax",
        }
        for row in rows:
            missing = sorted(name for name in required if not row.get(name))
            if missing:
                raise ValueError(
                    f"필수 필드가 없습니다(case_id={row.get('case_id')}): "
                    f"{', '.join(missing)}"
                )
            samples.append(
                {
                    "case_id": row["case_id"],
                    "crop_image": _resolve_dataset_path(
                        args.dataset, row["scene_image"]
                    ),
                    "sku_code": row["sku_code"],
                    "sku_image": _resolve_dataset_path(
                        args.dataset, row["sku_image"]
                    ),
                    "bbox": row,
                    "expected_label": row.get("expected_label", ""),
                }
            )
        return samples

    missing_args = (
        name
        for name in ("crop_image", "sku_code", "sku_image")
        if getattr(args, name) is None
    )
    missing = list(missing_args)
    if missing:
        raise ValueError(
            "단일 실행에는 다음 인자가 필요합니다: "
            + ", ".join(f"--{name.replace('_', '-')}" for name in missing)
        )
    return [
        {
            "case_id": "single",
            "crop_image": args.crop_image,
            "sku_code": args.sku_code,
            "sku_image": args.sku_image,
            "bbox": None,
            "expected_label": "",
        }
    ]


def _ratio(matched: int, expected: int) -> float:
    """0으로 나누지 않는 비율을 계산합니다."""
    return round(matched / expected, 6) if expected else 0.0


def _result_metrics(
    result: RubricScoreResult,
    sku_code: str,
    expected_label: str = "",
) -> dict[str, object]:
    """단일 crop·SKU 결과의 응답 계약 지표를 계산합니다."""
    matching_crops = [crop for crop in result.crops if crop.crop_index == 0]
    evaluations = [
        evaluation
        for crop in matching_crops
        for evaluation in crop.evaluations
        if evaluation.sku_id == sku_code
    ]

    crop_coverage = _ratio(len(matching_crops), 1)
    sku_exact_once = 1.0 if len(evaluations) == 1 else 0.0
    if not evaluations:
        return {
            "crop_coverage_rate": crop_coverage,
            "sku_exact_once_rate": sku_exact_once,
            "criteria_complete_rate": 0.0,
            "criteria_range_valid_rate": 0.0,
            "score_sum_valid_rate": 0.0,
            "status_threshold_valid_rate": 0.0,
            "object_label_present_rate": 0.0,
            "mood_present_rate": 0.0,
            "total_score": "",
            "match_status": "",
        }

    crop = matching_crops[0]
    evaluation = evaluations[0]
    criteria = evaluation.xai_result.criteria
    criteria_by_label = {criterion.label: criterion for criterion in criteria}
    criteria_complete = float(
        len(criteria) == len(_CRITERIA_LIMITS)
        and set(criteria_by_label) == set(_CRITERIA_LIMITS)
    )
    criteria_range_valid = float(
        criteria_complete == 1.0
        and all(
            0 <= criterion.score <= _CRITERIA_LIMITS[criterion.label]
            for criterion in criteria
        )
    )
    score_sum_valid = float(
        sum(criterion.score for criterion in criteria)
        == evaluation.total_score
    )
    expected_status = (
        "Matched" if evaluation.total_score >= 70 else "Rejected"
    )
    status_valid = float(evaluation.status == expected_status)
    mood = evaluation.xai_result.vlm_mood
    label_match = float(
        not expected_label
        or crop.label.strip() == expected_label.strip()
    )

    return {
        "crop_coverage_rate": crop_coverage,
        "sku_exact_once_rate": sku_exact_once,
        "criteria_complete_rate": criteria_complete,
        "criteria_range_valid_rate": criteria_range_valid,
        "score_sum_valid_rate": score_sum_valid,
        "status_threshold_valid_rate": status_valid,
        "object_label_present_rate": float(bool(crop.label.strip())),
        "object_label_match_rate": label_match,
        "mood_present_rate": float(bool(mood.summary.strip() and mood.tags)),
        "total_score": evaluation.total_score,
        "match_status": evaluation.status,
    }


def _run_version(
    *,
    prompt_version: XaiPromptVersion,
    crop_bytes: bytes,
    sku_code: str,
    sku_bytes: bytes,
    case_id: str,
    expected_label: str = "",
) -> dict[str, object]:
    """XAI 프롬프트 한 버전을 호출하고 스모크 지표를 반환합니다."""
    settings = get_settings()
    service = XaiScoringService(
        settings=settings,
        prompt_version=prompt_version,
    )
    targets = [
        ScoringCrop(
            crop_index=0,
            crop_image_bytes=crop_bytes,
            candidates=[
                ScoringCandidate(
                    sku_code=sku_code,
                    image_bytes=sku_bytes,
                )
            ],
        )
    ]
    started_at = time.perf_counter()
    try:
        result = service.score_all(targets)
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        return {
            "evaluated_at": datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat(),
            "case_id": case_id,
            "prompt_version": prompt_version,
            "model": settings.gemini_vlm_model,
            "success": 1,
            "duration_ms": duration_ms,
            **_result_metrics(result, sku_code, expected_label),
            "error": "",
        }
    except Exception as error:  # pylint: disable=broad-exception-caught
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        return {
            "evaluated_at": datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat(),
            "case_id": case_id,
            "prompt_version": prompt_version,
            "model": settings.gemini_vlm_model,
            "success": 0,
            "duration_ms": duration_ms,
            "crop_coverage_rate": 0.0,
            "sku_exact_once_rate": 0.0,
            "criteria_complete_rate": 0.0,
            "criteria_range_valid_rate": 0.0,
            "score_sum_valid_rate": 0.0,
            "status_threshold_valid_rate": 0.0,
            "object_label_present_rate": 0.0,
            "object_label_match_rate": 0.0,
            "mood_present_rate": 0.0,
            "total_score": "",
            "match_status": "",
            "error": f"{type(error).__name__}: {error}",
        }


def _parse_args() -> argparse.Namespace:
    """XAI 스모크 명령행 인자를 파싱합니다."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--crop-image", type=pathlib.Path)
    parser.add_argument("--sku-code")
    parser.add_argument("--sku-image", type=pathlib.Path)
    parser.add_argument(
        "--dataset",
        type=pathlib.Path,
        help=(
            "case_id,scene_image,sku_code,sku_image와 정규화 bbox 좌표를 "
            "담은 XAI 배치 CSV입니다."
        ),
    )
    parser.add_argument(
        "--prompt-versions",
        nargs="+",
        choices=("v1", "v2"),
        default=["v2"],
    )
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--request-interval-seconds", type=float, default=10)
    parser.add_argument("--confirm-live-calls", action="store_true")
    return parser.parse_args()


def main() -> int:
    """XAI 라이브 스모크를 실행하고 CSV 결과를 저장합니다."""
    args = _parse_args()
    if not args.confirm_live_calls:
        print("실제 모델 호출에는 --confirm-live-calls가 필요합니다.")
        return 2
    if args.request_interval_seconds < 0:
        print("요청 간격은 0 이상이어야 합니다.")
        return 2

    samples = _load_samples(args)
    rows: list[dict[str, object]] = []
    for sample_index, sample in enumerate(samples):
        crop_path = typing.cast(pathlib.Path, sample["crop_image"])
        bbox = typing.cast(dict[str, str] | None, sample["bbox"])
        crop_bytes = (
            _normalized_crop_bytes(crop_path, bbox)
            if bbox is not None
            else _jpeg_bytes(crop_path)
        )
        sku_path = typing.cast(pathlib.Path, sample["sku_image"])
        sku_bytes = _jpeg_bytes(sku_path)
        for version_index, version in enumerate(args.prompt_versions):
            if sample_index or version_index:
                time.sleep(args.request_interval_seconds)
            rows.append(
                _run_version(
                    prompt_version=typing.cast(XaiPromptVersion, version),
                    crop_bytes=crop_bytes,
                    sku_code=typing.cast(str, sample["sku_code"]),
                    sku_bytes=sku_bytes,
                    case_id=typing.cast(str, sample["case_id"]),
                    expected_label=typing.cast(
                        str, sample["expected_label"]
                    ),
                )
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"{args.output} ({len(samples)} samples, {len(rows)} calls)")
    return 0 if all(row["success"] == 1 for row in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
