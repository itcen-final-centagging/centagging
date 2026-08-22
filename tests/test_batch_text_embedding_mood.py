"""오프라인 배치의 텍스트 임베딩이 승인 누적 vlm_mood를 반영하는지 검증합니다."""

import unittest.mock

from scripts.embedding import build_embeddings


def test_embed_texts_appends_active_moods_and_dedupes_tags() -> None:
    """승인된 vlm_mood의 분위기·태그를 합쳐 임베딩 텍스트에 반영한다."""
    settings = object()
    result = build_embeddings.RunResult()
    conn = unittest.mock.Mock()
    embed_text = unittest.mock.Mock(return_value=[0.1, 0.2])

    with (
        unittest.mock.patch.object(
            build_embeddings.db,
            "fetch_text_embedded_sku_ids",
            return_value=set(),
        ),
        unittest.mock.patch.object(
            build_embeddings.db,
            "fetch_active_vlm_moods_by_sku_id",
            return_value={
                1: [
                    {
                        "summary": "따뜻한 우드톤 거실",
                        "tags": ["우드", "내추럴"],
                    },
                    {
                        "summary": "따뜻한 우드톤 거실",
                        "tags": ["우드", "미니멀"],
                    },
                ]
            },
        ),
        unittest.mock.patch.object(
            build_embeddings.gemini_embed, "embed_text", embed_text
        ),
        unittest.mock.patch.object(
            build_embeddings.db, "update_text_embedding"
        ) as update_text_embedding,
    ):
        build_embeddings.embed_texts(
            conn,
            [
                {
                    "sku_id": 1,
                    "product_name": "메쉬 사무용 의자",
                    "category": "의자",
                    "sub_category": "학생·사무용의자",
                    "attributes": {},
                    "key_features": [],
                }
            ],
            settings,
            result,
            dry_run=False,
            force=False,
        )

    assert result.text_embedded == 1
    assert not result.text_failed
    assert embed_text.call_args.args[1] == "\n".join(
        [
            "메쉬 사무용 의자",
            "카테고리: 의자 > 학생·사무용의자",
            "공간 분위기: 따뜻한 우드톤 거실",
            "스타일 태그: 우드, 내추럴, 미니멀",
        ]
    )
    update_text_embedding.assert_called_once_with(conn, 1, [0.1, 0.2])


def test_embed_texts_uses_base_text_when_sku_has_no_active_approval() -> None:
    """승인된 vlm_mood가 없는 SKU는 기존 텍스트만으로 임베딩한다."""
    settings = object()
    result = build_embeddings.RunResult()
    conn = unittest.mock.Mock()
    embed_text = unittest.mock.Mock(return_value=[0.0])

    with (
        unittest.mock.patch.object(
            build_embeddings.db,
            "fetch_text_embedded_sku_ids",
            return_value=set(),
        ),
        unittest.mock.patch.object(
            build_embeddings.db,
            "fetch_active_vlm_moods_by_sku_id",
            return_value={},
        ),
        unittest.mock.patch.object(
            build_embeddings.gemini_embed, "embed_text", embed_text
        ),
        unittest.mock.patch.object(
            build_embeddings.db, "update_text_embedding"
        ),
    ):
        build_embeddings.embed_texts(
            conn,
            [
                {
                    "sku_id": 2,
                    "product_name": "원목 식탁",
                    "category": "테이블",
                    "attributes": {},
                    "key_features": [],
                }
            ],
            settings,
            result,
            dry_run=False,
            force=False,
        )

    assert embed_text.call_args.args[1] == "\n".join(
        ["원목 식탁", "카테고리: 테이블"]
    )
