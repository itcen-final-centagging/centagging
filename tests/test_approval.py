"""승인 요청 API 계약 및 서비스 로직 테스트입니다."""

import datetime
import unittest

import fastapi
import starlette.testclient

from app import dependencies
from app.api import approval
from app.core import config
from app.services import approval_service


class _FakeResult:
    """SQLAlchemy 실행 결과의 mappings()/scalar_one() 인터페이스를 흉내냅니다."""

    def __init__(
        self,
        rows: list[dict[str, object]] | None = None,
        scalar: object = None,
    ) -> None:
        self._rows = rows or []
        self._scalar = scalar

    def mappings(self) -> "_FakeResult":
        """자기 자신을 반환해 result.mappings() 체이닝을 흉내냅니다."""
        return self

    def first(self) -> dict[str, object] | None:
        """첫 번째 행 또는 None을 반환합니다."""
        return self._rows[0] if self._rows else None

    def one(self) -> dict[str, object]:
        """정확히 한 행을 기대하는 조회 결과를 반환합니다."""
        return self._rows[0]

    def one_or_none(self) -> dict[str, object] | None:
        """0건 또는 1건을 기대하는 조회 결과를 반환합니다."""
        return self._rows[0] if self._rows else None

    def all(self) -> list[dict[str, object]]:
        """모든 행을 반환합니다."""
        return list(self._rows)

    def scalar_one(self) -> object:
        """단일 스칼라 값을 반환합니다."""
        return self._scalar

    def scalar_one_or_none(self) -> object:
        """단일 스칼라 값 또는 None을 반환합니다."""
        return self._scalar


def _test_settings() -> config.Settings:
    """테스트용 애플리케이션 설정을 생성합니다."""
    return config.Settings(
        gemini_api_key="test-key",
        gemini_vlm_model="",
        gemini_embedding_model="",
        mvp_login_id="admin",
        mvp_login_password="",
        image_storage_root="unused",
        database=config.DatabaseSettings(
            name="", username="", password="", host="", port=5432
        ),
    )


_REVIEWER_ROW = {"user_id": 1, "user_name": "박승인"}


class _FakeApprovalSession:
    """쿼리 텍스트로 분기해 고정 응답을 돌려주는 가짜 세션입니다."""

    def __init__(self, responses: dict[str, _FakeResult]) -> None:
        self._responses = responses
        self.executed: list[tuple[str, dict[str, object]]] = []
        self.commit_count = 0
        self.rollback_count = 0

    async def execute(
        self, statement: object, parameters: dict[str, object] | None = None
    ) -> _FakeResult:
        """등록된 SQL 조각과 매칭되는 첫 번째 응답을 반환합니다."""
        text = str(statement)
        self.executed.append((text, parameters or {}))
        for key, result in self._responses.items():
            if key in text:
                return result
        raise AssertionError(f"예상치 못한 쿼리입니다: {text}")

    async def commit(self) -> None:
        """커밋 횟수를 기록합니다."""
        self.commit_count += 1

    async def rollback(self) -> None:
        """롤백 횟수를 기록합니다."""
        self.rollback_count += 1


class ListApprovalsTest(unittest.IsolatedAsyncioTestCase):
    """list_approvals가 조건을 그대로 전달하고 응답을 조립하는지 검증합니다."""

    async def test_builds_items_from_rows(self) -> None:
        """조회된 행(객체 단위)을 camelCase 응답 항목으로 변환합니다."""
        session = _FakeApprovalSession(
            {
                "FROM approval a": _FakeResult(
                    rows=[
                        {
                            "request_id": 1024,
                            "status": "PENDING",
                            "requested_at": datetime.datetime(2026, 8, 5),
                            "reviewed_at": None,
                            "scene_image_id": 512,
                            "object_id": 3301,
                            "origin_name": "scene_office_01.jpg",
                            "requested_by_name": "김태깅",
                            "reviewed_by_name": None,
                            "category": "의자",
                            "sub_category": "오피스체어",
                            "crop_url": "/uploads/crop_3301.jpg",
                            "sku_code": "CH-1180",
                            "product_name": "메쉬 오피스체어 화이트",
                            "similarity_score": 0.9412,
                            "similarity_grade": "상",
                        }
                    ]
                ),
            }
        )
        service = approval_service.ApprovalService(
            session=session, settings=_test_settings()
        )

        result = await service.list_approvals("PENDING", None, None)

        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].request_id, 1024)
        self.assertEqual(result.items[0].object_id, 3301)
        self.assertEqual(result.items[0].sku_code, "CH-1180")
        _, params = session.executed[0]
        self.assertEqual(params["status"], "PENDING")
        self.assertIsNone(params["requested_from"])
        self.assertIsNone(params["requested_to"])


