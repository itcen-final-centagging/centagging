"""공통 API 예외 처리기와 request_id 오류 추적을 검증합니다."""

import unittest

import fastapi
import pydantic
import starlette.testclient

from app.core.exception_handlers import register_exception_handlers
from app.core.request_context import RequestIdMiddleware


class ExceptionHandlerTest(unittest.TestCase):
    """전역 예외 처리기가 공통 오류 응답을 만드는지 검증합니다."""

    def setUp(self) -> None:
        """예외 처리기와 요청 ID 미들웨어가 적용된 앱을 준비합니다."""
        self.app = fastapi.FastAPI()
        self.app.add_middleware(RequestIdMiddleware)
        register_exception_handlers(self.app)

        @self.app.get("/missing")
        async def missing_resource() -> None:
            raise fastapi.HTTPException(status_code=404, detail="결과가 없습니다.")

        @self.app.post("/validation")
        async def validate_login(
            payload: _LoginPayload,
        ) -> dict[str, str]:
            return {"login_id": payload.login_id}

        @self.app.get("/unexpected")
        async def unexpected_error() -> None:
            raise RuntimeError("database connection failed")

        self.client = starlette.testclient.TestClient(
            self.app,
            raise_server_exceptions=False,
        )

    def test_http_exception_uses_common_error_response(self) -> None:
        """HTTPException은 HTTP 상태와 공통 오류 본문을 함께 반환합니다."""
        response = self.client.get("/missing")
        payload = response.json()

        self.assertEqual(response.status_code, 404)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "RESOURCE_NOT_FOUND")
        self.assertEqual(payload["error"]["message"], "결과가 없습니다.")
        self.assertEqual(payload["meta"]["request_id"], response.headers["X-Request-ID"])

    def test_validation_error_exposes_field_reason_and_message(self) -> None:
        """요청 검증 오류는 프런트가 사용할 필드 구조로 변환합니다."""
        response = self.client.post("/validation", json={})
        payload = response.json()

        self.assertEqual(response.status_code, 422)
        self.assertEqual(payload["error"]["code"], "VALIDATION_ERROR")
        self.assertEqual(
            payload["error"]["details"],
            [
                {
                    "field": "login_id",
                    "reason": "required",
                    "message": "필수 값입니다.",
                }
            ],
        )

    def test_unexpected_error_logs_request_id_and_hides_internal_detail(self) -> None:
        """예상 밖 오류는 추적 ID를 로그에 남기고 안전한 오류만 반환합니다."""
        with self.assertLogs("app.core.exception_handlers", level="ERROR") as logs:
            response = self.client.get("/unexpected")

        payload = response.json()
        request_id = response.headers["X-Request-ID"]
        self.assertEqual(response.status_code, 500)
        self.assertEqual(payload["error"]["code"], "INTERNAL_SERVER_ERROR")
        self.assertEqual(payload["error"]["message"], "서버 오류가 발생했습니다.")
        self.assertEqual(payload["meta"]["request_id"], request_id)
        self.assertTrue(any(request_id in message for message in logs.output))
        self.assertNotIn("database connection failed", str(payload))


class _LoginPayload(pydantic.BaseModel):
    """예외 처리기 테스트용 로그인 요청 모델입니다."""

    login_id: str
