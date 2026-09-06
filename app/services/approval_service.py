"""현재 태깅 결과 모델을 위한 승인 요청 서비스입니다."""

import asyncio
import dataclasses
import datetime
import hashlib
import io
import logging
import pathlib
import typing

from PIL import Image
import sqlalchemy
from sqlalchemy.ext import asyncio as sqlalchemy_async

from app.core import config
from app.models import sku as sku_models
from app.schemas import approval as approval_schema
from app.services import (
    image_processing_service,
    sku_service,
    sku_text_embedding,
)
from app.services.fused_metadata import build_metadata_text
from app.services.gemini_service import GeminiService
from app.services.image_preprocessing_service import preprocess_for_embedding
from app.services.sku_image_storage import SkuImageStorage

_LOGGER = logging.getLogger(__name__)


class ApprovalNotFoundError(RuntimeError):
    """존재하지 않는 승인 요청을 조회하거나 처리한 경우입니다."""


class AlreadyReviewedError(RuntimeError):
    """이미 승인·반려 처리된 요청을 다시 처리한 경우입니다."""


@dataclasses.dataclass(frozen=True)
class _ApprovalReview:
    """승인·반려에서 갱신하는 상태 전이 값입니다."""

    approval_status: approval_schema.ApprovalStatus
    reject_reason: str | None


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
           object_data.metadata ->> 'category' AS category,
           sc.sku_code,
           sc.product_name,
           tr.similarity_score
      FROM approval a
      JOIN tagging_result tr ON tr.result_id = a.tagging_result_id
      JOIN scene_image si ON si.scene_image_id = a.scene_image_id
      JOIN sku_catalog sc ON sc.sku_id = tr.sku_id
      LEFT JOIN app_user ru ON ru.user_id = a.requested_by
      LEFT JOIN app_user vu ON vu.user_id = a.reviewed_by
      LEFT JOIN LATERAL (
          SELECT item.metadata
            FROM jsonb_array_elements(si.object_metadata) AS item(metadata)
           WHERE item.metadata ->> 'object_idx' = tr.object_idx::text
           LIMIT 1
      ) object_data ON TRUE
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
           object_data.metadata AS object_metadata,
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
      LEFT JOIN LATERAL (
          SELECT item.metadata
            FROM jsonb_array_elements(si.object_metadata) AS item(metadata)
           WHERE item.metadata ->> 'object_idx' = tr.object_idx::text
           LIMIT 1
      ) object_data ON TRUE
     WHERE a.request_id = :request_id
    """)

_SELECT_FOR_UPDATE = sqlalchemy.text("""
    SELECT a.request_id,
           a.status,
           a.tagging_result_id,
           si.image_url AS scene_image_url,
           object_data.metadata AS object_metadata,
           sc.sku_id,
           sc.sku_code
      FROM approval a
      JOIN tagging_result tr ON tr.result_id = a.tagging_result_id
      JOIN scene_image si ON si.scene_image_id = a.scene_image_id
      JOIN sku_catalog sc ON sc.sku_id = tr.sku_id
      LEFT JOIN LATERAL (
          SELECT item.metadata
            FROM jsonb_array_elements(si.object_metadata) AS item(metadata)
           WHERE item.metadata ->> 'object_idx' = tr.object_idx::text
           LIMIT 1
      ) object_data ON TRUE
     WHERE a.request_id = :request_id
       FOR UPDATE OF a, tr, si, sc
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

_SELECT_ACTIVE_VLM_MOODS = sqlalchemy.text("""
    SELECT tr.vlm_mood
      FROM tagging_result tr
      JOIN approval a ON a.tagging_result_id = tr.result_id
     WHERE tr.sku_id = :sku_id
       AND a.status = 'ACTIVE'
       AND tr.vlm_mood IS NOT NULL
    """)


