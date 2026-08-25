"""가림 면적 기반 객체 탐지 필터를 검증합니다."""

import unittest

from app.schemas.gemini_detection import (
    GeminiDetectionResult,
    GeminiRawDetection,
)
from app.services.furniture_detection_service import (
    filter_detections_by_visible_area,
)


def _detection(
    *,
    occluder_bbox: dict[str, float] | None,
) -> GeminiRawDetection:
    """고정된 대상 박스와 선택적인 가림 박스를 가진 탐지 객체를 만듭니다."""
    return GeminiRawDetection(
        category="의자",
        bbox_coord={"xmin": 0, "ymin": 0, "xmax": 100, "ymax": 100},
        occluder_bbox_coord=occluder_bbox,
        evidence="좌판과 등받이 구조가 보입니다.",
        confidence=0.9,
    )


def _result(*detections: GeminiRawDetection) -> GeminiDetectionResult:
    """주어진 객체 목록으로 탐지 결과를 만듭니다."""
    return GeminiDetectionResult(
        detections=list(detections),
        processing_time_ms=10,
    )


class VisibleAreaFilterTest(unittest.TestCase):
    """가림 객체 면적에 따른 탐지 객체 유지 여부를 검증합니다."""

    def test_keeps_detection_without_occluder(self) -> None:
        """가림 객체가 없으면 탐지 객체를 유지합니다."""
        result = filter_detections_by_visible_area(
            _result(_detection(occluder_bbox=None))
        )

        self.assertEqual(len(result.detections), 1)

    def test_keeps_detection_at_visible_area_threshold(self) -> None:
        """가시 면적이 정확히 75%이면 탐지 객체를 유지합니다."""
        result = filter_detections_by_visible_area(
            _result(
                _detection(
                    occluder_bbox={
                        "xmin": 0,
                        "ymin": 0,
                        "xmax": 25,
                        "ymax": 100,
                    }
                )
            )
        )

        self.assertEqual(len(result.detections), 1)

    def test_removes_detection_below_visible_area_threshold(self) -> None:
        """가시 면적이 75%보다 작으면 탐지 객체를 제거합니다."""
        result = filter_detections_by_visible_area(
            _result(
                _detection(
                    occluder_bbox={
                        "xmin": 0,
                        "ymin": 0,
                        "xmax": 26,
                        "ymax": 100,
                    }
                )
            )
        )

        self.assertEqual(result.detections, [])

    def test_uses_only_intersection_with_target_bbox(self) -> None:
        """가림 박스가 대상 밖으로 이어져도 교차한 면적만 차감합니다."""
        result = filter_detections_by_visible_area(
            _result(
                _detection(
                    occluder_bbox={
                        "xmin": 75,
                        "ymin": 0,
                        "xmax": 200,
                        "ymax": 100,
                    }
                )
            )
        )

        self.assertEqual(len(result.detections), 1)

    def test_keeps_detection_when_occluder_does_not_intersect(self) -> None:
        """가림 박스가 대상 박스 내부와 교차하지 않으면 객체를 유지합니다."""
        result = filter_detections_by_visible_area(
            _result(
                _detection(
                    occluder_bbox={
                        "xmin": 200,
                        "ymin": 200,
                        "xmax": 300,
                        "ymax": 300,
                    }
                )
            )
        )

        self.assertEqual(len(result.detections), 1)

    def test_does_not_compare_detection_boxes_with_each_other(self) -> None:
        """탐지 박스끼리 겹쳐도 가림 좌표가 없으면 모두 유지합니다."""
        result = filter_detections_by_visible_area(
            _result(
                _detection(occluder_bbox=None),
                _detection(occluder_bbox=None),
            )
        )

        self.assertEqual(len(result.detections), 2)


if __name__ == "__main__":
    unittest.main()
