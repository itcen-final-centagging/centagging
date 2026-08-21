"""융합 임베딩 파이프라인 버전 필터 테스트입니다."""

import asyncio
import types

from sqlalchemy.dialects import postgresql

from app.services import similar_sku_service


class _Result:
    """비어 있는 매핑 결과입니다."""

    def mappings(self) -> "_Result":
        return self

    def all(self) -> list[dict[str, object]]:
        return []


class _Session:
    """실행할 SQLAlchemy 문을 기록합니다."""

    def __init__(self) -> None:
        self.statement: object | None = None

    async def execute(self, statement: object) -> _Result:
        self.statement = statement
        return _Result()


def test_similarity_query_filters_pipeline_version() -> None:
    """새 쿼리 벡터와 구 카탈로그 벡터가 섞여 검색되지 않는다."""
    session = _Session()
    service = similar_sku_service.SimilarSkuService(
        session=session,  # type: ignore[arg-type]
        gemini_service=types.SimpleNamespace(),  # type: ignore[arg-type]
        settings=types.SimpleNamespace(
            sku_image_root="data/images",
            embedding_pipeline_version="2026-08-21.1",
        ),
    )

    asyncio.run(
        service.find_similar_skus(
            [0.1] * similar_sku_service.EMBEDDING_DIMENSIONS
        )
    )

    assert session.statement is not None
    sql = str(session.statement.compile(dialect=postgresql.dialect()))
    assert "sku_image.embedding_pipeline_version" in sql
    assert "embedding_pipeline_version" in sql
    assert "sku_image.embedding_image_sha256" in sql