class ApprovalService:
    """태깅 확정 결과를 SKU 스타일링 이미지로 승인·반려합니다."""

    def __init__(
        self,
        session: sqlalchemy_async.AsyncSession,
        settings: config.Settings,
        gemini_service: GeminiService,
    ) -> None:
        """Initialize the approval service."""
        self.session = session
        self.settings = settings
        self.gemini_service = gemini_service
        self.sku_image_storage = SkuImageStorage(settings.sku_image_root)

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
                    object_idx=int(row["object_index"]),
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
        category = object_metadata.get("category")
        sku_image_url = row["sku_image_url"]
        if sku_image_url is not None:
            sku_image_url = self.sku_image_storage.public_url(sku_image_url)
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
                object_idx=int(row["object_index"]),
                category=category,
                bbox=approval_schema.BoundingBox(**bbox),
            ),
            sku=approval_schema.ApprovalSku(
                sku_id=int(row["sku_id"]),
                sku_code=str(row["sku_code"]),
                product_name=str(row["product_name"]),
                image_url=sku_image_url,
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
        crop = await asyncio.to_thread(self._crop_object, row)
        image_url = sku_service.save_uploaded_image(
            self.settings,
            str(row["sku_code"]),
            f"approved-{row['request_id']}.jpg",
            crop.image_bytes,
        )
        embedding = await asyncio.to_thread(
            self.gemini_service.embed_image, crop.image_bytes
        )
        image_result = await self.session.execute(
            _INSERT_SKU_IMAGE,
            {
                "sku_id": row["sku_id"],
                "image_url": image_url,
                "embedding": embedding,
            },
        )
        sku_image_id = image_result.scalar_one_or_none()
        await self._review(
            request_id=request_id,
            reviewer_id=reviewer_id,
            review=_ApprovalReview(
                approval_status="ACTIVE",
                reject_reason=None,
            ),
        )
        if sku_image_id is not None:
            await self._index_styling_sku_image(int(sku_image_id))
        await self._reindex_sku_text_embedding(int(row["sku_id"]))
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

    async def _index_styling_sku_image(self, sku_image_id: int) -> None:
        """승인된 스타일링 이미지를 융합 임베딩으로 즉시 색인합니다."""
        try:
            sku_image = await self.session.get(
                sku_models.SkuImage,
                sku_image_id,
            )
            if sku_image is None:
                raise RuntimeError(
                    "승인된 스타일링 SKU 이미지를 찾을 수 없습니다."
                )
            sku = await self.session.get(
                sku_models.SkuCatalog, sku_image.sku_id
            )
            if sku is None:
                raise RuntimeError("스타일링 이미지의 SKU를 찾을 수 없습니다.")
            image_bytes = image_processing_service.read_sku_image_bytes(
                sku_image.image_url,
                self.settings.sku_image_root,
                self.settings.image_storage_root,
            )
            if image_bytes is None:
                raise RuntimeError("스타일링 SKU 이미지를 읽을 수 없습니다.")
            image = await asyncio.to_thread(
                image_processing_service.decode_image,
                image_bytes,
            )
            processed = (
                await asyncio.to_thread(
                    preprocess_for_embedding,
                    image,
                    self.settings,
                )
            ).image
            metadata_text = build_metadata_text(
                category=sku.category,
                sub_category=sku.sub_category,
                product_name=sku.product_name,
                brand=sku.brand,
                price=sku.price,
                attributes=sku.attributes,
            )
            embedding = await asyncio.to_thread(
                self.gemini_service.embed_fused,
                processed,
                metadata_text,
            )
            sku_image.embedding = embedding
            sku_image.embedding_pipeline_version = (
                self.settings.embedding_pipeline_version
            )
            sku_image.embedding_image_sha256 = _image_sha256(processed)
            sku_image.indexed_at = sqlalchemy.func.now()
            await self.session.commit()
        except (
            Exception
        ):  # noqa: BLE001 - 승인 상태를 보존하고 배치 재색인을 허용한다
            await self.session.rollback()

    async def _reindex_sku_text_embedding(self, sku_id: int) -> None:
        """승인 누적 공간 분위기·스타일 태그를 반영해 텍스트 임베딩을 다시 만듭니다.

        이번 승인 건 하나만이 아니라, 같은 SKU에 대해 지금까지 ACTIVE로
        승인된 모든 tagging_result.vlm_mood를 다시 모아 텍스트를
        조립한다. 같은 SKU가 여러 연출 이미지에서 반복 승인되어도 값이
        누적되고 중복 태그는 제거된다(sku_text_embedding.append_mood_lines).
        별도 컬럼에 결과를 저장하지 않고 매번 다시 계산하므로, 이 SKU의
        text_embedding만 갱신되고 다른 SKU는 영향을 받지 않는다.

        Gemini 호출 실패 등으로 재생성이 실패해도 이미 커밋된 승인
        처리는 되돌리지 않는다. 실패한 SKU는 text_embedding이 이전
        상태로 남으며, scripts/embedding/build_embeddings.py
        --force-text로 다시 색인할 수 있다.

        Args:
            sku_id: 텍스트 임베딩을 재생성할 SKU입니다.
        """
        try:
            sku = await self.session.get(sku_models.SkuCatalog, sku_id)
            if sku is None:
                raise RuntimeError(
                    f"승인된 SKU를 찾을 수 없습니다: sku_id={sku_id}"
                )
            moods_result = await self.session.execute(
                _SELECT_ACTIVE_VLM_MOODS, {"sku_id": sku_id}
            )
            vlm_moods = [row[0] for row in moods_result.all()]
            summaries, tags = sku_text_embedding.collect_active_moods(vlm_moods)
            deduped_summaries = sku_text_embedding.dedupe_preserve_order(
                summaries
            )
            deduped_tags = sku_text_embedding.dedupe_preserve_order(tags)
            base_text = sku_text_embedding.build_sku_base_text(
                product_name=sku.product_name,
                category=sku.category,
                sub_category=sku.sub_category,
                attributes=sku.attributes,
                key_features=sku.key_features,
            )
            text = sku_text_embedding.append_mood_lines(
                base_text,
                mood_summaries=deduped_summaries,
                style_tags=deduped_tags,
            )
            embedding = await asyncio.to_thread(
                self.gemini_service.embed_text, text
            )
            sku.text_embedding = embedding
            await self.session.commit()
            _LOGGER.info(
                "승인 SKU 텍스트 임베딩 재생성 완료: sku_id=%s, "
                "space_moods=%s, style_tags=%s",
                sku_id,
                deduped_summaries,
                deduped_tags,
            )
        except (
            Exception
        ):  # noqa: BLE001 - 승인 상태를 보존하고 배치 재색인을 허용한다
            await self.session.rollback()
            _LOGGER.exception(
                "승인 SKU 텍스트 임베딩 재생성 실패: sku_id=%s", sku_id
            )

    async def reject(
        self,
        request_id: int,
        reject_reason: str,
        reviewer_id: int,
        reviewer_name: str,
    ) -> approval_schema.RejectResponse:
        """승인 요청을 반려 상태로 전환합니다."""
        row = await self._get_pending_for_update(request_id)
        await self._review(
            request_id=request_id,
            reviewer_id=reviewer_id,
            review=_ApprovalReview(
                approval_status="REJECTED",
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
        await self.session.commit()

    def _crop_object(
        self, row: sqlalchemy.RowMapping
    ) -> image_processing_service.CroppedObject:
        """승인 대상 객체를 연출 이미지 태깅 파이프라인과 동일하게 크롭합니다.

        ``tagging_service``가 추천 단계에서 쓰는
        ``image_processing_service.crop_scene_objects``를 그대로
        재사용합니다. 승인 시 저장하는 임베딩이 연출 이미지 크롭
        임베딩과 같은 좌표계·인코딩으로 만들어져야 유사도 비교가
        유효하기 때문입니다.
        """
        object_metadata = _as_object_metadata(row["object_metadata"])
        if not isinstance(object_metadata.get("bbox_coord"), dict):
            raise ValueError("승인 대상 객체의 바운딩 박스가 없습니다.")
        source_path = pathlib.Path(self.settings.image_storage_root) / str(
            row["scene_image_url"]
        ).removeprefix("/uploads/")
        return image_processing_service.crop_scene_objects(
            source_path, [object_metadata]
        )[0]


def _as_object_metadata(value: object) -> dict[str, typing.Any]:
    """Psycopg JSONB 결과를 안전한 객체 메타데이터로 변환합니다."""
    return value if isinstance(value, dict) else {}


def _image_sha256(image: Image.Image) -> str:
    """전처리 이미지의 고정 PNG 표현을 재색인 식별자로 해시합니다."""
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG", optimize=False)
    return hashlib.sha256(buffer.getvalue()).hexdigest()
