"""태깅 이력 목록을 데이터베이스에서 조회합니다."""

import sqlalchemy
from sqlalchemy.ext import asyncio as sqlalchemy_async

from app.models.tagging_result import TaggingResult
from app.schemas import history as history_schema
from app.services import sku_image_storage

_SELECT_TAGGING_HISTORY = sqlalchemy.text("""
    SELECT tr.result_id,
           tr.scene_image_id,
           tr.object_idx,
           sc.sku_code,
           sc.product_name,
           COALESCE(object_data.metadata,
                    si.object_metadata -> tr.object_idx)
               ->> 'category' AS object_name,
           tr.similarity_score,
           tr.vlm_mood,
           au.user_name AS created_by,
           tr.created_at,
           si.image_url,
           si.origin_name,
           sku_img.image_url AS sku_image_url,
           COALESCE(object_data.metadata,
                    si.object_metadata -> tr.object_idx)
               -> 'bbox_coord' AS bbox,
           approval_data.status AS approval_status
      FROM tagging_result tr
      JOIN scene_image si
        ON si.scene_image_id = tr.scene_image_id
      JOIN app_user au
        ON au.user_id = tr.created_by
      JOIN sku_catalog sc
        ON sc.sku_id = tr.sku_id
 LEFT JOIN LATERAL (
           SELECT item.metadata
             FROM jsonb_array_elements(si.object_metadata) AS item(metadata)
            WHERE item.metadata ->> 'object_idx' = tr.object_idx::text
            LIMIT 1
       ) object_data ON TRUE
 LEFT JOIN sku_image sku_img
        ON sku_img.sku_image_id = tr.sku_image_id
 LEFT JOIN LATERAL (
           SELECT a.status
             FROM approval a
            WHERE a.tagging_result_id = tr.result_id
            ORDER BY a.requested_at DESC, a.request_id DESC
            LIMIT 1
       ) approval_data ON TRUE
     ORDER BY tr.created_at DESC, tr.result_id DESC
    """)

_SELECT_TAGGING_HISTORY_DETAIL = sqlalchemy.text("""
    SELECT tr.result_id,
           au.user_name AS created_by,
           tr.created_at,
           tr.similarity_score,
           si.image_url AS scene_image_url,
           si.origin_name,
           COALESCE(object_data.metadata,
                    si.object_metadata -> tr.object_idx)
               -> 'bbox_coord' AS bbox,
           COALESCE(object_data.metadata,
                    si.object_metadata -> tr.object_idx)
               ->> 'category' AS object_category,
           COALESCE(object_data.metadata,
                    si.object_metadata -> tr.object_idx)
               ->> 'sub_category' AS object_sub_category,
           COALESCE(object_data.metadata,
                    si.object_metadata -> tr.object_idx)
               -> 'attributes' AS object_attrs,
           sc.sku_code,
           sc.product_name,
           sc.brand,
           sc.price,
           sku_img.image_url AS sku_image_url,
           sc.category,
           sc.sub_category,
           sc.attributes,
           tr.xai_result,
           tr.vlm_mood,
           approval_data.status AS approval_status
      FROM tagging_result tr
      JOIN scene_image si
        ON si.scene_image_id = tr.scene_image_id
      JOIN app_user au
        ON au.user_id = tr.created_by
      JOIN sku_catalog sc
        ON sc.sku_id = tr.sku_id
 LEFT JOIN LATERAL (
           SELECT item.metadata
             FROM jsonb_array_elements(si.object_metadata) AS item(metadata)
            WHERE item.metadata ->> 'object_idx' = tr.object_idx::text
            LIMIT 1
       ) object_data ON TRUE
 LEFT JOIN sku_image sku_img
        ON sku_img.sku_image_id = tr.sku_image_id
 LEFT JOIN LATERAL (
           SELECT a.status
             FROM approval a
            WHERE a.tagging_result_id = tr.result_id
            ORDER BY a.requested_at DESC, a.request_id DESC
            LIMIT 1
       ) approval_data ON TRUE
     WHERE tr.result_id = :result_id
    """)


