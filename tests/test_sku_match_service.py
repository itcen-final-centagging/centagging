"""SKU 확정 저장 서비스의 DB 저장 규격을 검증합니다."""

import json
import pathlib
import types
import typing
import unittest

import sqlalchemy

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


class _IdempotentFakeSession(_FakeSession):
    """DB 유니크 제약을 모사해 동일 결과가 한 행만 유지되는지 검증합니다."""

    def __init__(self) -> None:
        super().__init__()
        self.result_ids: dict[tuple[int, int], int] = {}
        self.stored_values: dict[tuple[int, int], dict[str, object]] = {}

    async def execute(
        self,
        statement: object,
        parameters: dict[str, object] | None = None,
    ) -> _FakeResult:
        """조회·저장·상태 변경 SQL을 구분해 DB 동작을 모사합니다."""
        statement_sql = str(statement)
        values = parameters or {}
        self.statements.append(statement)
        self.executions.append(values)
        if "jsonb_array_length" in statement_sql:
            return _FakeResult(row={"object_count": 1})
        if "INSERT INTO tagging_result" not in statement_sql:
            return _FakeResult()

        key = (
            typing.cast(int, values["scene_image_id"]),
            typing.cast(int, values["object_idx"]),
        )
        if key in self.result_ids and "ON CONFLICT" not in statement_sql:
            raise sqlalchemy.exc.IntegrityError(
                statement_sql,
                values,
                RuntimeError("uq_result_scene_object"),
            )
        result_id = self.result_ids.setdefault(key, 91)
        self.stored_values[key] = values
        return _FakeResult(scalar=result_id)


class _SceneUpdateFailingSession(_FakeSession):
    """scene 완료 상태 저장에 실패하는 DB 세션 대역입니다."""

    async def execute(
        self,
        statement: object,
        parameters: dict[str, object] | None = None,
    ) -> _FakeResult:
        """scene 상태 변경 시 DB 오류를 발생시킵니다."""
        if "UPDATE scene_image" in str(statement):
            raise RuntimeError("scene update failed")
        return await super().execute(statement, parameters)


def _settings() -> config.Settings:
    """테스트용 고정 사용자 설정을 반환합니다."""
    return typing.cast(
        config.Settings,
        types.SimpleNamespace(mvp_login_id="mvp-user"),
    )