class GetDetailTest(unittest.IsolatedAsyncioTestCase):
    """get_detail의 404 처리와 상세 조립을 검증합니다."""

    async def test_raises_not_found_when_missing(self) -> None:
        """존재하지 않는 request_id는 ApprovalNotFoundError를 던집니다."""
        session = _FakeApprovalSession(
            {"FROM approval a": _FakeResult(rows=[])}
        )
        service = approval_service.ApprovalService(
            session=session, settings=_test_settings()
        )

        with self.assertRaises(approval_service.ApprovalNotFoundError):
            await service.get_detail(999)

    async def test_builds_detail_and_actions(self) -> None:
        """단일 객체-SKU 매칭 상세를 조립하고 PENDING이면 버튼을 켭니다."""
        detail_row = {
            "request_id": 1024,
            "status": "PENDING",
            "requested_at": datetime.datetime(2026, 8, 5),
            "reviewed_at": None,
            "reject_reason": None,
            "scene_image_id": 512,
            "object_id": 3301,
            "requested_by_name": "김태깅",
            "reviewed_by_name": None,
            "scene_image_url": "/uploads/scene.jpg",
            "origin_name": "scene_office_01.jpg",
            "mime_type": "image/jpeg",
            "file_size": 2418123,
            "width_px": 1920,
            "height_px": 1280,
            "scene_created_at": datetime.datetime(2026, 8, 5),
            "category": "의자",
            "sub_category": "오피스체어",
            "confidence": 0.962,
            "bbox_xmin": 412,
            "bbox_ymin": 305,
            "bbox_xmax": 668,
            "bbox_ymax": 742,
            "attributes": {"주요 소재": "메쉬"},
            "mood_summary": "밝은 홈오피스",
            "mood_tags": ["미니멀"],
            "crop_url": "/uploads/crop_3301.jpg",
            "has_embedding": True,
            "result_id": 8801,
            "match_source": "RECOMMEND",
            "match_rank": 1,
            "similarity_score": 0.9412,
            "similarity_grade": "상",
            "xai_result": None,
            "sku_id": 310,
            "sku_code": "CH-1180",
            "product_name": "메쉬 오피스체어 화이트",
            "brand": "센터퍼니처",
            "price": 289000,
            "sku_attributes": {"주요 소재": "메쉬"},
            "matched_sku_image_url": "/uploads/ch1180_main.jpg",
        }
        session = _FakeApprovalSession(
            {"FROM approval a": _FakeResult(rows=[detail_row])}
        )
        service = approval_service.ApprovalService(
            session=session, settings=_test_settings()
        )

        detail = await service.get_detail(1024)

        self.assertEqual(detail.result_id, 8801)
        self.assertEqual(detail.object.object_id, 3301)
        self.assertEqual(detail.sku.sku_code, "CH-1180")
        self.assertTrue(detail.actions.can_confirm)
        self.assertTrue(detail.actions.can_reject)

    async def test_builds_detail_with_no_matching_sku(self) -> None:
        """tagging_result가 없는 NO_SKU 요청은 sku·매칭 필드가 null입니다."""
        detail_row = {
            "request_id": 2048,
            "status": "NO_SKU",
            "requested_at": datetime.datetime(2026, 8, 6),
            "reviewed_at": None,
            "reject_reason": None,
            "scene_image_id": 600,
            "object_id": 4001,
            "requested_by_name": "박관리자",
            "reviewed_by_name": None,
            "scene_image_url": "/uploads/scene_admin.jpg",
            "origin_name": "product_photo.jpg",
            "mime_type": "image/jpeg",
            "file_size": 1000000,
            "width_px": 1200,
            "height_px": 1200,
            "scene_created_at": datetime.datetime(2026, 8, 6),
            "category": "화분",
            "sub_category": None,
            "confidence": 0.9,
            "bbox_xmin": 0,
            "bbox_ymin": 0,
            "bbox_xmax": 1000,
            "bbox_ymax": 1000,
            "attributes": {},
            "mood_summary": None,
            "mood_tags": None,
            "crop_url": "/uploads/crop_4001.jpg",
            "has_embedding": False,
            "result_id": None,
            "match_source": None,
            "match_rank": None,
            "similarity_score": None,
            "similarity_grade": None,
            "xai_result": None,
            "sku_id": None,
            "sku_code": None,
            "product_name": None,
            "brand": None,
            "price": None,
            "sku_attributes": None,
            "matched_sku_image_url": None,
        }
        session = _FakeApprovalSession(
            {"FROM approval a": _FakeResult(rows=[detail_row])}
        )
        service = approval_service.ApprovalService(
            session=session, settings=_test_settings()
        )

        detail = await service.get_detail(2048)

        self.assertEqual(detail.status, "NO_SKU")
        self.assertIsNone(detail.result_id)
        self.assertIsNone(detail.sku)
        self.assertIsNone(detail.match_source)
        self.assertEqual(detail.object.object_id, 4001)
        self.assertFalse(detail.actions.can_confirm)
        self.assertFalse(detail.actions.can_reject)


