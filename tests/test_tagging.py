"""태깅(유사 SKU 추천) 기능 테스트입니다."""

import pathlib
import tempfile
import unittest
import unittest.mock

import fastapi
import PIL.Image
import PIL.ImageDraw
import starlette.testclient

from app import dependencies
from app.api import tagging
from app.core import config, exception_handlers, request_context
from app.schemas import tagging as tagging_schemas
from app.services import image_processing_service, similar_sku_service


class GetCropImageTest(unittest.TestCase):
    """bbox_coord(0~1000 정규화 좌표)로 올바른 영역을 잘라내는지 검증합니다."""

    def setUp(self) -> None:
        """사분면마다 다른 색으로 채운 1000x1000 테스트 이미지를 준비합니다."""
        self.image = PIL.Image.new("RGB", (1000, 1000))
        draw = PIL.ImageDraw.Draw(self.image)
        draw.rectangle((0, 0, 499, 499), fill=(255, 0, 0))  # 좌상단: 빨강
        draw.rectangle((500, 0, 999, 499), fill=(0, 255, 0))  # 우상단: 초록
        draw.rectangle((0, 500, 499, 999), fill=(0, 0, 255))  # 좌하단: 파랑
        draw.rectangle((500, 500, 999, 999), fill=(255, 255, 0))  # 우하단: 노랑

    def _assert_solid_color(
        self, cropped: PIL.Image.Image, expected_rgb: tuple[int, int, int]
    ) -> None:
        """잘라낸 이미지가 예상 좌표 영역과 정확히 일치하는 단색인지 확인합니다."""
        colors = cropped.convert("RGB").getcolors(maxcolors=1)
        self.assertIsNotNone(
            colors, "영역 안에 여러 색이 섞여 있습니다 (좌표 계산 오류 가능성)"
        )
        _, rgb = colors[0]
        self.assertEqual(rgb, expected_rgb)

    def test_crops_top_left_quadrant(self) -> None:
        """xmin=0, ymin=0인 좌상단 영역을 정확히 잘라냅니다."""
        bbox = {"xmin": 0.0, "ymin": 0.0, "xmax": 500.0, "ymax": 500.0}

        cropped = image_processing_service.get_crop_image(self.image, bbox)

        self.assertEqual(cropped.size, (500, 500))
        self._assert_solid_color(cropped, (255, 0, 0))

    def test_crops_top_right_quadrant(self) -> None:
        """xmin이 큰 우상단 영역을 좌상단과 혼동하지 않고 잘라냅니다."""
        bbox = {"xmin": 500.0, "ymin": 0.0, "xmax": 1000.0, "ymax": 500.0}

        cropped = image_processing_service.get_crop_image(self.image, bbox)

        self.assertEqual(cropped.size, (500, 500))
        self._assert_solid_color(cropped, (0, 255, 0))

    def test_crops_bottom_left_quadrant(self) -> None:
        """ymin이 큰 좌하단 영역을 상단과 혼동하지 않고 잘라냅니다."""
        bbox = {"xmin": 0.0, "ymin": 500.0, "xmax": 500.0, "ymax": 1000.0}

        cropped = image_processing_service.get_crop_image(self.image, bbox)

        self.assertEqual(cropped.size, (500, 500))
        self._assert_solid_color(cropped, (0, 0, 255))

    def test_crops_bottom_right_quadrant(self) -> None:
        """x, y 모두 큰 우하단 영역을 정확히 잘라냅니다."""
        bbox = {"xmin": 500.0, "ymin": 500.0, "xmax": 1000.0, "ymax": 1000.0}

        cropped = image_processing_service.get_crop_image(self.image, bbox)

        self.assertEqual(cropped.size, (500, 500))
        self._assert_solid_color(cropped, (255, 255, 0))