def _matching(
    sku_code: str = "CHR-2041",
    match_rank: int = 2,
) -> tagging.SkuMatching:
    """테스트에서 공통으로 사용하는 SKU 확정 요청을 반환합니다."""
    return tagging.SkuMatching(
        object_idx=0,
        sku_code=sku_code,
        match_rank=match_rank,
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


class SkuMatchServiceTest(unittest.IsolatedAsyncioTestCase):
    """SKU 확정 결과의 트랜잭션 저장을 검증합니다."""

    async def test_stores_xai_and_mood_with_current_schema_fields(self) -> None:
        """필수 식별값과 JSONB 값을 현재 DB 규격으로 저장합니다."""
        session = _FakeSession()
        service = sku_match_service.SkuMatchService(session, _settings())
        matching = _matching()

        result_ids = await service.confirm_matching(7, [matching])

        self.assertEqual(result_ids, [91])
        self.assertEqual(len(session.executions), 3)
        stored = session.executions[1]
        self.assertEqual(stored["scene_image_id"], 7)
        self.assertEqual(stored["object_idx"], 0)
        self.assertEqual(stored["match_source"], "RECOMMEND")
        self.assertEqual(stored["match_rank"], 2)
        self.assertEqual(stored["similarity_score"], 0.92)
        insert_sql = str(session.statements[1])
        self.assertNotIn("tag_values", insert_sql)
        self.assertIn("object_idx", insert_sql)
        self.assertIn("match_source", insert_sql)
        self.assertIn("match_rank", insert_sql)
        self.assertIn(
            "ON CONFLICT (scene_image_id, object_idx)",
            insert_sql,
        )
        self.assertIn("CAST(:xai_result AS jsonb)", insert_sql)
        self.assertNotIn("xai_status", insert_sql)
        self.assertNotIn("xai_fallback_reason", insert_sql)
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

    async def test_marks_scene_completed_after_matching_is_saved(self) -> None:
        """태깅 결과 저장이 끝나면 연출 이미지 처리를 완료 상태로 바꿉니다."""
        session = _FakeSession()
        service = sku_match_service.SkuMatchService(session, _settings())
        matching = _matching()

        await service.confirm_matching(7, [matching])

        scene_update = session.executions[-1]
        self.assertEqual(
            scene_update,
            {
                "scene_image_id": 7,
                "analysis_status": "completed",
                "analysis_error": None,
            },
        )

    async def test_repeated_matching_returns_same_result_without_duplicate(
        self,
    ) -> None:
        """동일한 저장 요청을 재시도해도 결과 행을 추가하지 않습니다."""
        session = _IdempotentFakeSession()
        service = sku_match_service.SkuMatchService(session, _settings())
        matching = _matching()

        first_result = await service.confirm_matching(7, [matching])
        second_result = await service.confirm_matching(7, [matching])

        self.assertEqual(first_result, [91])
        self.assertEqual(second_result, [91])
        self.assertEqual(len(session.result_ids), 1)

    async def test_reselecting_sku_updates_existing_matching(self) -> None:
        """같은 탐지 객체에서 SKU를 다시 고르면 기존 결과를 갱신합니다."""
        session = _IdempotentFakeSession()
        service = sku_match_service.SkuMatchService(session, _settings())
        first_matching = _matching()
        second_matching = _matching(sku_code="CHR-3000", match_rank=1)

        first_result = await service.confirm_matching(7, [first_matching])
        second_result = await service.confirm_matching(7, [second_matching])

        self.assertEqual(first_result, [91])
        self.assertEqual(second_result, [91])
        self.assertEqual(len(session.result_ids), 1)
        self.assertEqual(
            session.stored_values[(7, 0)]["sku_code"],
            "CHR-3000",
        )
        upsert_sql = str(session.statements[1])
        self.assertIn("similarity_grade = CASE", upsert_sql)
        self.assertIn("status = CASE", upsert_sql)
        self.assertIn("tagging_result.similarity_score", upsert_sql)
        self.assertIn("tagging_result.xai_result", upsert_sql)
        self.assertIn("tagging_result.vlm_mood", upsert_sql)

    async def test_rolls_back_matching_when_scene_update_fails(self) -> None:
        """scene 완료 변경이 실패하면 앞서 저장한 매핑도 롤백합니다."""
        session = _SceneUpdateFailingSession()
        service = sku_match_service.SkuMatchService(session, _settings())

        with self.assertRaisesRegex(RuntimeError, "scene update failed"):
            await service.confirm_matching(7, [_matching()])

        self.assertFalse(session.committed)
        self.assertTrue(session.rolled_back)


class TaggingResultDdlTest(unittest.TestCase):
    """초기화 DDL의 XAI JSONB 계약을 검증합니다."""

    def test_keeps_xai_json_without_fallback_state_columns(self) -> None:
        """XAI JSON 구조만 유지하고 별도 상태 컬럼은 만들지 않습니다."""
        schema_sql = (
            pathlib.Path(__file__).parents[1]
            / "docker"
            / "db"
            / "init"
            / "schema.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("xai_result ? 'summary'", schema_sql)
        self.assertIn("xai_result ? 'criteria'", schema_sql)
        self.assertNotIn("xai_status", schema_sql)
        self.assertNotIn("xai_fallback_reason", schema_sql)
        self.assertNotIn("ck_result_xai_status", schema_sql)
        self.assertNotIn("xai_result->>'total'", schema_sql)
