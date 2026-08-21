"""XAI 채점 실패 시 공개 폴백 계약을 검증합니다."""

import json
import pathlib
import tempfile
import types
import typing
import unittest
from unittest import mock

from google.genai import errors
from PIL import Image

from app.core import config
from app.schemas import tagging
from app.services import gemini_service, tagging_service, xai_scoring_service
from app.services.image_processing_service import CroppedObject
from app.services.prompt.xai_prompt.xai_prompt import (
    build_xai_prompt as build_xai_prompt_v1,
)
from app.services.prompt.xai_prompt.xai_prompt_v2 import (
    build_xai_prompt as build_xai_prompt_v2,
)


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
        crops: list[xai_scoring_service.ScoringCrop],
    ) -> xai_scoring_service.RubricScoreResult:
        """후보 1건의 완료된 루브릭 결과를 반환합니다."""
        return xai_scoring_service.RubricScoreResult(
            crops=[
                xai_scoring_service.CropScore(
                    crop_index=crops[0].crop_index,
                    object_attrs=[
                        xai_scoring_service.ObjectAttribute(
                            key="material",
                            value="가죽",
                        )
                    ],
                    evaluations=[
                        xai_scoring_service.SkuEvaluation(
                            sku_id=crops[0].candidates[0].sku_code,
                            status="Matched",
                            total_score=93,
                            xai_result=xai_scoring_service.GeminiXaiResult(
                                summary="구조와 색상이 유사합니다."
                            ),
                        )
                    ],
                )
            ]
        )


def _build_xai_request(
    temp_dir: str,
    object_idx: int = 0,
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
        sku_id=11,
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
        object_idx=object_idx,
        bbox_coord=tagging.BoundingBox(
            xmin=0,
            ymin=0,
            xmax=1000,
            ymax=1000,
        ),
        sku_candidates=[candidate],
    )
    crop = CroppedObject(
        crop_index=object_idx,
        bbox=detected.bbox_coord,
        image=Image.new("RGB", (10, 10), color="white"),
        image_bytes=b"crop",
    )
    return settings, crop, detected


