"""태깅 결과 저장 API의 공개 오류 응답을 검증합니다."""

import unittest

import fastapi
import httpx
import starlette.testclient

from app import dependencies
from app.api import tagging
from app.core import exception_handlers, request_context
from app.services import sku_match_service


class _FailingMatchService:
    """준비된 도메인 오류를 발생시키는 저장 서비스 대역입니다."""

    def __init__(self, error: RuntimeError) -> None:
        """저장 호출에서 발생시킬 오류를 설정합니다."""
        self.error = error

    async def confirm_matching(
        self,
        _scene_id: int,
        _matching: object,
    ) -> list[int]:
        """준비된 도메인 오류를 발생시킵니다."""
        raise self.error


class TaggingSaveApiTest(unittest.TestCase):
    """태깅 결과 저장 API의 HTTP 계약을 검증합니다."""

    def setUp(self) -> None:
        """태깅 라우터와 공통 오류 처리기를 준비합니다."""
        self.app = fastapi.FastAPI()
        self.app.add_middleware(request_context.RequestIdMiddleware)
        exception_handlers.register_exception_handlers(self.app)
        self.app.include_router(tagging.router)
        self.service_error: RuntimeError = (
            sku_match_service.MatchingTargetNotFoundError("MISSING-SKU")
        )
        self.app.dependency_overrides[dependencies.get_sku_match_service] = (
            lambda: _FailingMatchService(self.service_error)
        )
        self.client = starlette.testclient.TestClient(self.app)

    def _save_matching(self) -> httpx.Response:
        """유효한 태깅 결과 저장 요청을 전송합니다."""
        return self.client.put(
            "/tagging/scenes/7",
            json={
                "matching": [
                    {
                        "object_index": 0,
                        "sku_code": "MISSING-SKU",
                        "match_rank": 1,
                        "similarity_score": 80,
                        "xai_result": {
                            "summary": "후보를 찾지 못했습니다.",
                            "criteria": [],
                        },
                        "vlm_mood": {"summary": "", "tags": []},
                    }
                ]
            },
        )

    def test_returns_resource_not_found_when_sku_does_not_exist(self) -> None:
        """존재하지 않는 SKU는 요청 형식 오류가 아니라 404로 구분합니다."""
        response = self._save_matching()

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()["error"]["code"],
            "RESOURCE_NOT_FOUND",
        )
        self.assertEqual(
            response.json()["meta"]["request_id"],
            response.headers["X-Request-ID"],
        )

    def test_returns_validation_error_for_duplicate_object_index(self) -> None:
        """요청 내부 객체 인덱스 중복은 입력값 오류로 구분합니다."""
        self.service_error = sku_match_service.DuplicateObjectIndexError([0])

        response = self._save_matching()

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "VALIDATION_ERROR")

    def test_returns_resource_not_found_when_scene_does_not_exist(self) -> None:
        """존재하지 않는 연출 이미지는 404로 구분합니다."""
        self.service_error = sku_match_service.SceneImageNotFoundError(999)

        response = self._save_matching()

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()["error"]["code"],
            "RESOURCE_NOT_FOUND",
        )

    def test_returns_validation_error_for_out_of_range_object(self) -> None:
        """장면에 없는 객체 인덱스는 입력값 오류로 구분합니다."""
        self.service_error = sku_match_service.ObjectIndexOutOfRangeError([9])

        response = self._save_matching()

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "VALIDATION_ERROR")


if __name__ == "__main__":
    unittest.main()
