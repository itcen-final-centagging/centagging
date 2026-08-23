"""XAI 판정 계약과 실패 시 폴백 동작을 검증합니다."""

import json
import pathlib
import tempfile
import types
import typing
import unittest
from unittest import mock

from google.genai import errors
from PIL import Image

from app.core import catalog_spec, config
from app.schemas import tagging
from app.services import gemini_service, tagging_service, xai_scoring_service
from app.services.image_processing_service import CroppedObject

_CATEGORY = "의자"


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
    """판정 단계에서 요청 한도 오류를 내는 테스트 어댑터입니다."""

    def score_all(
        self,
        _crops: list[xai_scoring_service.ScoringCrop],
    ) -> xai_scoring_service.MetadataScoreResult:
        """Gemini 요청 한도 오류를 발생시킵니다."""
        raise gemini_service.GeminiRateLimitError("rate limited")


def _verdict(
    key: str,
    verdict: str,
) -> xai_scoring_service.GeminiCandidateVerdict:
    """테스트용 판정 1건을 만듭니다."""
    return xai_scoring_service.GeminiCandidateVerdict(
        key=key,
        verdict=typing.cast(typing.Any, verdict),
        comment=f"{key} 근거",
    )


class _MetadataScoringService(xai_scoring_service.XaiScoringService):
    """고정된 v3 메타데이터 판정 결과를 반환하는 테스트 어댑터입니다.

    ``material``은 crop에서 판독하지 못한 항목으로, ``has_armrest``는
    판정이 누락된 항목으로 두어 서버 보정 경로까지 함께 확인합니다.
    """

    def score_all(
        self,
        crops: list[xai_scoring_service.ScoringCrop],
    ) -> xai_scoring_service.MetadataScoreResult:
        """후보 1건의 메타데이터 판정 결과를 반환합니다."""
        return xai_scoring_service.MetadataScoreResult(
            crops=[
                xai_scoring_service.MetadataCropScore(
                    crop_index=crops[0].crop_index,
                    crop_readings=[
                        xai_scoring_service.GeminiCropReading(
                            key="color", value="블랙"
                        ),
                        xai_scoring_service.GeminiCropReading(
                            key="style", value="모던"
                        ),
                        xai_scoring_service.GeminiCropReading(
                            key="pattern", value="무지"
                        ),
                        xai_scoring_service.GeminiCropReading(
                            key="chair_type", value="학생·사무용의자"
                        ),
                        xai_scoring_service.GeminiCropReading(
                            key="material",
                            value="",
                            note="조명 영향으로 소재를 특정하기 어렵습니다.",
                        ),
                        xai_scoring_service.GeminiCropReading(
                            key="has_wheels", value="있음"
                        ),
                        xai_scoring_service.GeminiCropReading(
                            key="has_backrest", value="있음"
                        ),
                        xai_scoring_service.GeminiCropReading(
                            key="has_armrest", value="있음"
                        ),
                    ],
                    evaluations=[
                        xai_scoring_service.MetadataSkuEvaluation(
                            sku_id=candidate.sku_code,
                            status="Rejected",
                            xai_result=xai_scoring_service.MetadataXaiResult(
                                common="두 이미지 모두 블랙 회전의자입니다.",
                                difference="패턴이 다릅니다.",
                                verdicts=[
                                    _verdict("color", "MATCH"),
                                    _verdict("style", "MATCH"),
                                    _verdict("pattern", "MISMATCH"),
                                    _verdict("chair_type", "MATCH"),
                                    _verdict("has_wheels", "MATCH"),
                                    _verdict("has_backrest", "MATCH"),
                                    # has_armrest 판정은 일부러 누락합니다.
                                ],
                            ),
                        )
                        for candidate in crops[0].candidates
                    ],
                )
            ]
        )