async def list_tagging_history(
    session: sqlalchemy_async.AsyncSession,
    image_storage: sku_image_storage.SkuImageStorage,
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
        vlm_mood = row["vlm_mood"] or {}
        items.append(
            history_schema.TaggingHistoryListItem.model_validate(
                {
                    "result_id": row["result_id"],
                    "scene_image_id": row["scene_image_id"],
                    "object_idx": row["object_idx"],
                    "sku_code": row["sku_code"],
                    "product_name": row["product_name"],
                    "object_name": row["object_name"],
                    "similarity_score": (
                        round(float(score) * 100) if score is not None else None
                    ),
                    "created_by": row["created_by"],
                    "created_at": row["created_at"],
                    "approval_status": row["approval_status"],
                    "style_tags": vlm_mood.get("tags", []),
                    "sku_image_url": (
                        image_storage.public_url(row["sku_image_url"])
                        if row["sku_image_url"] is not None
                        else None
                    ),
                    "scene_image": {
                        "image_url": row["image_url"],
                        "origin_name": row["origin_name"],
                        "bbox": row["bbox"],
                    },
                }
            )
        )

    return items


async def get_tagging_history_detail(
    session: sqlalchemy_async.AsyncSession,
    result_id: int,
    image_storage: sku_image_storage.SkuImageStorage,
) -> history_schema.TaggingHistoryDetail | None:
    """결과 ID에 해당하는 태깅 이력 상세를 조회합니다.

    Args:
        session: 요청 범위의 비동기 DB 세션입니다.
        result_id: 조회할 태깅 결과 ID입니다.
        image_storage: SKU 이미지 공개 URL 변환기입니다.

    Returns:
        태깅 이력 상세이며, 결과가 없으면 None입니다.
    """
    result = await session.execute(
        _SELECT_TAGGING_HISTORY_DETAIL,
        {"result_id": result_id},
    )
    row = result.mappings().one_or_none()
    if row is None:
        return None

    score = row["similarity_score"]
    return history_schema.TaggingHistoryDetail.model_validate(
        {
            "result_id": row["result_id"],
            "created_by": row["created_by"],
            "created_at": row["created_at"],
            "similarity_score": (
                round(float(score) * 100) if score is not None else None
            ),
            "approval_status": row["approval_status"],
            "scene_image": {
                "image_url": row["scene_image_url"],
                "origin_name": row["origin_name"],
            },
            "detected_object": {
                "category": row["object_category"],
                "sub_category": row["object_sub_category"],
                "attrs": row["object_attrs"] or {},
                "bbox": row["bbox"],
                "vlm_mood": row["vlm_mood"],
            },
            "matched_sku": {
                "sku_code": row["sku_code"],
                "product_name": row["product_name"],
                "brand": row["brand"],
                "price": row["price"],
                "image_url": (
                    image_storage.public_url(row["sku_image_url"])
                    if row["sku_image_url"] is not None
                    else None
                ),
                "category": row["category"],
                "sub_category": row["sub_category"],
                "attrs": row["attributes"],
            },
            "xai_result": row["xai_result"],
        }
    )


async def add_tagging_results(
    session: sqlalchemy_async.AsyncSession,
    tagging_results: list[TaggingResult],
) -> list[int]:
    """태깅 결과 엔티티를 세션에 추가하고 ID를 반환합니다.

    Args:
        session: 요청 범위의 비동기 SQLAlchemy 세션입니다.
        tagging_results: 저장할 태깅 결과 엔티티 목록입니다.

    Returns:
        저장된 태깅 결과의 result_id 목록입니다.
    """
    session.add_all(tagging_results)
    await session.flush()

    return [r.result_id for r in tagging_results]
