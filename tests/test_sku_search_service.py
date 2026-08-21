"""SKU 텍스트 임베딩 검색 서비스의 조회·오류 처리·재정렬을 검증합니다."""

import typing
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
    """검색어 임베딩·후보 재정렬 호출을 흉내 내는 대역입니다."""

    def __init__(
        self,
        embedding: list[float] | None = None,
        error: Exception | None = None,
        rerank_result: list[str] | None = None,
        rerank_error: Exception | None = None,
    ) -> None:
        self._embedding = embedding
        self._error = error
        self._rerank_result = rerank_result
        self._rerank_error = rerank_error
        self.embedded_queries: list[str] = []
        self.rerank_calls: list[
            tuple[str, list[dict[str, typing.Any]], int]
        ] = []

    def embed_text(self, text: str) -> list[float]:
        """설정된 벡터를 돌려주거나 준비된 예외를 던집니다."""
        self.embedded_queries.append(text)
        if self._error is not None:
            raise self._error
        assert self._embedding is not None
        return self._embedding

    def rerank_sku_candidates(
        self,
        query: str,
        candidates: list[dict[str, typing.Any]],
        top_k: int,
    ) -> list[str]:
        """설정된 순서를 돌려주거나 준비된 예외를 던집니다.

        이 대역이 애초에 정의되지 않은 경우(속성 자체가 없는 경우)를
        검증하는 기존 테스트와 달리, 이 대역은 재정렬이 "명시적으로"
        실패하는 경우까지 검증하기 위해 존재합니다.
        """
        self.rerank_calls.append((query, candidates, top_k))
        if self._rerank_error is not None:
            raise self._rerank_error
        assert self._rerank_result is not None
        return self._rerank_result


class _FakeSkuImageStorage:
    """저장 경로를 고정된 규칙으로 공개 URL로 바꾸는 대역입니다."""

    def public_url(self, stored_path: str | None) -> str:
        """접두사만 붙여 공개 URL 변환을 흉내 냅니다."""
        return f"https://cdn.example.com/{stored_path}"


def _valid_embedding() -> list[float]:
    """차원이 맞는 더미 임베딩 벡터를 만듭니다."""
    return [0.1] * sku_search_service.EMBEDDING_DIMENSIONS


def _row(sku_code: str, **overrides: object) -> dict[str, object]:
    """재정렬 테스트에 필요한 필드를 모두 채운 후보 행을 만듭니다."""
    row: dict[str, object] = {
        "sku_code": sku_code,
        "product_name": f"{sku_code} 상품",
        "category": "가구",
        "sub_category": "선반",
        "brand": None,
        "price": None,
        "attributes": {},
        "image_url": None,
        "similarity": 0.5,
    }
    row.update(overrides)
    return row


