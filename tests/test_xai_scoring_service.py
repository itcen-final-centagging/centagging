"""XAI 채점 실패 시 공개 폴백 계약을 검증합니다."""

import pathlib
import tempfile
import types
import typing
import unittest

from google.genai import errors
from PIL import Image

from app.core import config
from app.schemas import tagging
from app.services import gemini_service, xai_scoring_service
from app.services.image_processing_service import CroppedObject


class _RateLimitedModels:
    """Gemini 요청 한도 오류를 반환하는 모델 어댑터입니다."""

    def generate_content(self, **_kwargs: object) -> object:
        """429 ClientError를 발생시킵니다."""
        raise errors.ClientError(
            429,
            {"error": {"message": "Resource exhausted"}},
        )


class _RateLimitedClient:
    """429 모델 어댑터를 제공하는 Gemini 클라이언트 대역입니다."""

    def __init__(self) -> None:
        self.models = _RateLimitedModels()


class _RateLimitedScoringService(xai_scoring_service.XaiScoringService):
    """채점 단계에서 요청 한도 오류를 내는 테스트 어댑터입니다."""

    def score_all(
        self,
        _crops: list[xai_scoring_service.ScoringCrop],
    ) -> xai_scoring_service.RubricScoreResult:
        """Gemini 요청 한도 오류를 발생시킵니다."""
        raise gemini_service.GeminiRateLimitError("rate limited")


class _SuccessfulScoringService(xai_scoring_service.XaiScoringService):
    """고정된 XAI 채점 결과를 반환하는 테스트 어댑터입니다."""

    def score_all(
        self,
        _crops: list[xai_scoring_service.ScoringCrop],
    ) -> xai_scoring_service.RubricScoreResult:
        """후보 1건의 완료된 루브릭 결과를 반환합니다."""
        return xai_scoring_service.RubricScoreResult(
            crops=[
                xai_scoring_service.CropScore(
                    crop_index=0,
                    evaluations=[
                        xai_scoring_service.SkuEvaluation(
                            sku_id="CHR-2041",
                            status="Matched",
                            total_score=93,
                            xai_result=tagging.XaiResult(
                                summary="구조와 색상이 유사합니다."
                            ),
                        )
                    ],
                )
            ]
        )


def _build_xai_request(
    temp_dir: str,
) -> tuple[config.Settings, CroppedObject, tagging.DetectedObject]:
    """XAI 채점 공개 인터페이스에 전달할 입력을 만듭니다."""
    image_path = pathlib.Path(temp_dir) / "chair.png"
    Image.new("RGB", (10, 10), color="white").save(image_path)
    settings = typing.cast(
        config.Settings,
        types.SimpleNamespace(
            gemini_api_key="test-key",
            gemini_vlm_model="test-vlm",
            sku_image_root=temp_dir,
            image_storage_root=temp_dir,
        ),
    )
    candidate = tagging.SkuCandidate(
        sku_code="CHR-2041",
        product_name="사무용 의자",
        category="의자",
        sub_category="사무용의자",
        attrs={},
        similarity_score=91,
        matched_sku_image=tagging.MatchedSkuImage(
            sku_image_id=71,
            image_type="MAIN",
            image_url="chair.png",
        ),
        xai_result=tagging.XaiResult(summary="XAI 판정 결과가 없습니다."),
    )
    detected = tagging.DetectedObject(
        object_index=0,
        bbox=tagging.BoundingBox(
            xmin=0,
            ymin=0,
            xmax=1000,
            ymax=1000,
        ),
        sku_candidates=[candidate],
    )
    crop = CroppedObject(
        crop_index=0,
        bbox=detected.bbox,
        image=Image.new("RGB", (10, 10), color="white"),
        image_bytes=b"crop",
    )
    return settings, crop, detected


class XaiScoringServiceTest(unittest.TestCase):
    """Gemini 오류를 XAI 도메인 오류로 변환하는지 검증합니다."""

    def test_exposes_rate_limit_as_distinct_xai_error(self) -> None:
        """Gemini 429를 일반 채점 실패와 구분합니다."""
        settings = typing.cast(
            config.Settings,
            types.SimpleNamespace(
                gemini_api_key="test-key",
                gemini_vlm_model="test-vlm",
            ),
        )
        service = xai_scoring_service.XaiScoringService(settings)
        service._client = typing.cast(  # pylint: disable=protected-access
            typing.Any,
            _RateLimitedClient(),
        )
        crops = [
            xai_scoring_service.ScoringCrop(
                crop_index=0,
                crop_image_bytes=b"crop",
                candidates=[
                    xai_scoring_service.ScoringCandidate(
                        sku_code="CHR-2041",
                        image_bytes=b"sku",
                    )
                ],
            )
        ]

        with self.assertRaises(gemini_service.GeminiRateLimitError):
            service.score_all(crops)


class XaiFallbackContractTest(unittest.IsolatedAsyncioTestCase):
    """추천 후보에 노출되는 XAI 폴백 상태를 검증합니다."""

    async def test_rate_limit_keeps_candidate_with_fallback_status(
        self,
    ) -> None:
        """429가 발생해도 후보를 유지하고 RATE_LIMITED를 노출합니다."""
        with tempfile.TemporaryDirectory() as temp_dir:
            settings, crop, detected = _build_xai_request(temp_dir)
            service = _RateLimitedScoringService(settings)
            objects = await service.enrich_detected_objects([crop], [detected])

        self.assertEqual(len(objects[0].sku_candidates), 1)
        self.assertEqual(objects[0].sku_candidates[0].xai_status, "FALLBACK")
        self.assertEqual(
            objects[0].sku_candidates[0].xai_fallback_reason,
            "RATE_LIMITED",
        )

    async def test_success_marks_candidate_as_completed(self) -> None:
        """Gemini 채점 성공 후보는 폴백 원인을 제거합니다."""
        with tempfile.TemporaryDirectory() as temp_dir:
            settings, crop, detected = _build_xai_request(temp_dir)
            service = _SuccessfulScoringService(settings)

            objects = await service.enrich_detected_objects([crop], [detected])

        candidate = objects[0].sku_candidates[0]
        self.assertEqual(candidate.xai_status, "COMPLETED")
        self.assertIsNone(candidate.xai_fallback_reason)
        self.assertEqual(candidate.similarity_score, 93)


if __name__ == "__main__":
    unittest.main()