class ConfirmTest(unittest.IsolatedAsyncioTestCase):
    """confirm의 상태 전이와 예외 매핑을 검증합니다."""

    def _session(
        self,
        *,
        locked_status: str = "PENDING",
        crop_url: str | None = "/uploads/crop_3301.jpg",
        insert_returns: bool = True,
    ) -> _FakeApprovalSession:
        created_rows = (
            [{"sku_image_id": 1501, "sku_id": 310, "indexed": True}]
            if insert_returns
            else []
        )
        return _FakeApprovalSession(
            {
                "FOR UPDATE": _FakeResult(
                    rows=[
                        {
                            "request_id": 1024,
                            "scene_image_id": 512,
                            "object_id": 3301,
                            "status": locked_status,
                        }
                    ]
                ),
                "SELECT do_.crop_url": _FakeResult(scalar=crop_url),
                "INSERT INTO sku_image": _FakeResult(rows=created_rows),
                "FROM sku_catalog WHERE sku_id": _FakeResult(scalar="CH-1180"),
                "FROM app_user": _FakeResult(rows=[_REVIEWER_ROW]),
                "UPDATE approval": _FakeResult(),
            }
        )

    async def test_confirms_and_registers_sku_image(self) -> None:
        """정상 승인 시 등록된 SKU 이미지와 ACTIVE 상태를 반환합니다."""
        session = self._session()
        service = approval_service.ApprovalService(
            session=session, settings=_test_settings()
        )

        result = await service.confirm(1024)

        self.assertEqual(result.status, "ACTIVE")
        assert result.created_sku_image is not None
        self.assertEqual(result.created_sku_image.sku_code, "CH-1180")
        self.assertFalse(result.skipped)
        self.assertEqual(session.commit_count, 1)

    async def test_confirms_and_skips_when_already_registered(self) -> None:
        """이미 등록된 크롭이면 재등록하지 않고 skipped=True를 반환합니다."""
        session = self._session(insert_returns=False)
        service = approval_service.ApprovalService(
            session=session, settings=_test_settings()
        )

        result = await service.confirm(1024)

        self.assertIsNone(result.created_sku_image)
        self.assertTrue(result.skipped)
        self.assertEqual(session.commit_count, 1)

    async def test_raises_already_reviewed_when_not_pending(self) -> None:
        """이미 처리된 요청은 AlreadyReviewedError를 던집니다."""
        session = self._session(locked_status="ACTIVE")
        service = approval_service.ApprovalService(
            session=session, settings=_test_settings()
        )

        with self.assertRaises(approval_service.AlreadyReviewedError):
            await service.confirm(1024)

    async def test_raises_no_registrable_crop_when_missing(self) -> None:
        """대상 객체에 크롭이 없으면 NoRegistrableCropError를 던집니다."""
        session = self._session(crop_url=None)
        service = approval_service.ApprovalService(
            session=session, settings=_test_settings()
        )

        with self.assertRaises(approval_service.NoRegistrableCropError):
            await service.confirm(1024)


class RejectTest(unittest.IsolatedAsyncioTestCase):
    """reject의 검증 순서와 예외 매핑을 검증합니다."""

    async def test_raises_reject_reason_required_when_blank(self) -> None:
        """빈 사유는 쿼리 없이 RejectReasonRequiredError를 던집니다."""
        session = _FakeApprovalSession({})
        service = approval_service.ApprovalService(
            session=session, settings=_test_settings()
        )

        with self.assertRaises(approval_service.RejectReasonRequiredError):
            await service.reject(1024, "   ")
        self.assertEqual(session.executed, [])

    async def test_raises_already_reviewed_when_update_matches_zero_rows(
        self,
    ) -> None:
        """이미 처리된 요청은 UPDATE 0건이면 AlreadyReviewedError입니다."""
        session = _FakeApprovalSession(
            {
                "SELECT 1 FROM approval": _FakeResult(scalar=1),
                "FROM app_user": _FakeResult(rows=[_REVIEWER_ROW]),
                "UPDATE approval": _FakeResult(scalar=None),
            }
        )
        service = approval_service.ApprovalService(
            session=session, settings=_test_settings()
        )

        with self.assertRaises(approval_service.AlreadyReviewedError):
            await service.reject(1024, "사유")
        self.assertEqual(session.rollback_count, 1)

    async def test_rejects_successfully(self) -> None:
        """정상 반려 시 REJECTED 상태와 사유를 반환합니다."""
        session = _FakeApprovalSession(
            {
                "SELECT 1 FROM approval": _FakeResult(scalar=1),
                "FROM app_user": _FakeResult(rows=[_REVIEWER_ROW]),
                "UPDATE approval": _FakeResult(scalar=1024),
            }
        )
        service = approval_service.ApprovalService(
            session=session, settings=_test_settings()
        )

        result = await service.reject(1024, "소파 매칭 SKU가 다릅니다.")

        self.assertEqual(result.status, "REJECTED")
        self.assertEqual(result.reject_reason, "소파 매칭 SKU가 다릅니다.")
        self.assertEqual(session.commit_count, 1)