class SearchSkusTest(unittest.IsolatedAsyncioTestCase):
    """search_skus의 정렬·변환·오류 처리·재정렬을 검증합니다."""

    async def test_returns_items_ranked_by_similarity_with_converted_url(
        self,
    ) -> None:
        """distance를 0~100 유사도 점수로 바꾸고 이미지 URL을 변환합니다.

        이 케이스의 gemini_service 대역은 rerank_sku_candidates를
        정의하지 않으므로(속성 자체가 없음), search_skus는 재정렬을
        조용히 건너뛰고 코사인 유사도 순서를 그대로 반환해야 합니다 —
        재정렬 도입 이후에도 기존 호출자와의 하위 호환을 검증합니다.
        """
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

    async def test_reorders_results_by_gemini_rerank_order(self) -> None:
        """Gemini가 반환한 sku_code 순서로 최종 결과를 재정렬합니다."""
        rows = [
            _row("SOFA-A", similarity=0.9),
            _row("SOFA-B", similarity=0.8),
            _row("SOFA-C", similarity=0.7),
        ]
        session = _FakeSession(rows)
        gemini_service = _FakeGeminiService(
            embedding=_valid_embedding(),
            rerank_result=["SOFA-C", "SOFA-A", "SOFA-B"],
        )

        result = await sku_search_service.search_skus(
            session,
            gemini_service,
            _FakeSkuImageStorage(),
            "3인용 패브릭 소파",
        )

        self.assertEqual(
            [item.sku_code for item in result.skus],
            ["SOFA-C", "SOFA-A", "SOFA-B"],
        )
        self.assertEqual(len(gemini_service.rerank_calls), 1)
        query, candidates, top_k = gemini_service.rerank_calls[0]
        self.assertEqual(query, "3인용 패브릭 소파")
        self.assertEqual(top_k, sku_search_service.DEFAULT_RESULT_LIMIT)
        self.assertEqual(
            {candidate["sku_code"] for candidate in candidates},
            {"SOFA-A", "SOFA-B", "SOFA-C"},
        )

    async def test_falls_back_to_similarity_order_when_rerank_fails(
        self,
    ) -> None:
        """재정렬 호출이 실패하면 코사인 유사도 순서를 그대로 씁니다.

        재정렬은 부가 기능이므로 실패해도 검색 자체가 깨지면 안 됩니다
        (sku-search-test 실험에서 재정렬 실패가 조용히 결과를 망가뜨렸던
        문제를 다시 겪지 않도록, 실패 시에도 결과가 채워지는지 직접
        검증합니다).
        """
        rows = [
            _row("SOFA-A", similarity=0.9),
            _row("SOFA-B", similarity=0.8),
        ]
        session = _FakeSession(rows)
        gemini_service = _FakeGeminiService(
            embedding=_valid_embedding(),
            rerank_error=RuntimeError("gemini unavailable"),
        )

        result = await sku_search_service.search_skus(
            session, gemini_service, _FakeSkuImageStorage(), "검색어"
        )

        self.assertEqual(
            [item.sku_code for item in result.skus], ["SOFA-A", "SOFA-B"]
        )

    async def test_reranks_full_pool_then_truncates_to_final_limit(
        self,
    ) -> None:
        """전체 후보 풀을 재정렬 대상으로 넘기고, 최종 결과만 limit개로 자릅니다.

        실제 DB 조회는 CANDIDATE_POOL_SIZE만큼 후보를 가져오도록 SQL의
        LIMIT을 넉넉히 잡습니다(SQL 자체는 이 유닛 테스트의 대역이
        검증하지 않는 영역입니다). 여기서는 조회된 후보 풀 전체가
        재정렬 대상으로 넘어가고, 최종 응답만 요청한 limit개로
        잘리는지를 검증합니다.
        """
        rows = [
            _row(f"SKU-{i:02d}", similarity=1.0 - i * 0.01)
            for i in range(sku_search_service.CANDIDATE_POOL_SIZE)
        ]
        session = _FakeSession(rows)
        gemini_service = _FakeGeminiService(
            embedding=_valid_embedding(), rerank_result=[]
        )

        result = await sku_search_service.search_skus(
            session, gemini_service, _FakeSkuImageStorage(), "검색어", limit=5
        )

        self.assertEqual(len(result.skus), 5)
        self.assertEqual(
            [item.sku_code for item in result.skus],
            ["SKU-00", "SKU-01", "SKU-02", "SKU-03", "SKU-04"],
        )
        self.assertEqual(len(session.executed_statements), 1)
        _, candidates, top_k = gemini_service.rerank_calls[0]
        self.assertEqual(
            len(candidates), sku_search_service.CANDIDATE_POOL_SIZE
        )
        self.assertEqual(top_k, 5)



class GetSkuDetailTest(unittest.IsolatedAsyncioTestCase):
    """get_sku_detail의 조회·매핑을 검증합니다."""

    async def test_returns_detail_with_attributes_and_image_url(
        self,
    ) -> None:
        """attributes를 그대로 담고 이미지 경로를 공개 URL로 바꿉니다."""
        row = {
            "sku_id": 501,
            "sku_code": "CHR-2041",
            "product_name": "북유럽 철제 선반",
            "brand": "브랜드A",
            "price": 39000,
            "category": "가구",
            "sub_category": "선반",
            "attributes": {"color": "WHITE", "material": "철제"},
            "image_url": "data/images/13147_CHR-2041_WHITE_m_001.jpg",
            "sku_image_id": 9001,
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
