"""SKU 텍스트 임베딩 검색 서비스의 조회·오류 계약을 검증합니다."""

import unittest

from app.services import sku_search_service
from app.services.gemini_service import GeminiConfigurationError


class _FakeMappingsResult:
    """SQLAlchemy Result.mappings() 인터페이스를 흉내 냅니다."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def mappings(self) -> "_FakeMappingsResult":
        """자기 자신을 반환해 체이닝을 흉내 냅니다."""
        return self

    def all(self) -> list[dict[str, object]]:
        """search_skus가 기대하는 다건 조회 결과입니다."""
        return self._rows

    def first(self) -> dict[str, object] | None:
        """get_sku_detail이 기대하는 단건 조회 결과입니다."""
        return self._rows[0] if self._rows else None


class _FakeSession:
    """준비된 결과를 그대로 돌려주는 DB 세션 대역입니다."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows
        self.executed_statements: list[object] = []

    async def execute(self, statement: object) -> _FakeMappingsResult:
        """실행된 statement를 기록하고 준비된 결과를 반환합니다."""
        self.executed_statements.append(statement)
        return _FakeMappingsResult(self._rows)


class _FakeGeminiService:
    """검색어 임베딩 호출을 흉내 내는 대역입니다."""

    def __init__(
        self,
        embedding: list[float] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._embedding = embedding
        self._error = error
        self.embedded_queries: list[str] = []

    def embed_text(self, text: str) -> list[float]:
        """설정된 벡터를 돌려주거나 준비된 예외를 던집니다."""
        self.embedded_queries.append(text)
        if self._error is not None:
            raise self._error
        assert self._embedding is not None
        return self._embedding


class _FakeSkuImageStorage:
    """저장 경로를 고정된 규칙으로 공개 URL로 바꾸는 대역입니다."""

    def public_url(self, stored_path: str | None) -> str:
        """접두사만 붙여 공개 URL 변환을 흉내 냅니다."""
        return f"https://cdn.example.com/{stored_path}"


def _valid_embedding() -> list[float]:
    """차원이 맞는 더미 임베딩 벡터를 만듭니다."""
    return [0.1] * sku_search_service.EMBEDDING_DIMENSIONS


class SearchSkusTest(unittest.IsolatedAsyncioTestCase):
    """search_skus의 정렬·변환·오류 처리를 검증합니다."""

    async def test_returns_items_ranked_by_similarity_with_converted_url(
        self,
    ) -> None:
        """distance를 0~100 유사도 점수로 바꾸고 이미지 URL을 변환합니다."""
        rows = [
            {
                "sku_code": "CHR-2041",
                "product_name": "북유럽 철제 선반",
                "category": "가구",
                "sub_category": "선반",
                "brand": "브랜드A",
                "price": 39000,
                "image_url": "data/images/13147_CHR-2041_WHITE_m_001.jpg",
                "similarity": 0.873,
            },
            {
                "sku_code": "CHR-3000",
                "product_name": "우드톤 책장",
                "category": "가구",
                "sub_category": "책장",
                "brand": None,
                "price": None,
                "image_url": None,
                "similarity": 0.5,
            },
        ]
        session = _FakeSession(rows)
        gemini_service = _FakeGeminiService(embedding=_valid_embedding())
        storage = _FakeSkuImageStorage()

        result = await sku_search_service.search_skus(
            session, gemini_service, storage, "북유럽 스타일 철제 선반"
        )

        self.assertEqual(len(result.skus), 2)
        first, second = result.skus
        self.assertEqual(first.sku_code, "CHR-2041")
        self.assertEqual(first.similarity_score, 87.3)
        self.assertEqual(
            first.image_url,
            "https://cdn.example.com/data/images/13147_CHR-2041_"
            "WHITE_m_001.jpg",
        )
        self.assertEqual(second.sku_code, "CHR-3000")
        self.assertIsNone(second.image_url)
        self.assertEqual(second.similarity_score, 50.0)
        self.assertEqual(
            gemini_service.embedded_queries, ["북유럽 스타일 철제 선반"]
        )

    async def test_raises_query_error_when_embedding_fails(self) -> None:
        """Gemini 임베딩 호출이 실패하면 도메인 오류로 변환합니다."""
        session = _FakeSession(rows=[])
        gemini_service = _FakeGeminiService(error=RuntimeError("boom"))

        with self.assertRaises(sku_search_service.SkuSearchQueryError):
            await sku_search_service.search_skus(
                session, gemini_service, _FakeSkuImageStorage(), "검색어"
            )

        self.assertEqual(session.executed_statements, [])

class GetSkuDetailTest(unittest.IsolatedAsyncioTestCase):
    """get_sku_detail의 조회·매핑을 검증합니다."""

    async def test_returns_detail_with_attributes_and_image_url(
        self,
    ) -> None:
        """attributes를 그대로 담고 이미지 경로를 공개 URL로 바꿉니다."""
        row = {
            "sku_code": "CHR-2041",
            "product_name": "북유럽 철제 선반",
            "brand": "브랜드A",
            "price": 39000,
            "category": "가구",
            "sub_category": "선반",
            "attributes": {"color": "WHITE", "material": "철제"},
            "image_url": "data/images/13147_CHR-2041_WHITE_m_001.jpg",
        }
        session = _FakeSession([row])

        detail = await sku_search_service.get_sku_detail(
            session, _FakeSkuImageStorage(), "CHR-2041"
        )

        assert detail is not None
        self.assertEqual(detail.sku_code, "CHR-2041")
        self.assertEqual(detail.attrs, {"color": "WHITE", "material": "철제"})
        self.assertEqual(
            detail.image_url,
            "https://cdn.example.com/data/images/13147_CHR-2041_"
            "WHITE_m_001.jpg",
        )

    async def test_returns_none_when_sku_code_not_found(self) -> None:
        """존재하지 않는 sku_code는 None을 반환합니다."""
        session = _FakeSession(rows=[])

        detail = await sku_search_service.get_sku_detail(
            session, _FakeSkuImageStorage(), "MISSING"
        )

        self.assertIsNone(detail)


if __name__ == "__main__":
    unittest.main()