def _build_xai_request(
    temp_dir: str,
    object_idx: int = 0,
) -> tuple[config.Settings, CroppedObject, tagging.DetectedObject]:
    """XAI 판정 공개 인터페이스에 전달할 입력을 만듭니다."""
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
        category=_CATEGORY,
        sub_category="학생·사무용의자",
        attrs={"color": "블랙", "material": "메쉬"},
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
        category=_CATEGORY,
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


def _scoring_crop(
    category: str = _CATEGORY,
    crop_index: int = 7,
) -> xai_scoring_service.ScoringCrop:
    """프롬프트 조립에 쓰는 채점 입력 1건을 만듭니다."""
    return xai_scoring_service.ScoringCrop(
        crop_index=crop_index,
        crop_image_bytes=b"crop",
        category=category,
        candidates=[
            xai_scoring_service.ScoringCandidate(
                sku_code="CHR-2041",
                image_bytes=b"sku",
                attrs={"color": "블랙"},
            )
        ],
    )


class XaiScoringServiceTest(unittest.TestCase):
    """프롬프트 조립과 Gemini 오류 변환을 검증합니다."""

    def test_prompt_only_lists_visually_verifiable_attributes(self) -> None:
        """프롬프트에는 시각 판별이 가능한 속성만 비교 항목으로 들어갑니다."""
        settings = typing.cast(config.Settings, types.SimpleNamespace())
        service = xai_scoring_service.XaiScoringService(settings)

        # pylint: disable-next=protected-access
        prompt = service._build_prompt([_scoring_crop(category="매트리스")])

        # 두께는 이미지로 비교할 수 있지만, 내부 구조·촉감·치수·가격은 아닙니다.
        self.assertIn("thickness", prompt)
        for hidden_key in (
            "mattress_type",
            "firmness",
            "features",
            "size",
            "brand",
            "selling_price",
        ):
            self.assertNotIn(hidden_key, prompt)

    def test_prompt_does_not_request_score_or_mood(self) -> None:
        """점수표와 vlm_mood는 요구하지 않습니다."""
        settings = typing.cast(config.Settings, types.SimpleNamespace())
        service = xai_scoring_service.XaiScoringService(settings)

        # pylint: disable-next=protected-access
        prompt = service._build_prompt([_scoring_crop()])

        self.assertNotIn("total_score", prompt)
        self.assertNotIn("vlm_mood", prompt)
        self.assertNotIn("object_attrs", prompt)
        self.assertIn("MISMATCH", prompt)
        self.assertIn("UNKNOWN", prompt)

    def test_builds_client_through_shared_genai_factory(self) -> None:
        """XAI 판정기도 공통 Gen AI 클라이언트 정책을 사용합니다."""
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
        """Gemini 429를 일반 판정 실패와 구분합니다."""
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

        with mock.patch("app.services.genai_retry.time.sleep"):
            with self.assertRaises(gemini_service.GeminiRateLimitError):
                service.score_all([_scoring_crop(crop_index=0)])

    def test_gemini_response_schema_excludes_dynamic_xai_attrs(self) -> None:
        """Gemini Developer API에 동적 딕셔너리 스키마를 전달하지 않습니다."""
        schema = xai_scoring_service.MetadataScoreResult.model_json_schema()

        self.assertNotIn("xai_attrs", json.dumps(schema))


