"""태깅 이력 목록을 데이터베이스에서 조회합니다."""

import sqlalchemy
from sqlalchemy.ext import asyncio as sqlalchemy_async

from app.schemas import history as history_schema

_SELECT_TAGGING_HISTORY = sqlalchemy.text("""
    SELECT tr.result_id,
           sc.sku_code,
           sc.product_name,
           sc.category AS object_name,
           tr.similarity_score,
           au.user_name AS created_by,
           tr.created_at,
           si.image_url,
           si.origin_name,
           si.bbox_coord -> tr.object_index AS bbox
      FROM tagging_result tr
      JOIN scene_image si
        ON si.scene_image_id = tr.scene_image_id
      JOIN app_user au
        ON au.user_id = tr.created_by
      JOIN sku_catalog sc
        ON sc.sku_id = tr.sku_id
     ORDER BY tr.created_at DESC, tr.result_id DESC
    """)


async def list_tagging_history(
    session: sqlalchemy_async.AsyncSession,
) -> list[history_schema.TaggingHistoryListItem]:
    """저장된 태깅 결과를 최신순으로 조회합니다.

    Args:
        session: 요청 범위의 비동기 DB 세션입니다.

    Returns:
        검수 이력 화면에 표시할 태깅 결과 목록입니다.
    """
    result = await session.execute(_SELECT_TAGGING_HISTORY)
    items = []

    for row in result.mappings().all():
        score = row["similarity_score"]
        items.append(
            history_schema.TaggingHistoryListItem.model_validate(
                {
                    "result_id": row["result_id"],
                    "sku_code": row["sku_code"],
                    "product_name": row["product_name"],
                    "object_name": row["object_name"],
                    "similarity_score": (
                        round(float(score) * 100) if score is not None else None
                    ),
                    "created_by": row["created_by"],
                    "created_at": row["created_at"],
                    "style_tags": [],
                    "scene_image": {
                        "image_url": row["image_url"],
                        "origin_name": row["origin_name"],
                        "bbox": row["bbox"],
                    },
                }
            )
        )

    return items