class _FakeMappingsResult:
    """SQLAlchemy 실행 결과의 mappings() 인터페이스를 흉내냅니다."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def mappings(self) -> "_FakeMappingsResult":
        """자기 자신을 반환해 result.mappings() 체이닝을 흉내냅니다."""
        return self

    def first(self) -> dict[str, object] | None:
        """첫 번째 행 또는 None을 반환합니다."""
        return self._rows[0] if self._rows else None

    def all(self) -> list[dict[str, object]]:
        """모든 행을 반환합니다."""
        return list(self._rows)


class _FakeSimilarSkuSession:
    """scene_image 조회 쿼리와 유사 SKU 조회 쿼리를 구분해 응답하는 가짜 세션입니다."""

    def __init__(
        self,
        scene_row: dict[str, object] | None,
        similar_rows: list[dict[str, object]] | None = None,
        scene_query_error: Exception | None = None,
        similar_query_error: Exception | None = None,
    ) -> None:
        self._scene_row = scene_row
        self._similar_rows = similar_rows if similar_rows is not None else []
        self._scene_query_error = scene_query_error
        self._similar_query_error = similar_query_error
        self.similar_query_embeddings: list[list[float]] = []
        self.status_updates: list[dict[str, object]] = []
        self.commit_count = 0
        self.rollback_count = 0

    async def execute(
        self, statement: object, parameters: dict[str, object]
    ) -> _FakeMappingsResult:
        """쿼리 텍스트로 scene_image 조회와 유사 SKU 조회를 구분합니다."""
        if "FROM scene_image" in str(statement):
            if self._scene_query_error is not None:
                raise self._scene_query_error
            rows = [self._scene_row] if self._scene_row is not None else []
            return _FakeMappingsResult(rows)
        if "UPDATE scene_image" in str(statement):
            self.status_updates.append(parameters)
            return _FakeMappingsResult([])

        self.similar_query_embeddings.append(parameters["embedding"])
        if self._similar_query_error is not None:
            raise self._similar_query_error
        return _FakeMappingsResult(self._similar_rows)

    async def commit(self) -> None:
        """상태 변경 커밋 횟수를 기록합니다."""
        self.commit_count += 1

    async def rollback(self) -> None:
        """오류 발생 시 롤백 횟수를 기록합니다."""
        self.rollback_count += 1


class _FakeGeminiService:
    """실제 Gemini 호출 없이 고정 임베딩을 반환하는 가짜 서비스입니다."""

    def __init__(self) -> None:
        self.received_images: list[PIL.Image.Image] = []

    def embed_image(self, image: PIL.Image.Image) -> list[float]:
        """전달받은 크롭 이미지를 기록하고 고정 임베딩을 반환합니다."""
        self.received_images.append(image.copy())
        return [0.1] * similar_sku_service.EMBEDDING_DIMENSIONS


class _FailingGeminiService(_FakeGeminiService):
    """임베딩 단계 오류를 발생시키는 가짜 서비스입니다."""

    def embed_image(self, image: PIL.Image.Image) -> list[float]:
        """임베딩 실패 상황을 재현합니다."""
        raise RuntimeError("embedding failed")


def _test_settings(image_storage_root: str) -> config.Settings:
    """테스트용 애플리케이션 설정을 생성합니다."""
    return config.Settings(
        gemini_api_key="test-key",
        vertex_api_key="test-vertex-key",
        gcp_project_id="test-project",
        vertex_ai_location="global",
        gemini_vlm_model="",
        gemini_embedding_model="",
        mvp_login_id="",
        mvp_login_password="",
        image_storage_root=image_storage_root,
        sku_image_root="",
        database=config.DatabaseSettings(
            name="", username="", password="", host="", port=5432
        ),
    )


class GetCropImageCoordsTest(unittest.IsolatedAsyncioTestCase):
    """scene_image 좌표 조회 및 인덱스 필터링을 검증합니다."""

    async def test_raises_not_found_when_scene_missing(self) -> None:
        """존재하지 않는 scene_id는 SceneImageNotFoundError를 발생시킵니다."""
        service = similar_sku_service.SimilarSkuService(
            session=_FakeSimilarSkuSession(scene_row=None),
            gemini_service=_FakeGeminiService(),
            settings=_test_settings("unused"),
            scoring_service=unittest.mock.Mock(),
        )

        with self.assertRaises(similar_sku_service.SceneImageNotFoundError):
            await service.get_crop_image_coords(
                scene_id=999, object_indexes=[0]
            )

    async def test_preserves_original_index_for_each_requested_object(
        self,
    ) -> None:
        """필터링 후에도 요청한 원래 인덱스가 좌표와 함께 유지됩니다."""
        coords = [
            {"xmin": 0.0, "ymin": 0.0, "xmax": 100.0, "ymax": 100.0},
            {
                "xmin": 100.0,
                "ymin": 100.0,
                "xmax": 200.0,
                "ymax": 200.0,
            },
            {
                "xmin": 200.0,
                "ymin": 200.0,
                "xmax": 300.0,
                "ymax": 300.0,
            },
        ]
        session = _FakeSimilarSkuSession(
            scene_row={
                "image_url": "/uploads/scene.png",
                "object_metadata": coords,
            }
        )
        service = similar_sku_service.SimilarSkuService(
            session=session,
            gemini_service=_FakeGeminiService(),
            settings=_test_settings("unused"),
            scoring_service=unittest.mock.Mock(),
        )

        # 순서를 바꾸고 존재하지 않는 인덱스를 섞어서 요청합니다.
        scene = await service.get_crop_image_coords(
            scene_id=1, object_indexes=[2, 0, 99, -1]
        )

        self.assertEqual(
            scene["indexed_coords"],
            [(2, coords[2]), (0, coords[0])],
        )


class OrchestrateSimilarSkusTest(unittest.IsolatedAsyncioTestCase):
    """전체 추천 흐름에서 인덱스와 SKU 후보가 올바르게 조립되는지 검증합니다."""

    def setUp(self) -> None:
        """임시 저장소에 테스트용 장면 이미지를 준비합니다."""
        self.storage_dir = tempfile.TemporaryDirectory()
        image_dir = pathlib.Path(self.storage_dir.name) / "scene-images"
        image_dir.mkdir(parents=True)
        PIL.Image.new("RGB", (1000, 1000)).save(image_dir / "scene.png")
        self.settings = _test_settings(self.storage_dir.name)

    def tearDown(self) -> None:
        """임시 저장소를 정리합니다."""
        self.storage_dir.cleanup()

    async def test_response_object_index_matches_request_not_loop_position(
        self,
    ) -> None:
        """object_indexes=[2, 0]으로 요청하면 응답도 2, 0 순서/값을 유지합니다."""
        bbox_coord = [
            {"xmin": 0.0, "ymin": 0.0, "xmax": 100.0, "ymax": 100.0},
            {
                "xmin": 100.0,
                "ymin": 100.0,
                "xmax": 200.0,
                "ymax": 200.0,
            },
            {
                "xmin": 200.0,
                "ymin": 200.0,
                "xmax": 300.0,
                "ymax": 300.0,
            },
        ]
        scene_row = {
            "image_url": "/uploads/scene-images/scene.png",
            "object_metadata": bbox_coord,
        }
        similar_row = {
            "sku_id": 1,
            "sku_image_id": 10,
            "sku_code": "SKU-001",
            "product_name": "1인 소파",
            "image_url": "/uploads/sku/1.png",
            "image_type": "MAIN",
            "category": "가구",
            "sub_category": "소파",
            "attributes": {"color": "beige"},
            "similarity": 0.87,
        }
        session = _FakeSimilarSkuSession(
            scene_row=scene_row, similar_rows=[similar_row]
        )
        gemini_service = _FakeGeminiService()
        service = similar_sku_service.SimilarSkuService(
            session=session,
            gemini_service=gemini_service,
            settings=self.settings,
            scoring_service=unittest.mock.Mock(),
        )

        result = await service.orchestrate_similar_skus(
            scene_id=1, object_indexes=[2, 0]
        )

        self.assertEqual([obj.object_index for obj in result.objects], [2, 0])
        self.assertEqual(
            result.objects[0].bbox_coord,
            {"xmin": 200.0, "ymin": 200.0, "xmax": 300.0, "ymax": 300.0},
        )
        self.assertEqual(
            result.objects[1].bbox_coord,
            {"xmin": 0.0, "ymin": 0.0, "xmax": 100.0, "ymax": 100.0},
        )
        self.assertEqual(len(gemini_service.received_images), 2)
        self.assertEqual(
            result.objects[0].sku_candidates[0].sku_code, "SKU-001"
        )
        self.assertEqual(
            result.objects[0].sku_candidates[0].similarity_score, 87
        )
        self.assertEqual(result.processing_status, "completed")
        self.assertEqual(
            session.status_updates,
            [
                {
                    "scene_image_id": 1,
                    "analysis_status": "embedded",
                    "analysis_error": None,
                },
                {
                    "scene_image_id": 1,
                    "analysis_status": "completed",
                    "analysis_error": None,
                },
            ],
        )
        self.assertEqual(session.commit_count, 2)

    async def test_returns_empty_objects_when_no_indexes_requested(
        self,
    ) -> None:
        """object_indexes를 비워서 요청하면 크롭/임베딩 없이 빈 목록을 반환합니다."""
        scene_row = {
            "image_url": "/uploads/scene-images/scene.png",
            "object_metadata": [
                {
                    "xmin": 0.0,
                    "ymin": 0.0,
                    "xmax": 100.0,
                    "ymax": 100.0,
                }
            ],
        }
        session = _FakeSimilarSkuSession(scene_row=scene_row)
        gemini_service = _FakeGeminiService()
        service = similar_sku_service.SimilarSkuService(
            session=session,
            gemini_service=gemini_service,
            settings=self.settings,
            scoring_service=unittest.mock.Mock(),
        )

        result = await service.orchestrate_similar_skus(
            scene_id=1, object_indexes=[]
        )

        self.assertEqual(result.objects, [])
        self.assertEqual(gemini_service.received_images, [])
        self.assertEqual(result.processing_status, "detected")
        self.assertEqual(session.status_updates, [])

    async def test_marks_failed_when_embedding_fails(self) -> None:
        """임베딩 오류가 발생하면 failed 상태와 원인을 저장합니다."""
        scene_row = {
            "image_url": "/uploads/scene-images/scene.png",
            "object_metadata": [
                {"xmin": 0.0, "ymin": 0.0, "xmax": 100.0, "ymax": 100.0}
            ],
        }
        session = _FakeSimilarSkuSession(scene_row=scene_row)
        service = similar_sku_service.SimilarSkuService(
            session=session,
            gemini_service=_FailingGeminiService(),
            settings=self.settings,
            scoring_service=unittest.mock.Mock(),
        )

        with self.assertRaisesRegex(RuntimeError, "embedding failed"):
            await service.orchestrate_similar_skus(
                scene_id=1, object_indexes=[0]
            )

        self.assertEqual(session.rollback_count, 1)
        self.assertEqual(
            session.status_updates,
            [
                {
                    "scene_image_id": 1,
                    "analysis_status": "failed",
                    "analysis_error": "embedding failed",
                }
            ],
        )

    async def test_marks_failed_when_scene_query_fails(self) -> None:
        """장면 조회 오류가 발생해도 failed 상태와 원인을 저장합니다."""
        session = _FakeSimilarSkuSession(
            scene_row=None,
            scene_query_error=RuntimeError("scene query failed"),
        )
        service = similar_sku_service.SimilarSkuService(
            session=session,
            gemini_service=_FakeGeminiService(),
            settings=self.settings,
            scoring_service=unittest.mock.Mock(),
        )

        with self.assertRaisesRegex(RuntimeError, "scene query failed"):
            await service.orchestrate_similar_skus(
                scene_id=1, object_indexes=[0]
            )

        self.assertEqual(
            session.status_updates,
            [
                {
                    "scene_image_id": 1,
                    "analysis_status": "failed",
                    "analysis_error": "scene query failed",
                }
            ],
        )

    async def test_marks_embedded_then_failed_when_candidate_query_fails(
        self,
    ) -> None:
        """후보 생성 오류는 embedded 이후 failed 상태로 전환합니다."""
        scene_row = {
            "image_url": "/uploads/scene-images/scene.png",
            "object_metadata": [
                {"xmin": 0.0, "ymin": 0.0, "xmax": 100.0, "ymax": 100.0}
            ],
        }
        session = _FakeSimilarSkuSession(
            scene_row=scene_row,
            similar_query_error=RuntimeError("candidate query failed"),
        )
        service = similar_sku_service.SimilarSkuService(
            session=session,
            gemini_service=_FakeGeminiService(),
            settings=self.settings,
            scoring_service=unittest.mock.Mock(),
        )

        with self.assertRaisesRegex(RuntimeError, "candidate query failed"):
            await service.orchestrate_similar_skus(
                scene_id=1, object_indexes=[0]
            )

        self.assertEqual(
            [update["analysis_status"] for update in session.status_updates],
            ["embedded", "failed"],
        )
        self.assertEqual(
            session.status_updates[-1]["analysis_error"],
            "candidate query failed",
        )


class TaggingApiTest(unittest.TestCase):
    """/tagging/scenes/{scene_id} API 계약을 검증합니다."""

    def setUp(self) -> None:
        """tagging 라우터만 포함한 최소 앱을 구성합니다."""
        self.app = fastapi.FastAPI()
        self.app.add_middleware(request_context.RequestIdMiddleware)
        exception_handlers.register_exception_handlers(self.app)
        self.app.include_router(tagging.router)
        self.client = starlette.testclient.TestClient(self.app)

    def _override_service(self, fake_service: object) -> None:
        """get_similar_sku_service 의존성을 가짜 서비스로 대체합니다."""

        async def _provide() -> object:
            return fake_service

        self.app.dependency_overrides[dependencies.get_similar_sku_service] = (
            _provide
        )

    def _override_match_service(self, fake_service: object) -> None:
        """get_sku_match_service 의존성을 가짜 서비스로 대체합니다."""

        async def _provide() -> object:
            return fake_service

        self.app.dependency_overrides[dependencies.get_sku_match_service] = (
            _provide
        )

    def test_returns_404_when_scene_not_found(self) -> None:
        """서비스가 SceneImageNotFoundError를 던지면 404로 변환합니다."""

        class _RaisingService:
            async def orchestrate_similar_skus(
                self, scene_id: int, object_indexes: list[int]
            ) -> None:
                raise similar_sku_service.SceneImageNotFoundError(scene_id)

        self._override_service(_RaisingService())

        response = self.client.get("/tagging/scenes/999")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "RESOURCE_NOT_FOUND")

    def test_passes_query_object_indexes_to_service_in_order(self) -> None:
        """반복된 object_indexes 쿼리 파라미터가 순서대로 서비스에 전달됩니다."""
        captured: dict[str, object] = {}

        class _RecordingService:
            async def orchestrate_similar_skus(
                self, scene_id: int, object_indexes: list[int]
            ) -> tagging_schemas.DetectionResult:
                captured["scene_id"] = scene_id
                captured["object_indexes"] = object_indexes
                return tagging_schemas.DetectionResult(
                    processing_status="completed",
                    scene_image=tagging_schemas.SceneImageInfo(
                        scene_image_id=scene_id,
                        image_url="/uploads/scene.png",
                        origin_name="scene.png",
                        mime_type="image/png",
                        file_size=1,
                        width_px=1,
                        height_px=1,
                    ),
                    objects=[],
                )

        self._override_service(_RecordingService())

        response = self.client.get(
            "/tagging/scenes/7?object_indexes=2&object_indexes=0"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["scene_id"], 7)
        self.assertEqual(captured["object_indexes"], [2, 0])
        self.assertEqual(response.json()["status"], "success")
        self.assertEqual(
            response.json()["data"]["processing_status"], "completed"
        )
        self.assertEqual(
            response.json()["meta"]["request_id"],
            response.headers["X-Request-ID"],
        )

    def test_confirms_matching_with_common_success_response(self) -> None:
        """SKU 확정 결과도 공통 성공 응답과 요청 ID를 반환합니다."""

        class _MatchingService:
            async def confirm_matching(
                self,
                scene_id: int,
                matching: list[tagging_schemas.SkuMatching],
            ) -> list[int]:
                self.assertEqual(scene_id, 7)
                self.assertEqual(matching[0].sku_code, "CHR-2041")
                return [91]

            def assertEqual(self, actual: object, expected: object) -> None:
                """테스트 서비스 내부 값 비교를 수행합니다."""
                if actual != expected:
                    raise AssertionError(f"{actual!r} != {expected!r}")

        self._override_match_service(_MatchingService())
        response = self.client.put(
            "/tagging/scenes/7",
            json={
                "matching": [
                    {
                        "object_index": 0,
                        "sku_code": "CHR-2041",
                        "match_rank": 1,
                        "similarity_score": 90,
                        "xai_result": {
                            "summary": "유사합니다.",
                            "criteria": [],
                        },
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        self.assertEqual(response.json()["data"]["result_ids"], [91])
        self.assertEqual(
            response.json()["meta"]["request_id"],
            response.headers["X-Request-ID"],
        )

    def test_invalid_matching_request_uses_common_validation_error(
        self,
    ) -> None:
        """태깅 확정 요청의 필수값 누락은 공통 422 오류로 반환합니다."""
        response = self.client.put("/tagging/scenes/7", json={})

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "VALIDATION_ERROR")
        self.assertEqual(
            response.json()["error"]["details"][0]["field"], "matching"
        )


if __name__ == "__main__":
    unittest.main()
