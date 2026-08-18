"""현재 태깅 결과 모델을 위한 승인 요청 서비스입니다."""

import dataclasses
import datetime
import pathlib
import typing

import sqlalchemy
from sqlalchemy.ext import asyncio as sqlalchemy_async

from app.core import config
from app.schemas import approval as approval_schema
from app.services import image_processing_service, sku_service


class ApprovalNotFoundError(RuntimeError):
    """존재하지 않는 승인 요청을 조회하거나 처리한 경우입니다."""


class AlreadyReviewedError(RuntimeError):
    """이미 승인·반려 처리된 요청을 다시 처리한 경우입니다."""


@dataclasses.dataclass(frozen=True)
class _ApprovalReview:
    """승인·반려에서 함께 갱신하는 상태 전이 값입니다."""

    approval_status: approval_schema.ApprovalStatus
    reject_reason: str | None
    tagging_status: typing.Literal["ACTIVE", "DEACTIVE"]


_SELECT_LIST = sqlalchemy.text("""
    SELECT a.request_id,
           a.status,
           a.requested_at,
           a.reviewed_at,
           a.scene_image_id,
           a.object_index,
           si.origin_name,
           ru.user_name AS requested_by_name,
           vu.user_name AS reviewed_by_name,
           si.object_metadata -> tr.object_index -> 'attribute' ->> 'label'
               AS category,
           sc.sku_code,
           sc.product_name,
           tr.similarity_score
      FROM approval a
      JOIN tagging_result tr ON tr.result_id = a.tagging_result_id
      JOIN scene_image si ON si.scene_image_id = a.scene_image_id
      JOIN sku_catalog sc ON sc.sku_id = tr.sku_id
      LEFT JOIN app_user ru ON ru.user_id = a.requested_by
      LEFT JOIN app_user vu ON vu.user_id = a.reviewed_by
     WHERE (:status = 'ALL' OR a.status = :status)
     ORDER BY a.requested_at DESC
    """)

_SELECT_DETAIL = sqlalchemy.text("""
    SELECT a.request_id,
           a.status,
           a.requested_at,
           a.reviewed_at,
           a.reject_reason,
           a.scene_image_id,
           a.object_index,
           ru.user_name AS requested_by_name,
           vu.user_name AS reviewed_by_name,
           si.image_url AS scene_image_url,
           si.origin_name,
           si.object_metadata -> tr.object_index AS object_metadata,
           tr.similarity_score,
           tr.xai_result,
           sc.sku_id,
           sc.sku_code,
           sc.product_name,
           simg.image_url AS sku_image_url
      FROM approval a
      JOIN tagging_result tr ON tr.result_id = a.tagging_result_id
      JOIN scene_image si ON si.scene_image_id = a.scene_image_id
      JOIN sku_catalog sc ON sc.sku_id = tr.sku_id
      LEFT JOIN sku_image simg ON simg.sku_image_id = tr.sku_image_id
      LEFT JOIN app_user ru ON ru.user_id = a.requested_by
      LEFT JOIN app_user vu ON vu.user_id = a.reviewed_by
     WHERE a.request_id = :request_id
    """)

_SELECT_FOR_UPDATE = sqlalchemy.text("""
    SELECT a.request_id,
           a.status,
           a.tagging_result_id,
           si.image_url AS scene_image_url,
           si.object_metadata -> tr.object_index AS object_metadata,
           sc.sku_id,
           sc.sku_code
      FROM approval a
      JOIN tagging_result tr ON tr.result_id = a.tagging_result_id
      JOIN scene_image si ON si.scene_image_id = a.scene_image_id
      JOIN sku_catalog sc ON sc.sku_id = tr.sku_id
     WHERE a.request_id = :request_id
       FOR UPDATE
    """)

_INSERT_SKU_IMAGE = sqlalchemy.text("""
    INSERT INTO sku_image (sku_id, image_url, image_type)
    VALUES (:sku_id, :image_url, 'STYLING')
    ON CONFLICT (sku_id, image_url) DO NOTHING
    RETURNING sku_image_id
    """)

