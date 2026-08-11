"""SKU 확정 저장 서비스의 DB 저장 규격을 검증합니다."""

import json
import types
import typing
import unittest

from app.core import config
from app.schemas import tagging
from app.services import sku_match_service


class _FakeResult:
    """DB 조회와 INSERT 결과를 반환합니다."""

    def __init__(
        self,
        row: dict[str, object] | None = None,
        scalar: int | None = None,
    ) -> None:
        self.row = row
        self.scalar = scalar

    def mappings(self) -> "_FakeResult":
        """SQLAlchemy mappings 결과 인터페이스를 표현합니다."""
        return self

    def first(self) -> dict[str, object] | None:
        """첫 번째 조회 행을 반환합니다."""
        return self.row

    def scalar_one_or_none(self) -> int | None:
        """INSERT로 생성된 result_id를 반환합니다."""
        return self.scalar


class _FakeSession:
    """서비스가 DB 어댑터에 전달한 저장값을 기록합니다."""

    def __init__(self) -> None:
        self.statements: list[object] = []
        self.executions: list[dict[str, object]] = []
        self.committed = False
        self.rolled_back = False

    async def execute(
        self,
        _statement: object,
        parameters: dict[str, object] | None = None,
    ) -> _FakeResult:
        """scene_image 조회 후 저장 결과를 순서대로 반환합니다."""
        self.statements.append(_statement)
        self.executions.append(parameters or {})
        if len(self.executions) == 1:
            return _FakeResult(row={"object_count": 1})
        return _FakeResult(scalar=91)

    async def commit(self) -> None:
        """커밋 호출 여부를 기록합니다."""
        self.committed = True

    async def rollback(self) -> None:
        """롤백 호출 여부를 기록합니다."""
        self.rolled_back = True


class SkuMatchServiceTest(unittest.IsolatedAsyncioTestCase):
    """SKU 확정 결과의 트랜잭션 저장을 검증합니다."""

    async def test_stores_xai_and_mood_with_current_schema_fields(self) -> None:
        """필수 식별값과 JSONB 값을 현재 DB 규격으로 저장합니다."""
        session = _FakeSession()
        settings = typing.cast(
            config.Settings,
            types.SimpleNamespace(mvp_login_id="mvp-user"),
        )
        service = sku_match_service.SkuMatchService(session, settings)
        matching = tagging.SkuMatching(
            object_index=0,
            sku_code="CHR-2041",
            match_rank=2,
            similarity_score=92,
            xai_result=tagging.XaiResult(
                summary="구조와 색상이 유사합니다.",
                criteria=[],
            ),
            vlm_mood=tagging.VlmMood(
                summary="따뜻한 거실 분위기입니다.",
                tags=["내추럴"],
            ),
        )

        result_ids = await service.confirm_matching(7, [matching])

        self.assertEqual(result_ids, [91])
        self.assertEqual(len(session.executions), 2)
        stored = session.executions[1]
        self.assertEqual(stored["scene_image_id"], 7)
        self.assertEqual(stored["object_index"], 0)
        self.assertEqual(stored["match_source"], "RECOMMEND")
        self.assertEqual(stored["match_rank"], 2)
        self.assertEqual(stored["similarity_score"], 0.92)
        insert_sql = str(session.statements[1])
        self.assertNotIn("tag_values", insert_sql)
        self.assertIn("object_index", insert_sql)
        self.assertIn("match_source", insert_sql)
        self.assertIn("match_rank", insert_sql)
        self.assertIn("CAST(:xai_result AS jsonb)", insert_sql)
        self.assertIn("CAST(:vlm_mood AS jsonb)", insert_sql)
        self.assertEqual(
            json.loads(typing.cast(str, stored["xai_result"])),
            {
                "summary": "구조와 색상이 유사합니다.",
                "criteria": [],
            },
        )
        self.assertEqual(
            json.loads(typing.cast(str, stored["vlm_mood"])),
            {
                "summary": "따뜻한 거실 분위기입니다.",
                "tags": ["내추럴"],
            },
        )
        self.assertTrue(session.committed)
        self.assertFalse(session.rolled_back)