class MetadataResultTest(unittest.TestCase):
    """메타데이터 판정 결과 조립을 검증합니다."""

    @staticmethod
    def _readings(*pairs: tuple[str, str]) -> list[tagging.XaiCropReading]:
        """key와 판독값 쌍으로 crop 판독 목록을 만듭니다."""
        return [
            tagging.XaiCropReading(key=key, value=value)
            for key, value in pairs
        ]

    def test_keeps_unknown_metadata_verdict(self) -> None:
        """판독하지 못한 속성은 후보별 판단 불가로 유지합니다."""
        readings = self._readings(
            ("color", "블랙"),
            ("pattern", "무지"),
            # 판독 실패 항목입니다.
            ("material", ""),
        )
        gemini = xai_scoring_service.MetadataXaiResult(
            verdicts=[
                _verdict("color", "MATCH"),
                _verdict("pattern", "MATCH"),
            ]
        )

        result = (
            # pylint: disable-next=protected-access
            xai_scoring_service.XaiScoringService._build_metadata_xai_result(
                gemini, readings
            )
        )

        # 화면용 일치도는 추천 후보의 임베딩 유사도를 적용할 때 채웁니다.
        self.assertIsNone(result.match_rate)
        self.assertEqual(
            [item.verdict for item in result.criteria],
            ["MATCH", "MATCH", "UNKNOWN"],
        )

    def test_empty_readings_leave_match_rate_empty(self) -> None:
        """임베딩 후보와 연결 전에는 화면용 일치도를 채우지 않습니다."""
        result = (
            # pylint: disable-next=protected-access
            xai_scoring_service.XaiScoringService._build_metadata_xai_result(
                xai_scoring_service.MetadataXaiResult(), []
            )
        )

        self.assertIsNone(result.match_rate)
        self.assertEqual(result.criteria, [])

    def test_summary_joins_common_and_difference(self) -> None:
        """summary는 공통점과 차이점을 이어 붙여 채웁니다."""
        gemini = xai_scoring_service.MetadataXaiResult(
            common="공통점입니다.",
            difference="차이점입니다.",
        )

        result = (
            # pylint: disable-next=protected-access
            xai_scoring_service.XaiScoringService._build_metadata_xai_result(
                gemini, []
            )
        )

        self.assertEqual(result.common, "공통점입니다.")
        self.assertEqual(result.difference, "차이점입니다.")
        self.assertEqual(result.summary, "공통점입니다. 차이점입니다.")

    def test_readings_follow_catalog_spec_order(self) -> None:
        """비교 항목과 순서는 모델 응답이 아니라 catalog_spec이 정합니다."""
        readings = (
            # pylint: disable-next=protected-access
            xai_scoring_service.XaiScoringService._build_readings(
                _CATEGORY,
                [
                    # 순서를 뒤집고 일부 항목을 빠뜨린 응답입니다.
                    xai_scoring_service.GeminiCropReading(
                        key="has_wheels", value="있음"
                    ),
                    xai_scoring_service.GeminiCropReading(
                        key="color", value="블랙"
                    ),
                ],
            )
        )

        self.assertEqual(
            [reading.key for reading in readings],
            catalog_spec.visual_attribute_names(_CATEGORY),
        )
        missing = next(
            reading for reading in readings if reading.key == "chair_type"
        )
        self.assertEqual(missing.value, "")
        self.assertEqual(
            missing.note, xai_scoring_service.MISSING_READING_NOTE
        )