class XaiScoringServiceTest(unittest.TestCase):
    """Gemini 오류를 XAI 도메인 오류로 변환하는지 검증합니다."""

    def test_uses_v2_prompt_by_default(self) -> None:
        """운영 XAI 채점기는 별도 지정이 없으면 v2를 사용합니다."""
        settings = typing.cast(config.Settings, types.SimpleNamespace())

        service = xai_scoring_service.XaiScoringService(settings)

        self.assertEqual(service.prompt_version, "v2")

    def test_xai_prompt_versions_inject_the_same_inputs(self) -> None:
        """v1·v2가 같은 crop 구성값을 중괄호 템플릿으로 주입합니다."""
        crop_summary = "- crop 7: SKU 후보 ['CHR-2041']"

        v1_prompt = build_xai_prompt_v1(
            crop_count=1,
            crop_summary=crop_summary,
        )
        v2_prompt = build_xai_prompt_v2(
            crop_count=1,
            crop_summary=crop_summary,
        )

        for prompt in (v1_prompt, v2_prompt):
            self.assertIn("1개의", prompt)
            self.assertIn(crop_summary, prompt)
            self.assertNotIn("{crop_count}", prompt)
            self.assertNotIn("{crop_summary}", prompt)

        self.assertNotEqual(v1_prompt, v2_prompt)

    def test_selects_xai_prompt_version_without_changing_inputs(self) -> None:
        """서비스가 동일한 대상 구성에서 요청한 XAI 버전을 선택합니다."""
        settings = typing.cast(config.Settings, types.SimpleNamespace())
        targets = [
            xai_scoring_service.ScoringCrop(
                crop_index=7,
                crop_image_bytes=b"crop",
                candidates=[
                    xai_scoring_service.ScoringCandidate(
                        sku_code="CHR-2041",
                        image_bytes=b"sku",
                    )
                ],
            )
        ]

        v1_service = xai_scoring_service.XaiScoringService(
            settings,
            prompt_version="v1",
        )
        v2_service = xai_scoring_service.XaiScoringService(
            settings,
            prompt_version="v2",
        )

        self.assertEqual(v1_service.prompt_version, "v1")
        self.assertEqual(v2_service.prompt_version, "v2")
        # pylint: disable-next=protected-access
        v1_prompt = v1_service._build_prompt(targets)
        # pylint: disable-next=protected-access
        v2_prompt = v2_service._build_prompt(targets)
        self.assertIn("crop 7", v1_prompt)
        self.assertIn("crop 7", v2_prompt)
        self.assertNotEqual(v1_prompt, v2_prompt)

    def test_builds_client_through_shared_genai_factory(self) -> None:
        """XAI 채점기도 공통 Gen AI 클라이언트 정책을 사용합니다."""
        settings = typing.cast(
            config.Settings,
            types.SimpleNamespace(
                gemini_api_key="test-key",
                vertex_api_key="",
                gcp_project_id="",
            ),
        )
        client = object()
        service = xai_scoring_service.XaiScoringService(settings)

        with mock.patch(
            "app.core.genai_client.create_client",
            return_value=client,
        ) as create_client:
            result = service._get_client()  # pylint: disable=protected-access

        self.assertIs(result, client)
        create_client.assert_called_once_with(settings)

    def test_exposes_rate_limit_as_distinct_xai_error(self) -> None:
        """Gemini 429를 일반 채점 실패와 구분합니다."""
        settings = typing.cast(
            config.Settings,
            types.SimpleNamespace(
                gemini_api_key="test-key",
                vertex_api_key="",
                gcp_project_id="",
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

        with mock.patch("app.services.genai_retry.time.sleep"):
            with self.assertRaises(gemini_service.GeminiRateLimitError):
                service.score_all(crops)

    def test_gemini_response_schema_excludes_dynamic_xai_attrs(self) -> None:
        """Gemini Developer API에 동적 딕셔너리 스키마를 전달하지 않습니다."""
        schema = xai_scoring_service.RubricScoreResult.model_json_schema()

        self.assertNotIn("xai_attrs", json.dumps(schema))


class XaiFallbackContractTest(unittest.IsolatedAsyncioTestCase):
    """XAI 실패 시에도 추천 후보를 유지하는지 검증합니다."""

    async def test_rate_limit_keeps_candidate(
        self,
    ) -> None:
        """429가 발생해도 임베딩 유사도 후보를 유지합니다."""
        with tempfile.TemporaryDirectory() as temp_dir:
            settings, crop, detected = _build_xai_request(temp_dir)
            service = _RateLimitedScoringService(settings)
            xai_results = await service.score_detected_objects(
                [crop], [detected]
            )

        self.assertEqual(xai_results, {})
        self.assertEqual(len(detected.sku_candidates), 1)
        self.assertEqual(detected.sku_candidates[0].similarity_score, 91)

    async def test_success_applies_xai_score(self) -> None:
        """0이 아닌 객체 인덱스에도 XAI 점수를 반영합니다."""
        with tempfile.TemporaryDirectory() as temp_dir:
            settings, crop, detected = _build_xai_request(
                temp_dir,
                object_idx=5,
            )
            service = _SuccessfulScoringService(settings)

            xai_results = await service.score_detected_objects(
                [crop], [detected]
            )

        tagging_service.TaggingService._apply_xai_results(
            [detected],
            xai_results,
        )

        candidate = detected.sku_candidates[0]
        self.assertEqual(detected.object_idx, 5)
        self.assertEqual(detected.xai_attrs, {"material": "가죽"})
        self.assertEqual(candidate.similarity_score, 93)
        self.assertEqual(
            candidate.xai_result.summary, "구조와 색상이 유사합니다."
        )
        self.assertEqual(
            candidate.xai_result.xai_attrs,
            {"material": "가죽"},
        )


if __name__ == "__main__":
    unittest.main()
