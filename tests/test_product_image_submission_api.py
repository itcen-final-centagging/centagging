"""제품 이미지 등록 요청의 권한·상태 API 계약을 검증합니다."""

import datetime
import io
import unittest

import fastapi
import PIL.Image
import starlette.testclient

from app import dependencies
from app.api import product_image_submissions
from app.core import exception_handlers, request_context
from app.schemas import product_image_submission as submission_schema


def _image_bytes() -> bytes:
    """multipart 요청에 넣을 유효한 PNG 바이트를 생성합니다."""
    buffer = io.BytesIO()
    PIL.Image.new("RGB", (24, 24), color="white").save(buffer, format="PNG")
    return buffer.getvalue()


def _item(
    *, status: submission_schema.SubmissionStatus = "DRAFT"
) -> submission_schema.ProductImageSubmissionItem:
    """테스트용 등록 요청 한 건을 만듭니다."""
    return submission_schema.ProductImageSubmissionItem(
        image_type="MAIN",
        image_url="/uploads/sku/submissions/item.png",
        requested_at=datetime.datetime(
            2026, 8, 15, tzinfo=datetime.timezone.utc
        ),
        requested_by_name="상품 관리자",
        status=status,
        submission_id=8,
    )


class _ProductImageSubmissionService:
    """라우터 계약 확인용 서비스 대역입니다."""

    def __init__(self) -> None:
        self.list_arguments: dict[str, object] | None = None
        self.create_arguments: tuple[list[tuple[str, bytes]], int] | None = None
        self.approve_arguments: tuple[int, int] | None = None

    async def create_drafts(
        self, images: list[tuple[str, bytes]], requester_id: int
    ) -> list[submission_schema.ProductImageSubmissionItem]:
        self.create_arguments = (images, requester_id)
        return [_item()]

    async def list_submissions(
        self,
        *,
        requester_id: int,
        is_super_admin: bool,
        status: str,
    ) -> submission_schema.ProductImageSubmissionListResponse:
        self.list_arguments = {
            "requester_id": requester_id,
            "is_super_admin": is_super_admin,
            "status": status,
        }
        return submission_schema.ProductImageSubmissionListResponse(
            items=[_item()]
        )

    async def approve(
        self, submission_id: int, *, reviewer_id: int
    ) -> submission_schema.ProductImageSubmissionDetail:
        self.approve_arguments = (submission_id, reviewer_id)
        item = _item(status="APPROVED").model_dump()
        item.update(final_sku_id=31, final_sku_image_id=44)
        return submission_schema.ProductImageSubmissionDetail(**item)


class ProductImageSubmissionApiTest(unittest.TestCase):
    """일괄 업로드·조회 범위·최종 승인 권한을 확인합니다."""

    def setUp(self) -> None:
        self.app = fastapi.FastAPI()
        self.app.add_middleware(request_context.RequestIdMiddleware)
        exception_handlers.register_exception_handlers(self.app)
        self.app.include_router(product_image_submissions.router)
        self.service = _ProductImageSubmissionService()
        self.app.dependency_overrides[
            dependencies.get_product_image_submission_service
        ] = lambda: self.service
        self.client = starlette.testclient.TestClient(self.app)

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()

    def _set_user(self, role: str, user_id: int = 3) -> None:
        async def get_user() -> dependencies.AdminUser:
            return {
                "role": role,
                "user_id": user_id,
                "user_name": "상품 관리자",
            }

        self.app.dependency_overrides[dependencies.get_admin_user] = get_user

    def test_admin_uploads_multiple_draft_items(self) -> None:
        """한 번의 업로드가 파일 단위 DRAFT 큐로 전달됩니다."""
        self._set_user("ADMIN", user_id=11)

        response = self.client.post(
            "/product-image-submissions",
            files=[
                ("images", ("one.png", _image_bytes(), "image/png")),
                ("images", ("two.png", _image_bytes(), "image/png")),
            ],
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "success")
        self.assertEqual(response.json()["data"]["items"][0]["status"], "DRAFT")
        self.assertIsNotNone(self.service.create_arguments)
        assert self.service.create_arguments is not None
        self.assertEqual(self.service.create_arguments[1], 11)
        self.assertEqual(
            [filename for filename, _ in self.service.create_arguments[0]],
            ["one.png", "two.png"],
        )

    def test_admin_list_is_limited_to_own_status_scope(self) -> None:
        """일반 관리자의 목록 요청은 서비스에 본인 범위로 전달됩니다."""
        self._set_user("ADMIN", user_id=11)

        response = self.client.get("/product-image-submissions?status=PENDING")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.service.list_arguments,
            {
                "requester_id": 11,
                "is_super_admin": False,
                "status": "PENDING",
            },
        )

    def test_regular_admin_cannot_approve(self) -> None:
        """일반 관리자는 SKU 반영 승인을 실행할 수 없습니다."""
        self._set_user("ADMIN")

        response = self.client.post("/product-image-submissions/8/approve")

        self.assertEqual(response.status_code, 403)
        self.assertIsNone(self.service.approve_arguments)

    def test_super_admin_approves_submission(self) -> None:
        """최종 관리자는 PENDING 요청을 승인할 수 있습니다."""
        self._set_user("SUPER_ADMIN", user_id=19)

        response = self.client.post("/product-image-submissions/8/approve")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        self.assertEqual(response.json()["data"]["status"], "APPROVED")
        self.assertEqual(self.service.approve_arguments, (8, 19))
