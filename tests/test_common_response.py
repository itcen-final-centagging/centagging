"""공통 API 응답 모델과 요청 ID 처리기를 검증합니다."""

import unittest
import uuid

import fastapi
import starlette.testclient

from app.core.error_codes import ErrorCode
from app.core.request_context import RequestIdMiddleware, get_request_id
from app.schemas.common import ErrorDetail, error_response, success_response


class CommonResponseTest(unittest.TestCase):
    """공통 응답 모델의 직렬화 규격을 검증합니다."""

    def test_success_response_contains_status_data_and_request_id(self) -> None:
        """성공 응답은 상태, 데이터, 요청 ID를 포함합니다."""
        response = success_response({"user_id": 1}, request_id="request-123")

        self.assertEqual(
            response.model_dump(),
            {
                "status": "success",
                "data": {"user_id": 1},
                "meta": {"request_id": "request-123"},
            },
        )

    def test_error_response_uses_error_code_and_details(self) -> None:
        """오류 응답은 오류 코드, 메시지, 상세 목록을 포함합니다."""
        response = error_response(
            ErrorCode.VALIDATION_ERROR,
            details=[
                ErrorDetail(
                    field="login_id",
                    reason="min_length",
                    message="아이디를 입력해 주세요.",
                )
            ],
            request_id="request-123",
        )

        self.assertEqual(
            response.model_dump(),
            {
                "status": "error",
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "요청 값을 확인해 주세요.",
                    "details": [
                        {
                            "field": "login_id",
                            "reason": "min_length",
                            "message": "아이디를 입력해 주세요.",
                        }
                    ],
                },
                "meta": {"request_id": "request-123"},
            },
        )


class RequestIdMiddlewareTest(unittest.TestCase):
    """요청 ID 미들웨어의 생성과 조회를 검증합니다."""

    def setUp(self) -> None:
        """요청 ID 미들웨어가 적용된 테스트 애플리케이션을 준비합니다."""
        self.app = fastapi.FastAPI()
        self.app.add_middleware(RequestIdMiddleware)

        @self.app.get("/request-id")
        async def request_id() -> dict[str, str | None]:
            return {"request_id": get_request_id()}

        self.client = starlette.testclient.TestClient(self.app)

    def test_middleware_generates_request_id_for_each_request(self) -> None:
        """미들웨어는 UUID 요청 ID를 생성해 핸들러와 응답 헤더에 제공합니다."""
        response = self.client.get("/request-id")
        request_id = response.headers["X-Request-ID"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["request_id"], request_id)
        self.assertEqual(str(uuid.UUID(request_id)), request_id)