class XaiFallbackContractTest(unittest.IsolatedAsyncioTestCase):
    """XAI 실패 시에도 추천 후보를 유지하는지 검증합니다."""

    async def test_rate_limit_keeps_candidate(self) -> None:
        """429가 발생해도 임베딩 유사도 후보를 유지합니다."""
        with tempfile.TemporaryDirectory() as temp_dir:
            settings, crop, detected = _build_xai_request(temp_dir)
            service = _RateLimitedScoringService(settings)
            xai_results = await service.score_detected_objects(
                [crop], [detected], {detected.object_idx: _CATEGORY}
            )

        self.assertEqual(xai_results, {})
        self.assertEqual(len(detected.sku_candidates), 1)
        self.assertEqual(detected.sku_candidates[0].similarity_score, 91)

    async def test_skips_crop_without_comparable_category(self) -> None:
        """비교 항목을 만들 수 없는 카테고리는 v3 판정에서 제외합니다."""
        with tempfile.TemporaryDirectory() as temp_dir:
            settings, crop, detected = _build_xai_request(temp_dir)
            detected.category = "정의되지 않은 카테고리"
            service = _MetadataScoringService(settings)

            xai_results = await service.score_detected_objects(
                [crop], [detected], {}
            )

        self.assertEqual(xai_results, {})

    async def test_applies_metadata_verdicts_to_each_candidate(self) -> None:
        """crop 판독값은 객체에, 판정과 근거는 후보에 반영합니다."""
        with tempfile.TemporaryDirectory() as temp_dir:
            settings, crop, detected = _build_xai_request(
                temp_dir,
                object_idx=5,
            )
            service = _MetadataScoringService(settings)

            xai_results = await service.score_detected_objects(
                [crop], [detected], {detected.object_idx: _CATEGORY}
            )

        # pylint: disable-next=protected-access
        tagging_service.TaggingService._apply_xai_results(
            [detected],
            xai_results,
        )

        candidate = detected.sku_candidates[0]
        readings = {reading.key: reading for reading in detected.xai_readings}
        criteria = {item.key: item for item in candidate.xai_result.criteria}

        self.assertEqual(detected.object_idx, 5)

        # crop 판독값은 객체 단위로 한 번만 실립니다.
        self.assertEqual(readings["color"].value, "블랙")
        self.assertEqual(readings["material"].value, "")
        self.assertIn("조명", readings["material"].note)
        self.assertEqual(detected.xai_attrs.get("color"), "블랙")
        self.assertNotIn("material", detected.xai_attrs)

        # 후보 판정에는 crop 값을 중복해 담지 않습니다.
        # 화면 표시명은 프론트엔드가 key로 해석하므로 응답에 담지 않습니다.
        self.assertEqual(criteria["color"].verdict, "MATCH")
        self.assertEqual(criteria["pattern"].verdict, "MISMATCH")
        self.assertIsNone(criteria["color"].score)
        self.assertEqual(criteria["color"].label, "")

        # 판독 실패 항목과 판정 누락 항목은 서버가 판단 불가로 채웁니다.
        self.assertEqual(criteria["material"].verdict, "UNKNOWN")
        self.assertEqual(criteria["has_armrest"].verdict, "UNKNOWN")
        self.assertEqual(
            criteria["has_armrest"].comment,
            xai_scoring_service.MISSING_VERDICT_COMMENT,
        )

        # 비교 항목은 그대로 후보에 포함하고, 화면 일치도에는 기존 임베딩
        # 유사도를 사용합니다.
        self.assertEqual(len(candidate.xai_result.criteria), 8)
        self.assertEqual(candidate.xai_result.match_rate, 91)
        self.assertEqual(
            candidate.xai_result.common,
            "두 이미지 모두 블랙 회전의자입니다.",
        )
        self.assertEqual(candidate.xai_result.difference, "패턴이 다릅니다.")

        # 순위 근거인 임베딩 유사도는 XAI가 덮어쓰지 않습니다.
        self.assertEqual(candidate.similarity_score, 91)

    async def test_keeps_embedding_order(self) -> None:
        """XAI 결과가 후보 순서를 바꾸지 않습니다."""
        with tempfile.TemporaryDirectory() as temp_dir:
            settings, crop, detected = _build_xai_request(temp_dir)
            detected.sku_candidates.append(
                detected.sku_candidates[0].model_copy(
                    update={
                        "sku_id": 12,
                        "sku_code": "CHR-9999",
                        "similarity_score": 40,
                    }
                )
            )
            service = _MetadataScoringService(settings)

            xai_results = await service.score_detected_objects(
                [crop], [detected], {detected.object_idx: _CATEGORY}
            )

        # pylint: disable-next=protected-access
        tagging_service.TaggingService._apply_xai_results(
            [detected],
            xai_results,
        )

        self.assertEqual(
            [item.sku_code for item in detected.sku_candidates],
            ["CHR-2041", "CHR-9999"],
        )


if __name__ == "__main__":
    unittest.main()
