"""SKU 카탈로그 융합 임베딩 재색인 테스트입니다."""

import pathlib
import tempfile
import types
import unittest.mock

from PIL import Image

from scripts.embedding import build_embeddings, db, storage


def test_catalog_metadata_uses_shared_fused_metadata_contract() -> None:
    """SKU 색인은 검색 객체와 같은 메타데이터 조립 규칙을 쓴다."""
    metadata = build_embeddings._build_sku_metadata_text(
        {
            "product_name": "메쉬 사무용 의자",
            "category": "의자",
            "sub_category": "학생·사무용의자",
            "brand": "다니카",
            "price": 47900,
            "attributes": {"has_wheels": "있음", "color": "블랙"},
        }
    )

    assert metadata == "\n".join(
        [
            "상품명: 메쉬 사무용 의자",
            "카테고리: 의자",
            "소분류: 학생·사무용의자",
            "브랜드: 다니카",
            "가격: 47900",
            "color: 블랙",
            "has_wheels: 있음",
        ]
    )


def test_embedding_image_sha256_uses_processed_rgb_pixels() -> None:
    """같은 보정 RGB 입력은 항상 같은 재색인 해시를 만든다."""
    image = Image.new("RGB", (2, 1), color=(20, 30, 40))

    assert build_embeddings._embedding_image_sha256(image) == (
        build_embeddings._embedding_image_sha256(image.copy())
    )


def test_embed_images_stores_fused_embedding_with_tracking_metadata() -> None:
    """카탈로그 이미지는 보정·메타 결합 벡터와 추적 정보를 함께 저장한다."""
    with tempfile.TemporaryDirectory() as directory:
        project_root = pathlib.Path(directory)
        image_path = project_root / "images" / "1_CHAIR_BLACK_m_001.jpg"
        image_path.parent.mkdir()
        Image.new("RGB", (2, 2), color=(10, 20, 30)).save(image_path)
        incoming_image = storage.IncomingImage(
            path=image_path,
            goods_id="1",
            sku_code="CHAIR",
            color="BLACK",
            image_type="MAIN",
            sequence="001",
        )
        embedder = unittest.mock.Mock()
        embedder.embed_fused.return_value = [0.1, 0.2]
        upsert = unittest.mock.Mock(return_value=True)
        settings = types.SimpleNamespace(embedding_pipeline_version="test-v1")
        result = build_embeddings.RunResult()
        conn = unittest.mock.Mock()

        with (
            unittest.mock.patch.object(
                storage, "PROJECT_ROOT", project_root
            ),
            unittest.mock.patch.object(
                storage, "list_incoming_images", return_value=[incoming_image]
            ),
            unittest.mock.patch.object(
                build_embeddings.db,
                "fetch_sku_ids_by_code",
                return_value={"CHAIR": 1},
            ),
            unittest.mock.patch.object(
                build_embeddings.db,
                "fetch_image_embedding_states",
                return_value={},
            ),
            unittest.mock.patch.object(
                build_embeddings.gemini_embed,
                "make_image_embedder",
                return_value=embedder,
            ),
            unittest.mock.patch.object(
                build_embeddings,
                "preprocess_for_embedding",
                side_effect=lambda image, _: types.SimpleNamespace(
                    image=image.copy()
                ),
            ),
            unittest.mock.patch.object(
                build_embeddings.db, "upsert_sku_image", upsert
            ),
        ):
            build_embeddings.embed_images(
                conn,
                settings,
                [
                    {
                        "sku_code": "CHAIR",
                        "product_name": "메쉬 사무용 의자",
                        "category": "의자",
                        "sub_category": "학생·사무용의자",
                        "attributes": {"color": "블랙"},
                    }
                ],
                result,
                dry_run=False,
                force=False,
            )

    assert result.image_embedded == 1
    assert conn.commit.call_count == 1
    assert embedder.embed_fused.call_args.args[1] == "\n".join(
        [
            "상품명: 메쉬 사무용 의자",
            "카테고리: 의자",
            "소분류: 학생·사무용의자",
            "color: 블랙",
        ]
    )
    assert upsert.call_args.kwargs["pipeline_version"] == "test-v1"
    assert len(upsert.call_args.kwargs["image_sha256"]) == 64


def test_upsert_sku_image_replaces_existing_embedding_with_current_pipeline() -> None:
    """파이프라인 또는 이미지 해시가 바뀐 기존 벡터는 갱신한다."""

    class Cursor:
        """DB 저장 호출만 기록하는 최소 커서입니다."""

        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, query: str, params: object) -> None:
            self.calls.append((query, params))

        def fetchone(self) -> tuple[int, list[float]]:
            return (10, [0.0])

    class Connection:
        """동일 커서를 반환하는 최소 연결입니다."""

        def __init__(self) -> None:
            self.cursor_value = Cursor()

        def cursor(self) -> Cursor:
            return self.cursor_value

    connection = Connection()
    db.upsert_sku_image(
        connection, 1, "data/images/chair.jpg", "MAIN", [0.1], "test-v1", "a" * 64
    )

    update_query, update_params = connection.cursor_value.calls[1]
    assert "UPDATE sku_image" in update_query
    assert "embedding_pipeline_version" in update_query
    assert update_params[3:5] == ("test-v1", "a" * 64)
