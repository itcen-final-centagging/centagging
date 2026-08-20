"""SKU 검색 API(GET /search/skus, GET /search/skus/{sku_code})를 검증합니다."""

import unittest
import unittest.mock

import fastapi
import starlette.testclient

from app import dependencies
from app.api import sku_search
from app.core import database, exception_handlers, request_context
from app.schemas import sku_search as sku_search_schema
from app.services.gemini_service import GeminiConfigurationError
from app.services.sku_search_service import SkuSearchQueryError


class SkuSearchApiTest(unittest.TestCase):
    """검색 API의 상태 코드·응답 계약을 검증합니다."""

    def setUp(self) -> None:
        """검색 라우터만 붙인 최소 FastAPI 앱을 구성합니다."""
        self.app = fastapi.FastAPI()
        self.app.add_middleware(request_context.RequestIdMiddleware)
        exception_handlers.register_exception_handlers(self.app)
        self.app.include_router(sku_search.router)

        self.session = object()

        async def override_database_session():
            yield self.session

        self.app.dependency_overrides[database.get_database_session] = (
            override_database_session
        )
        self.app.dependency_overrides[dependencies.get_gemini_service] = (
            lambda: object()
        )
        self.app.dependency_overrides[dependencies.get_sku_image_storage] = (
            lambda: object()
        )
        self.client = starlette.testclient.TestClient(self.app)

    def tearDown(self) -> None:
        """다음 테스트에 영향이 없도록 오버라이드를 정리합니다."""
        self.app.dependency_overrides.clear()

    def test_search_returns_ranked_skus(self) -> None:
        """검색 결과를 200과 함께 그대로 내려줍니다."""
        data = sku_search_schema.SkuSearchData(
            skus=[
                sku_search_schema.SkuSearchItem(
                    sku_code="CHR-2041",
                    product_name="북유럽 철제 선반",
                    category="가구",
                    sub_category="선반",
                    image_url="https://cdn.example.com/one.jpg",
                    brand="브랜드A",
                    price=39000,
                    similarity_score=87.3,
                )
            ]
        )
        with unittest.mock.patch.object(
            sku_search.sku_search_service,
            "search_skus",
            new=unittest.mock.AsyncMock(return_value=data),
        ) as search_skus:
            response = self.client.get(
                "/search/skus", params={"q": "북유럽 스타일 철제 선반"}
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "success")
        self.assertEqual(len(body["data"]["skus"]), 1)
        self.assertEqual(body["data"]["skus"][0]["sku_code"], "CHR-2041")
        search_skus.assert_awaited_once()
        self.assertEqual(
            search_skus.await_args.args[3], "북유럽 스타일 철제 선반"
        )

    def test_rejects_empty_query_without_calling_service(self) -> None:
        """검색어가 비어 있으면 400을 반환하고 서비스는 호출하지 않습니다."""
        with unittest.mock.patch.object(
            sku_search.sku_search_service,
            "search_skus",
            new=unittest.mock.AsyncMock(),
        ) as search_skus:
            response = self.client.get("/search/skus", params={"q": "  "})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "INVALID_QUERY")
        search_skus.assert_not_awaited()

    def test_returns_503_when_gemini_not_configured(self) -> None:
        """Gemini 인증이 안 된 상태는 503(SERVICE_UNAVAILABLE)입니다."""
        with unittest.mock.patch.object(
            sku_search.sku_search_service,
            "search_skus",
            new=unittest.mock.AsyncMock(
                side_effect=GeminiConfigurationError("not configured")
            ),
        ):
            response = self.client.get("/search/skus", params={"q": "검색어"})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["error"]["code"], "SERVICE_UNAVAILABLE"
        )

    def test_returns_502_when_embedding_query_fails(self) -> None:
        """임베딩·조회 실패는 502(UPSTREAM_ERROR)로 응답합니다."""
        with unittest.mock.patch.object(
            sku_search.sku_search_service,
            "search_skus",
            new=unittest.mock.AsyncMock(
                side_effect=SkuSearchQueryError("boom")
            ),
        ):
            response = self.client.get("/search/skus", params={"q": "검색어"})

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"]["code"], "UPSTREAM_ERROR")

    def test_detail_returns_sku_when_found(self) -> None:
        """존재하는 sku_code는 200과 상세 정보를 반환합니다."""
        detail = sku_search_schema.SkuDetailData(
            sku_code="CHR-2041",
            product_name="북유럽 철제 선반",
            brand="브랜드A",
            price=39000,
            category="가구",
            sub_category="선반",
            attrs={"color": "WHITE"},
            image_url="https://cdn.example.com/one.jpg",
        )
        with unittest.mock.patch.object(
            sku_search.sku_search_service,
            "get_sku_detail",
            new=unittest.mock.AsyncMock(return_value=detail),
        ):
            response = self.client.get("/search/skus/CHR-2041")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["attrs"], {"color": "WHITE"})

    def test_detail_returns_404_when_sku_code_not_found(self) -> None:
        """존재하지 않는 sku_code는 404(SKU_NOT_FOUND)입니다."""
        with unittest.mock.patch.object(
            sku_search.sku_search_service,
            "get_sku_detail",
            new=unittest.mock.AsyncMock(return_value=None),
        ):
            response = self.client.get("/search/skus/MISSING")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "SKU_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
