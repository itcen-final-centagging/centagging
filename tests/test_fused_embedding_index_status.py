"""융합 SKU 이미지 색인 상태 점검 테스트입니다."""

import sys
import types
import unittest.mock

from scripts.embedding import build_embeddings, db


class _Cursor:
    """집계 SQL과 인자를 기록하는 커서 대역입니다."""

    def __init__(self) -> None:
        self.query = ""
        self.params: object | None = None

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, query: str, params: object) -> None:
        self.query = query
        self.params = params

    def fetchone(self) -> tuple[int, int, int]:
        return (12, 9, 3)


class _Connection:
    """동일 커서를 반환하는 연결 대역입니다."""

    def __init__(self) -> None:
        self.cursor_value = _Cursor()

    def cursor(self) -> _Cursor:
        return self.cursor_value


def test_index_status_counts_current_and_pending_images() -> None:
    """현재 버전·해시가 없는 이미지는 재색인 대상으로 집계한다."""
    connection = _Connection()

    status = db.fetch_image_embedding_index_status(
        connection,  # type: ignore[arg-type]
        "2026-08-21.1",
    )

    assert status == db.ImageEmbeddingIndexStatus(
        total=12, current=9, pending=3
    )
    assert "embedding_pipeline_version" in connection.cursor_value.query
    assert "embedding_image_sha256" in connection.cursor_value.query
    assert connection.cursor_value.params == ("2026-08-21.1", "2026-08-21.1")


def test_check_image_index_does_not_start_updates() -> None:
    """점검 명령은 Gemini 호출·카탈로그 적재 없이 미완료 상태를 알린다."""
    connection = unittest.mock.Mock()
    settings = types.SimpleNamespace(
        database=types.SimpleNamespace(),
        embedding_pipeline_version="2026-08-21.1",
    )

    with (
        unittest.mock.patch.object(
            sys,
            "argv",
            ["build_embeddings", "--check-image-index"],
        ),
        unittest.mock.patch.object(
            build_embeddings.storage,
            "get_settings",
            return_value=settings,
        ),
        unittest.mock.patch.object(
            build_embeddings.db,
            "connect",
            return_value=connection,
        ),
        unittest.mock.patch.object(
            build_embeddings.db,
            "fetch_image_embedding_index_status",
            return_value=db.ImageEmbeddingIndexStatus(12, 9, 3),
        ),
        unittest.mock.patch.object(build_embeddings, "load_skus") as load_skus,
    ):
        try:
            build_embeddings.main()
        except SystemExit as error:
            assert error.code == 1
        else:
            raise AssertionError("재색인 대상이 있는데 성공으로 종료했습니다.")

    assert connection.close.call_count == 1
    assert load_skus.call_count == 0
