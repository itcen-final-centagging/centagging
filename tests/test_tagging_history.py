"""태깅 이력 목록 조회 API 테스트입니다."""

import collections.abc
import datetime
import decimal
import unittest

import fastapi
import starlette.testclient

from app.api import history
from app.core import database


class _FakeResult:
    """SQLAlchemy 목록 조회 결과를 흉내 냅니다."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def mappings(self) -> "_FakeResult":
        """매핑 결과 체인을 유지합니다."""
        return self

    def all(self) -> list[dict[str, object]]:
        """조회 행을 반환합니다."""
        return self._rows

    def one_or_none(self) -> dict[str, object] | None:
        """상세 조회 행을 반환합니다."""
        return self._rows[0] if self._rows else None


class _FakeSession:
    """목록 조회 테스트용 비동기 DB 세션입니다."""

    def __init__(
        self,
        rows: list[dict[str, object]],
        detail_row: dict[str, object] | None,
    ) -> None:
        self._rows = rows
        self.detail_row = detail_row
        self.executed_statement = ""

    async def execute(
        self,
        statement: object,
        parameters: dict[str, object] | None = None,
    ) -> _FakeResult:
        """준비된 목록 조회 결과를 반환합니다."""
        self.executed_statement = str(statement)
        if parameters is not None:
            rows = [self.detail_row] if self.detail_row is not None else []
            return _FakeResult(rows)
        return _FakeResult(self._rows)


class TaggingHistoryApiTest(unittest.TestCase):
    """태깅 이력 목록의 공개 HTTP 동작을 검증합니다."""

    def setUp(self) -> None:
        """태깅 이력 라우터와 테스트 DB 세션을 연결합니다."""
        rows = [
            {
                "result_id": 8801,
                "sku_code": "CHR-2041",
                "product_name": "에르고 메쉬 오피스체어 화이트",
                "object_name": "의자",
                "similarity_score": decimal.Decimal("0.9200"),
                "created_by": "김태깅",
                "created_at": datetime.datetime(
                    2026,
                    8,
                    10,
                    17,
                    56,
                    tzinfo=datetime.timezone(datetime.timedelta(hours=9)),
                ),
                "image_url": "/uploads/scene-images/9f2c.jpg",
                "origin_name": "scene_office_01.jpg",
                "bbox": {
                    "xmin": 262,
                    "ymin": 300,
                    "xmax": 681,
                    "ymax": 890,
                },
            }
        ]
        detail_row = {
            "result_id": 9901,
            "created_by": "김태깅",
            "created_at": datetime.datetime(
                2026,
                8,
                11,
                9,
                30,
                tzinfo=datetime.timezone(datetime.timedelta(hours=9)),
            ),
            "similarity_score": decimal.Decimal("0.8750"),
            "scene_image_url": "/uploads/scene-images/detail.jpg",
            "origin_name": "scene_detail.jpg",
            "bbox": {
                "xmin": 100,
                "ymin": 200,
                "xmax": 500,
                "ymax": 800,
            },
            "sku_code": "CHR-9901",
            "product_name": "메쉬 사무용 의자",
            "brand": "센터퍼니처",
            "price": 249000,
            "sku_image_url": "/uploads/sku-images/CHR-9901_main.jpg",
            "category": "의자",
            "sub_category": "학생·사무용의자",
            "attributes": {"color": "화이트", "material": "메쉬"},
            "xai_result": {"summary": "형태와 색상이 유사합니다."},
        }
        self.session = _FakeSession(rows, detail_row)
        self.app = fastapi.FastAPI()
        self.app.include_router(history.router)

        async def override_database_session() -> (
            collections.abc.AsyncIterator[_FakeSession]
        ):
            yield self.session

        self.app.dependency_overrides[database.get_database_session] = (
            override_database_session
        )
        self.client = starlette.testclient.TestClient(self.app)

    def test_returns_fields_used_by_history_page(self) -> None:
        """검수 이력 화면에 필요한 저장 결과를 반환합니다."""
        response = self.client.get("/history/results")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "success",
                "data": {
                    "items": [
                        {
                            "result_id": 8801,
                            "sku_code": "CHR-2041",
                            "product_name": ("에르고 메쉬 오피스체어 화이트"),
                            "object_name": "의자",
                            "similarity_score": 92,
                            "created_by": "김태깅",
                            "created_at": "2026-08-10T17:56:00+09:00",
                            "style_tags": [],
                            "scene_image": {
                                "image_url": ("/uploads/scene-images/9f2c.jpg"),
                                "origin_name": "scene_office_01.jpg",
                                "bbox": {
                                    "xmin": 262,
                                    "ymin": 300,
                                    "xmax": 681,
                                    "ymax": 890,
                                },
                            },
                        }
                    ]
                },
            },
        )

    def test_returns_empty_items_when_history_does_not_exist(self) -> None:
        """저장된 태깅 결과가 없으면 빈 목록을 반환합니다."""
        self.session._rows = []

        response = self.client.get("/history/results")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": "success", "data": {"items": []}},
        )

    def test_queries_bbox_by_object_index_in_newest_first_order(self) -> None:
        """객체 좌표를 선택하고 저장 시각 최신순으로 조회합니다."""
        self.client.get("/history/results")

        self.assertIn(
            "si.bbox_coord -> tr.object_index",
            self.session.executed_statement,
        )
        self.assertIn(
            "ORDER BY tr.created_at DESC, tr.result_id DESC",
            self.session.executed_statement,
        )

    def test_returns_saved_tagging_history_detail(self) -> None:
        """저장된 연출 이미지와 확정 SKU 상세 정보를 반환합니다."""
        response = self.client.get("/history/results/9901")

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["result_id"], 9901)
        self.assertEqual(data["similarity_score"], 88)
        self.assertEqual(data["scene_image"]["origin_name"], "scene_detail.jpg")
        self.assertEqual(
            data["detected_object"]["bbox"],
            {"xmin": 100, "ymin": 200, "xmax": 500, "ymax": 800},
        )
        self.assertIsNone(data["detected_object"]["category"])
        self.assertEqual(data["detected_object"]["attrs"], {})
        self.assertIsNone(data["detected_object"]["vlm_mood"])
        self.assertEqual(data["matched_sku"]["sku_code"], "CHR-9901")
        self.assertEqual(
            data["matched_sku"]["image_url"],
            "/uploads/sku-images/CHR-9901_main.jpg",
        )
        self.assertEqual(
            data["xai_result"],
            {"summary": "형태와 색상이 유사합니다."},
        )

    def test_returns_404_when_tagging_history_does_not_exist(self) -> None:
        """결과 ID에 해당하는 태깅 이력이 없으면 404를 반환합니다."""
        self.session.detail_row = None

        response = self.client.get("/history/results/9999")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()["detail"],
            "태깅 이력을 찾을 수 없습니다.",
        )


if __name__ == "__main__":
    unittest.main()