class ApprovalApiTest(unittest.TestCase):
    """/approvals API 계약(상태 코드·에러 매핑)을 검증합니다."""

    def setUp(self) -> None:
        """approval 라우터만 포함한 최소 앱을 구성합니다."""
        self.app = fastapi.FastAPI()
        self.app.include_router(approval.router)
        self.client = starlette.testclient.TestClient(self.app)

    def _override_service(self, fake_service: object) -> None:
        """get_approval_service 의존성을 가짜 서비스로 대체합니다."""

        async def _provide() -> object:
            return fake_service

        self.app.dependency_overrides[dependencies.get_approval_service] = (
            _provide
        )

    def test_get_detail_returns_404_when_not_found(self) -> None:
        """서비스가 ApprovalNotFoundError를 던지면 404로 변환합니다."""

        class _RaisingService:
            async def get_detail(self, request_id: int) -> None:
                raise approval_service.ApprovalNotFoundError(request_id)

        self._override_service(_RaisingService())

        response = self.client.get("/approvals/999")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()["detail"]["code"], "APPROVAL_NOT_FOUND"
        )

    def test_confirm_returns_409_when_already_reviewed(self) -> None:
        """이미 처리된 요청을 확정하면 409를 반환합니다."""

        class _RaisingService:
            async def confirm(self, request_id: int) -> None:
                raise approval_service.AlreadyReviewedError(request_id)

        self._override_service(_RaisingService())

        response = self.client.post("/approvals/1024/confirm")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "ALREADY_REVIEWED")

    def test_confirm_returns_422_when_no_registrable_crop(self) -> None:
        """등록 가능한 크롭이 없으면 422를 반환합니다."""

        class _RaisingService:
            async def confirm(self, request_id: int) -> None:
                raise approval_service.NoRegistrableCropError(request_id)

        self._override_service(_RaisingService())

        response = self.client.post("/approvals/1024/confirm")

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["detail"]["code"], "NO_REGISTRABLE_CROP"
        )

    def test_reject_returns_400_when_reason_missing(self) -> None:
        """반려 사유가 비어 있으면 400을 반환합니다."""

        class _RaisingService:
            async def reject(self, request_id: int, reject_reason: str) -> None:
                raise approval_service.RejectReasonRequiredError(request_id)

        self._override_service(_RaisingService())

        response = self.client.post(
            "/approvals/1024/reject", json={"rejectReason": ""}
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"]["code"], "REJECT_REASON_REQUIRED"
        )

    def test_list_passes_status_and_requested_range_query_params(
        self,
    ) -> None:
        """status·requestedFrom·requestedTo가 그대로 서비스에 전달됩니다."""
        captured: dict[str, object] = {}

        class _RecordingService:
            async def list_approvals(
                self,
                status: str,
                requested_from: datetime.datetime | None,
                requested_to: datetime.datetime | None,
            ) -> dict[str, object]:
                captured["status"] = status
                captured["requested_from"] = requested_from
                captured["requested_to"] = requested_to
                return {"items": []}

        self._override_service(_RecordingService())

        response = self.client.get(
            "/approvals"
            "?status=ALL"
            "&requestedFrom=2026-08-01T00:00:00"
            "&requestedTo=2026-08-11T23:59:59"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["status"], "ALL")
        self.assertEqual(
            captured["requested_from"],
            datetime.datetime(2026, 8, 1),
        )
        self.assertEqual(
            captured["requested_to"],
            datetime.datetime(2026, 8, 11, 23, 59, 59),
        )
        self.assertEqual(response.json(), {"items": []})


if __name__ == "__main__":
    unittest.main()
