"""SKU 승인 시 텍스트 임베딩 자동 재생성 규칙을 검증합니다."""

import types
import typing
import unittest

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import sku as sku_models
from app.services import approval_service


class _FakeMoodResult:  # pylint: disable=too-few-public-methods
    """승인된 vlm_mood 조회 결과 대역입니다."""

    def __init__(self, rows: list[tuple[dict, ...]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[dict, ...]]:
        """조회된 vlm_mood 행을 그대로 반환합니다."""
        return self._rows


class _FakeSession:
    """텍스트 재색인에 필요한 최소 세션 대역입니다."""

    def __init__(
        self,
        sku: sku_models.SkuCatalog | None,
        vlm_moods: list[dict],
    ) -> None:
        self._sku = sku
        self._vlm_moods = vlm_moods
        self.committed = False
        self.rolled_back = False
        self.executed_params: list[dict[str, object]] = []

    async def get(
        self, model: type, primary_key: object, **_kwargs: object
    ) -> object | None:
        """저장된 SKU의 기본키가 일치하면 반환합니다."""
        if model is not sku_models.SkuCatalog or self._sku is None:
            return None
        if self._sku.sku_id != primary_key:
            return None
        return self._sku

    async def execute(
        self, statement: object, parameters: dict[str, object]
    ) -> _FakeMoodResult:
        """실행된 조회 파라미터를 기록하고 고정 vlm_mood 목록을 돌려줍니다."""
        del statement
        self.executed_params.append(parameters)
        return _FakeMoodResult([(mood,) for mood in self._vlm_moods])

    async def commit(self) -> None:
        """커밋 호출 여부를 기록합니다."""
        self.committed = True

    async def rollback(self) -> None:
        """롤백 호출 여부를 기록합니다."""
        self.rolled_back = True


class _FakeGeminiService:
    """텍스트 임베딩 호출을 기록하는 Gemini 서비스 대역입니다."""

    def __init__(
        self,
        embedding: list[float] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.embedding = embedding
        self.error = error
        self.calls: list[str] = []

    def embed_text(self, text: str) -> list[float]:
        """호출된 텍스트를 기록하고 고정 벡터를 반환하거나 오류를 냅니다."""
        self.calls.append(text)
        if self.error is not None:
            raise self.error
        assert self.embedding is not None
        return self.embedding


def _sku(sku_id: int = 1) -> sku_models.SkuCatalog:
    """재색인 대상 SKU 픽스처를 만듭니다."""
    return sku_models.SkuCatalog(
        sku_id=sku_id,
        sku_code="CHAIR-001",
        product_name="메쉬 사무용 의자",
        category="의자",
        sub_category="학생·사무용의자",
        attributes={"color": "블랙"},
        key_features=["높이 조절"],
    )


def _service(
    session: _FakeSession, gemini_service: _FakeGeminiService
) -> approval_service.ApprovalService:
    """세션·Gemini 서비스 대역이 주입된 ApprovalService를 만듭니다."""
    return approval_service.ApprovalService(
        session=typing.cast(AsyncSession, session),
        settings=types.SimpleNamespace(sku_image_root="/tmp"),
        gemini_service=typing.cast(
            approval_service.GeminiService, gemini_service
        ),
    )


class ReindexSkuTextEmbeddingTest(unittest.IsolatedAsyncioTestCase):
    """승인 누적 vlm_mood를 반영한 텍스트 재색인 규칙을 검증합니다."""

    async def test_accumulates_mood_and_tags_from_active_approvals(
        self,
    ) -> None:
        """서로 다른 승인 건의 공간 분위기·스타일 태그를 중복 없이 반영한다."""
        sku = _sku()
        session = _FakeSession(
            sku=sku,
            vlm_moods=[
                {"summary": "따뜻한 우드톤 거실", "tags": ["우드", "내추럴"]},
                {"summary": "따뜻한 우드톤 거실", "tags": ["우드", "미니멀"]},
            ],
        )
        gemini_service = _FakeGeminiService(embedding=[0.1, 0.2])
        service = _service(session, gemini_service)

        # pylint: disable=protected-access
        await service._reindex_sku_text_embedding(sku.sku_id)

        self.assertEqual(len(gemini_service.calls), 1)
        self.assertEqual(
            gemini_service.calls[0],
            "\n".join(
                [
                    "메쉬 사무용 의자",
                    "카테고리: 의자 > 학생·사무용의자",
                    "속성: color: 블랙",
                    "특징: 높이 조절",
                    "공간 분위기: 따뜻한 우드톤 거실",
                    "스타일 태그: 우드, 내추럴, 미니멀",
                ]
            ),
        )
        self.assertEqual(sku.text_embedding, [0.1, 0.2])
        self.assertTrue(session.committed)
        self.assertEqual(session.executed_params, [{"sku_id": sku.sku_id}])

    async def test_embedding_failure_does_not_raise_and_rolls_back(
        self,
    ) -> None:
        """텍스트 임베딩 호출이 실패해도 예외를 올리지 않고 롤백만 한다."""
        sku = _sku()
        session = _FakeSession(sku=sku, vlm_moods=[])
        gemini_service = _FakeGeminiService(error=RuntimeError("gemini down"))
        service = _service(session, gemini_service)

        # pylint: disable=protected-access
        await service._reindex_sku_text_embedding(sku.sku_id)

        self.assertTrue(session.rolled_back)
        self.assertFalse(session.committed)
        self.assertIsNone(sku.text_embedding)

    async def test_missing_sku_does_not_raise(self) -> None:
        """SKU를 찾지 못해도 예외를 밖으로 올리지 않는다(승인 자체는 보존)."""
        session = _FakeSession(sku=None, vlm_moods=[])
        gemini_service = _FakeGeminiService(embedding=[0.0])
        service = _service(session, gemini_service)

        # pylint: disable=protected-access
        await service._reindex_sku_text_embedding(999)

        self.assertEqual(gemini_service.calls, [])
        self.assertTrue(session.rolled_back)