_UPDATE_APPROVAL = sqlalchemy.text("""
    UPDATE approval
       SET status = :status,
           reviewed_by = :reviewer_id,
           reviewed_at = now(),
           reject_reason = :reject_reason
     WHERE request_id = :request_id
       AND status = 'PENDING'
    RETURNING request_id
    """)

_UPDATE_TAGGING_RESULT = sqlalchemy.text("""
    UPDATE tagging_result
       SET status = :status
     WHERE result_id = :tagging_result_id
    """)


class ApprovalService:
    """태깅 확정 결과를 SKU 스타일링 이미지로 승인·반려합니다."""

    def __init__(
        self,
        session: sqlalchemy_async.AsyncSession,
        settings: config.Settings,
    ) -> None:
        """Initialize the approval service."""
        self.session = session
        self.settings = settings

    async def list_approvals(
        self, status: str
    ) -> approval_schema.ApprovalListResponse:
        """상태에 맞는 태깅 결과 승인 요청을 최신순으로 반환합니다."""
        rows = (
            (await self.session.execute(_SELECT_LIST, {"status": status}))
            .mappings()
            .all()
        )
        return approval_schema.ApprovalListResponse(
            items=[
                approval_schema.ApprovalListItem(
                    request_id=int(row["request_id"]),
                    status=typing.cast(
                        approval_schema.ApprovalStatus,
                        row["status"],
                    ),
                    requested_at=row["requested_at"],
                    requested_by_name=row["requested_by_name"],
                    reviewed_at=row["reviewed_at"],
                    reviewed_by_name=row["reviewed_by_name"],
                    scene_image_id=int(row["scene_image_id"]),
                    origin_name=str(row["origin_name"]),
                    object_index=int(row["object_index"]),
                    category=row["category"],
                    sku_code=str(row["sku_code"]),
                    product_name=str(row["product_name"]),
                    similarity_score=(
                        float(row["similarity_score"])
                        if row["similarity_score"] is not None
                        else None
                    ),
                )
                for row in rows
            ]
        )

    async def get_detail(
        self, request_id: int
    ) -> approval_schema.ApprovalDetailResponse:
        """원본 이미지, 객체 바운딩 박스, SKU를 포함한 요청 상세를 반환합니다."""
        row = (
            (
                await self.session.execute(
                    _SELECT_DETAIL, {"request_id": request_id}
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise ApprovalNotFoundError(request_id)
        object_metadata = _as_object_metadata(row["object_metadata"])
        bbox = object_metadata.get("bbox_coord", {})
        attribute = object_metadata.get("attribute", {})
        return approval_schema.ApprovalDetailResponse(
            request_id=int(row["request_id"]),
            status=typing.cast(approval_schema.ApprovalStatus, row["status"]),
            requested_by_name=row["requested_by_name"],
            requested_at=row["requested_at"],
            reviewed_by_name=row["reviewed_by_name"],
            reviewed_at=row["reviewed_at"],
            reject_reason=row["reject_reason"],
            scene_image=approval_schema.ApprovalSceneImage(
                scene_image_id=int(row["scene_image_id"]),
                image_url=str(row["scene_image_url"]),
                origin_name=str(row["origin_name"]),
            ),
            object=approval_schema.ApprovalObject(
                object_index=int(row["object_index"]),
                category=attribute.get("label"),
                bbox=approval_schema.BoundingBox(**bbox),
            ),
            sku=approval_schema.ApprovalSku(
                sku_id=int(row["sku_id"]),
                sku_code=str(row["sku_code"]),
                product_name=str(row["product_name"]),
                image_url=row["sku_image_url"],
            ),
            similarity_score=(
                float(row["similarity_score"])
                if row["similarity_score"] is not None
                else None
            ),
            xai_result=row["xai_result"],
            actions=approval_schema.ApprovalActions(
                can_confirm=row["status"] == "PENDING",
                can_reject=row["status"] == "PENDING",
            ),
        )

    async def confirm(
        self,
        request_id: int,
        reviewer_id: int,
        reviewer_name: str,
    ) -> approval_schema.ConfirmResponse:
        """승인 대상 객체를 크롭해 SKU 스타일링 이미지로 등록합니다."""
        row = await self._get_pending_for_update(request_id)
        image_url = self._save_crop(row)
        image_result = await self.session.execute(
            _INSERT_SKU_IMAGE,
            {"image_url": image_url, "sku_id": row["sku_id"]},
        )
        sku_image_id = image_result.scalar_one_or_none()
        await self._review(
            request_id=request_id,
            reviewer_id=reviewer_id,
            tagging_result_id=int(row["tagging_result_id"]),
            review=_ApprovalReview(
                approval_status="ACTIVE",
                tagging_status="ACTIVE",
                reject_reason=None,
            ),
        )
        return approval_schema.ConfirmResponse(
            request_id=request_id,
            reviewed_by_name=reviewer_name,
            reviewed_at=datetime.datetime.now(datetime.timezone.utc),
            created_sku_image=(
                approval_schema.ConfirmCreatedSkuImage(
                    sku_image_id=int(sku_image_id),
                    image_url=image_url,
                    skipped=False,
                )
                if sku_image_id is not None
                else None
            ),
        )

    async def reject(
        self,
        request_id: int,
        reject_reason: str,
        reviewer_id: int,
        reviewer_name: str,
    ) -> approval_schema.RejectResponse:
        """승인 요청을 반려하고 태깅 결과를 비활성 상태로 전환합니다."""
        row = await self._get_pending_for_update(request_id)
        await self._review(
            request_id=request_id,
            reviewer_id=reviewer_id,
            tagging_result_id=int(row["tagging_result_id"]),
            review=_ApprovalReview(
                approval_status="REJECTED",
                tagging_status="DEACTIVE",
                reject_reason=reject_reason.strip(),
            ),
        )
        return approval_schema.RejectResponse(
            request_id=request_id,
            reviewed_by_name=reviewer_name,
            reviewed_at=datetime.datetime.now(datetime.timezone.utc),
            reject_reason=reject_reason.strip(),
        )

    async def _get_pending_for_update(
        self, request_id: int
    ) -> sqlalchemy.RowMapping:
        row = (
            (
                await self.session.execute(
                    _SELECT_FOR_UPDATE, {"request_id": request_id}
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise ApprovalNotFoundError(request_id)
        if row["status"] != "PENDING":
            raise AlreadyReviewedError(request_id)
        return row

    async def _review(
        self,
        *,
        request_id: int,
        reviewer_id: int,
        tagging_result_id: int,
        review: _ApprovalReview,
    ) -> None:
        updated = await self.session.execute(
            _UPDATE_APPROVAL,
            {
                "reject_reason": review.reject_reason,
                "request_id": request_id,
                "reviewer_id": reviewer_id,
                "status": review.approval_status,
            },
        )
        if updated.scalar_one_or_none() is None:
            await self.session.rollback()
            raise AlreadyReviewedError(request_id)
        await self.session.execute(
            _UPDATE_TAGGING_RESULT,
            {
                "status": review.tagging_status,
                "tagging_result_id": tagging_result_id,
            },
        )
        await self.session.commit()

    def _save_crop(self, row: sqlalchemy.RowMapping) -> str:
        object_metadata = _as_object_metadata(row["object_metadata"])
        bbox = object_metadata.get("bbox_coord")
        if not isinstance(bbox, dict):
            raise ValueError("승인 대상 객체의 바운딩 박스가 없습니다.")
        source_path = pathlib.Path(self.settings.image_storage_root) / str(
            row["scene_image_url"]
        ).removeprefix("/uploads/")
        scene_image = image_processing_service.decode_image(
            source_path.read_bytes()
        )
        crop = image_processing_service.get_crop_image(scene_image, bbox)
        return sku_service.save_uploaded_image(
            self.settings,
            str(row["sku_code"]),
            f"approved-{row['request_id']}.jpg",
            image_processing_service.parse_image_to_bytes(crop),
        )


def _as_object_metadata(value: object) -> dict[str, typing.Any]:
    """Psycopg JSONB 결과를 안전한 객체 메타데이터로 변환합니다."""
    return value if isinstance(value, dict) else {}
