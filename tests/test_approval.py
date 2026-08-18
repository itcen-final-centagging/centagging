"""현재 태깅 결과 모델과 승인 API의 계약을 검증합니다."""

import datetime
import unittest

import fastapi
import starlette.testclient

from app import dependencies
from app.api import approval
from app.core import exception_handlers, request_context
from app.schemas import approval as approval_schema
from app.services import approval_service


class _ApprovalService:
    """승인 API 테스트용 서비스 대역입니다."""

    async def list_approvals(
        self, status: str
    ) -> approval_schema.ApprovalListResponse:
        return approval_schema.ApprovalListResponse(items=[])

    async def get_detail(
        self, request_id: int
    ) -> approval_schema.ApprovalDetailResponse:
        raise approval_service.ApprovalNotFoundError(request_id)

    async def confirm(
        self, request_id: int, reviewer_id: int, reviewer_name: str
    ) -> approval_schema.ConfirmResponse:
        return approval_schema.ConfirmResponse(
            request_id=request_id,
            reviewed_by_name=reviewer_name,
            reviewed_at=datetime.datetime(2026, 8, 15),
        )

    async def reject(
        self,
        request_id: int,
        reject_reason: str,
        reviewer_id: int,
        reviewer_name: str,
    ) -> approval_schema.RejectResponse:
        return approval_schema.RejectResponse(
            request_id=request_id,
            reviewed_by_name=reviewer_name,
            reviewed_at=datetime.datetime(2026, 8, 15),
            reject_reason=reject_reason,
        )


class ApprovalApiTest(unittest.TestCase):
    """승인 목록·승인·반려의 권한과 요청 계약을 검증합니다."""

    def setUp(self) -> None:
        self.app = fastapi.FastAPI()
        self.app.add_middleware(request_context.RequestIdMiddleware)
        exception_handlers.register_exception_handlers(self.app)
        self.app.include_router(approval.router)
        self.app.dependency_overrides[dependencies.get_approval_service] = (
            _ApprovalService
        )
        self.client = starlette.testclient.TestClient(self.app)

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()

    def _set_user(self, role: str) -> None:
        async def get_user() -> dependencies.AdminUser:
            return {
                "role": role,
                "user_id": 3,
                "user_name": "최종 관리자",
            }

        self.app.dependency_overrides[dependencies.get_admin_user] = get_user

    def test_admin_can_list_approval_requests(self) -> None:
        """일반 관리자는 승인 대기열을 조회할 수 있습니다."""
        self._set_user("ADMIN")

        response = self.client.get("/approvals?status=PENDING")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        self.assertEqual(response.json()["data"], {"items": []})

    def test_only_super_admin_can_confirm(self) -> None:
        """승인 등록은 최종 관리자 계정으로 제한됩니다."""
        self._set_user("ADMIN")

        response = self.client.post("/approvals/7/confirm")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "AUTH_FORBIDDEN")

    def test_super_admin_can_confirm(self) -> None:
        """최종 관리자는 선택 객체를 SKU 이미지로 승인할 수 있습니다."""
        self._set_user("SUPER_ADMIN")

        response = self.client.post("/approvals/7/confirm")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        self.assertEqual(response.json()["data"]["status"], "ACTIVE")
        self.assertEqual(
            response.json()["data"]["reviewedByName"], "최종 관리자"
        )

    def test_reject_requires_a_reason(self) -> None:
        """반려 사유가 빠지면 공통 422 오류를 반환합니다."""
        self._set_user("SUPER_ADMIN")

        response = self.client.post("/approvals/7/reject", json={})

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "VALIDATION_ERROR")
