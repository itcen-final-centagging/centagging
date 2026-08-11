"""승인 요청(객체-SKU 매칭 검수) 서비스입니다.

테이블은 ``docker/db/init/schema.sql``의 ``approval``이며, 이 모듈은
다른 테이블(``scene_image``, ``detected_object``, ``tagging_result``)과
같은 방식으로 raw SQL(``sqlalchemy.text``)로 접근합니다.

승인 요청은 ``tagging_result``와 마찬가지로 탐지 객체(object) 단위이며,
한 요청 = 객체-SKU 매칭 1건입니다. 사진 한 장에 객체가 여러 개면
그만큼 승인 요청도 여러 건 생겨서 개별적으로 승인/반려할 수 있습니다.
"""

import datetime
import typing

import sqlalchemy
from sqlalchemy.ext import asyncio as sqlalchemy_async

from app.core import config
from app.schemas import approval as approval_schema


class ApprovalNotFoundError(RuntimeError):
    """존재하지 않는 request_id로 조회·처리하려는 경우입니다."""


class AlreadyReviewedError(RuntimeError):
    """이미 승인·반려 처리된 요청을 다시 처리하려는 경우입니다."""


class NoRegistrableCropError(RuntimeError):
    """승인 대상 객체에 등록 가능한 크롭(crop_url)이 없는 경우입니다."""


class RejectReasonRequiredError(RuntimeError):
    """반려 사유가 비어 있는 경우입니다."""


_SELECT_REVIEWER = sqlalchemy.text("""
    SELECT user_id, user_name
      FROM app_user
     WHERE login_id = :login_id
       AND is_active = TRUE
    """)

_SELECT_LIST = sqlalchemy.text("""
    SELECT a.request_id,
           a.status,
           a.requested_at,
           a.reviewed_at,
           a.scene_image_id,
           a.object_id,
           si.origin_name,
           ru.user_name AS requested_by_name,
           vu.user_name AS reviewed_by_name,
           do_.category, do_.sub_category, do_.crop_url,
           sc.sku_code, sc.product_name,
           tr.similarity_score, tr.similarity_grade
      FROM approval a
      JOIN scene_image si      ON si.scene_image_id = a.scene_image_id
      JOIN detected_object do_ ON do_.object_id      = a.object_id
      LEFT JOIN tagging_result tr ON tr.object_id    = a.object_id
      LEFT JOIN sku_catalog sc    ON sc.sku_id       = tr.sku_id
      LEFT JOIN app_user ru ON ru.user_id = a.requested_by
      LEFT JOIN app_user vu ON vu.user_id = a.reviewed_by
     WHERE (:status = 'ALL' OR a.status = :status)
       AND (:requested_from IS NULL OR a.requested_at >= :requested_from)
       AND (:requested_to IS NULL OR a.requested_at <= :requested_to)
     ORDER BY a.requested_at DESC
    """).bindparams(
    sqlalchemy.bindparam(
        "requested_from", type_=sqlalchemy.DateTime(timezone=True)
    ),
    sqlalchemy.bindparam(
        "requested_to", type_=sqlalchemy.DateTime(timezone=True)
    ),
)

_SELECT_DETAIL = sqlalchemy.text("""
    SELECT a.request_id, a.status, a.requested_at, a.reviewed_at,
           a.reject_reason, a.scene_image_id, a.object_id,
           ru.user_name AS requested_by_name,
           vu.user_name AS reviewed_by_name,
           si.image_url AS scene_image_url, si.origin_name, si.mime_type,
           si.file_size, si.width_px, si.height_px,
           si.created_at AS scene_created_at,
           do_.category, do_.sub_category, do_.confidence,
           do_.bbox_xmin, do_.bbox_ymin, do_.bbox_xmax, do_.bbox_ymax,
           do_.attributes, do_.mood_summary, do_.mood_tags, do_.crop_url,
           (do_.embedding IS NOT NULL) AS has_embedding,
           tr.result_id, tr.match_source, tr.match_rank,
           tr.similarity_score, tr.similarity_grade, tr.xai_result,
           sc.sku_id, sc.sku_code, sc.product_name, sc.brand, sc.price,
           sc.attributes AS sku_attributes,
           simg.image_url AS matched_sku_image_url
      FROM approval a
      JOIN scene_image si      ON si.scene_image_id = a.scene_image_id
      JOIN detected_object do_ ON do_.object_id      = a.object_id
      LEFT JOIN tagging_result tr ON tr.object_id    = a.object_id
      LEFT JOIN sku_catalog sc    ON sc.sku_id       = tr.sku_id
      LEFT JOIN sku_image simg ON simg.sku_image_id  = tr.sku_image_id
      LEFT JOIN app_user ru ON ru.user_id = a.requested_by
      LEFT JOIN app_user vu ON vu.user_id = a.reviewed_by
     WHERE a.request_id = :request_id
    """)

_SELECT_FOR_UPDATE = sqlalchemy.text("""
    SELECT request_id, scene_image_id, object_id, status
      FROM approval
     WHERE request_id = :request_id
       FOR UPDATE
    """)

_SELECT_CROP_URL = sqlalchemy.text("""
    SELECT do_.crop_url
      FROM tagging_result tr
      JOIN detected_object do_ ON do_.object_id = tr.object_id
     WHERE tr.object_id = :object_id
    """)

_INSERT_SKU_IMAGE = sqlalchemy.text("""
    INSERT INTO sku_image (
        sku_id, image_url, image_type, embedding, indexed_at
    )
    SELECT tr.sku_id,
           do_.crop_url,
           'STYLING',
           do_.embedding,
           CASE WHEN do_.embedding IS NOT NULL THEN now() END
      FROM tagging_result tr
      JOIN detected_object do_ ON do_.object_id = tr.object_id
     WHERE tr.object_id = :object_id
       AND do_.crop_url IS NOT NULL
    ON CONFLICT (sku_id, image_url) DO NOTHING
    RETURNING sku_image_id, sku_id, embedding IS NOT NULL AS indexed
    """)

_SELECT_SKU_CODE = sqlalchemy.text("""
    SELECT sku_code FROM sku_catalog WHERE sku_id = :sku_id
    """)

_UPDATE_CONFIRM = sqlalchemy.text("""
    UPDATE approval
       SET status = 'ACTIVE', reviewed_by = :reviewer_id, reviewed_at = now()
     WHERE request_id = :request_id
       AND status = 'PENDING'
    """)

_UPDATE_REJECT = sqlalchemy.text("""
    UPDATE approval
       SET status        = 'REJECTED',
           reviewed_by   = :reviewer_id,
           reviewed_at   = now(),
           reject_reason = :reject_reason
     WHERE request_id = :request_id
       AND status = 'PENDING'
    RETURNING request_id
    """)

_CREATE_PENDING_APPROVAL = sqlalchemy.text("""
    INSERT INTO approval (scene_image_id, object_id, requested_by, status)
    SELECT tr.scene_image_id, tr.object_id, si.user_id, 'PENDING'
      FROM tagging_result tr
      JOIN scene_image si ON si.scene_image_id = tr.scene_image_id
     WHERE tr.scene_image_id = :scene_image_id
       AND si.analysis_status = 'completed'
    ON CONFLICT (object_id) WHERE status = 'PENDING' DO NOTHING
    """)


class ApprovalService:
    """승인 요청 조회·승인·반려를 처리하는 서비스입니다."""

    def __init__(
        self,
        session: sqlalchemy_async.AsyncSession,
        settings: typing.Optional[config.Settings] = None,
    ) -> None:
        """서비스가 사용할 세션과 설정을 주입받습니다.

        Args:
            session: 요청 범위의 비동기 SQLAlchemy 세션입니다.
            settings: 고정 로그인 계정 조회에 쓰는 애플리케이션 설정입니다.
        """
        self.session = session
        self.settings = settings or config.get_settings()

    async def list_approvals(
        self,
        status: str,
        requested_from: typing.Optional[datetime.datetime],
        requested_to: typing.Optional[datetime.datetime],
    ) -> approval_schema.ApprovalListResponse:
        """조건에 맞는 승인 요청 전체 목록을 최신순으로 조회합니다.

        요청 1건 = 객체-SKU 매칭 1건이라 사진 한 장에 여러 객체가
        있으면 그만큼 여러 행으로 나뉘어 조회됩니다. 프론트가 무한
        스크롤로 소비하므로 페이지네이션은 없습니다.

        Args:
            status: PENDING | ACTIVE | REJECTED | ALL 중 하나입니다.
            requested_from: 이 시각 이후 요청된 건만 조회합니다.
            requested_to: 이 시각 이전 요청된 건만 조회합니다.

        Returns:
            승인 요청 목록입니다.
        """
        rows = (
            (
                await self.session.execute(
                    _SELECT_LIST,
                    {
                        "status": status,
                        "requested_from": requested_from,
                        "requested_to": requested_to,
                    },
                )
            )
            .mappings()
            .all()
        )

        return approval_schema.ApprovalListResponse(
            items=[
                approval_schema.ApprovalListItem(
                    request_id=row["request_id"],
                    status=row["status"],
                    requested_at=row["requested_at"],
                    requested_by_name=row["requested_by_name"],
                    reviewed_at=row["reviewed_at"],
                    reviewed_by_name=row["reviewed_by_name"],
                    scene_image_id=row["scene_image_id"],
                    origin_name=row["origin_name"],
                    object_id=row["object_id"],
                    category=row["category"],
                    sub_category=row["sub_category"],
                    crop_url=row["crop_url"],
                    sku_code=row["sku_code"],
                    product_name=row["product_name"],
                    similarity_score=(
                        float(row["similarity_score"])
                        if row["similarity_score"] is not None
                        else None
                    ),
                    similarity_grade=row["similarity_grade"],
                )
                for row in rows
            ],
        )

    async def get_detail(
        self, request_id: int
    ) -> approval_schema.ApprovalDetailResponse:
        """승인 요청 1건(객체-SKU 매칭 1건)을 상세 조회합니다.

        Args:
            request_id: 조회할 승인 요청 ID입니다.

        Returns:
            연출 이미지·객체·매칭 SKU·승인 가능 여부가 담긴 상세입니다.

        Raises:
            ApprovalNotFoundError: request_id에 해당하는 요청이 없는
                경우입니다.
        """
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

        xai_result = row["xai_result"]
        return approval_schema.ApprovalDetailResponse(
            request_id=row["request_id"],
            status=row["status"],
            requested_by_name=row["requested_by_name"],
            requested_at=row["requested_at"],
            reviewed_by_name=row["reviewed_by_name"],
            reviewed_at=row["reviewed_at"],
            reject_reason=row["reject_reason"],
            result_id=row["result_id"],
            scene_image=approval_schema.ApprovalSceneImage(
                scene_image_id=row["scene_image_id"],
                image_url=row["scene_image_url"],
                origin_name=row["origin_name"],
                mime_type=row["mime_type"],
                file_size=row["file_size"],
                width_px=row["width_px"],
                height_px=row["height_px"],
                created_at=row["scene_created_at"],
            ),
            object=approval_schema.ApprovalObject(
                object_id=row["object_id"],
                category=row["category"],
                sub_category=row["sub_category"],
                confidence=float(row["confidence"]),
                bbox=approval_schema.BoundingBox(
                    xmin=row["bbox_xmin"],
                    ymin=row["bbox_ymin"],
                    xmax=row["bbox_xmax"],
                    ymax=row["bbox_ymax"],
                ),
                crop_url=row["crop_url"],
                has_embedding=row["has_embedding"],
                mood_summary=row["mood_summary"],
                mood_tags=row["mood_tags"] or [],
                attributes=row["attributes"] or {},
            ),
            sku=(
                approval_schema.ApprovalSku(
                    sku_id=row["sku_id"],
                    sku_code=row["sku_code"],
                    product_name=row["product_name"],
                    brand=row["brand"],
                    price=row["price"],
                    attributes=row["sku_attributes"] or {},
                )
                if row["sku_id"] is not None
                else None
            ),
            match_source=row["match_source"],
            match_rank=row["match_rank"],
            similarity_score=(
                float(row["similarity_score"])
                if row["similarity_score"] is not None
                else None
            ),
            similarity_grade=row["similarity_grade"],
            matched_sku_image_url=row["matched_sku_image_url"],
            xai_result=(
                approval_schema.XaiResult(**xai_result)
                if xai_result is not None
                else None
            ),
            actions=approval_schema.ApprovalActions(
                can_confirm=row["status"] == "PENDING",
                can_reject=row["status"] == "PENDING",
            ),
        )

    async def confirm(self, request_id: int) -> approval_schema.ConfirmResponse:
        """승인 요청을 확정하고 크롭을 ``sku_image``에 등록합니다.

        Args:
            request_id: 확정할 승인 요청 ID입니다.

        Returns:
            승인 상태와 새로 등록된 SKU 이미지(있다면) 정보입니다.

        Raises:
            ApprovalNotFoundError: request_id에 해당하는 요청이 없는
                경우입니다.
            AlreadyReviewedError: 이미 승인·반려된 요청인 경우입니다.
            NoRegistrableCropError: 대상 객체에 등록 가능한 크롭이
                없는 경우입니다.
        """
        locked = (
            (
                await self.session.execute(
                    _SELECT_FOR_UPDATE, {"request_id": request_id}
                )
            )
            .mappings()
            .one_or_none()
        )
        if locked is None:
            raise ApprovalNotFoundError(request_id)
        if locked["status"] != "PENDING":
            raise AlreadyReviewedError(request_id)

        object_id = locked["object_id"]

        crop_url = (
            await self.session.execute(
                _SELECT_CROP_URL, {"object_id": object_id}
            )
        ).scalar_one_or_none()
        if not crop_url:
            raise NoRegistrableCropError(request_id)

        created_row = (
            (
                await self.session.execute(
                    _INSERT_SKU_IMAGE, {"object_id": object_id}
                )
            )
            .mappings()
            .one_or_none()
        )

        created_sku_image = None
        if created_row is not None:
            sku_code = (
                await self.session.execute(
                    _SELECT_SKU_CODE, {"sku_id": created_row["sku_id"]}
                )
            ).scalar_one()
            created_sku_image = approval_schema.ConfirmCreatedSkuImage(
                sku_image_id=created_row["sku_image_id"],
                sku_id=created_row["sku_id"],
                sku_code=sku_code,
                image_type="STYLING",
                indexed=created_row["indexed"],
            )

        reviewer = await self._select_reviewer()
        await self.session.execute(
            _UPDATE_CONFIRM,
            {"request_id": request_id, "reviewer_id": reviewer["user_id"]},
        )
        await self.session.commit()

        return approval_schema.ConfirmResponse(
            request_id=request_id,
            status="ACTIVE",
            reviewed_by_name=reviewer["user_name"],
            reviewed_at=datetime.datetime.now(datetime.timezone.utc),
            created_sku_image=created_sku_image,
            skipped=created_row is None,
        )

    async def reject(
        self, request_id: int, reject_reason: str
    ) -> approval_schema.RejectResponse:
        """승인 요청을 반려합니다.

        Args:
            request_id: 반려할 승인 요청 ID입니다.
            reject_reason: 반려 사유입니다 (필수, 최대 255자).

        Returns:
            반려 상태와 사유가 담긴 응답입니다.

        Raises:
            RejectReasonRequiredError: reject_reason이 비어 있는 경우입니다.
            ApprovalNotFoundError: request_id에 해당하는 요청이 없는
                경우입니다.
            AlreadyReviewedError: 이미 승인·반려된 요청인 경우입니다.
        """
        reject_reason = reject_reason.strip()
        if not reject_reason:
            raise RejectReasonRequiredError(request_id)

        exists = (
            await self.session.execute(
                sqlalchemy.text(
                    "SELECT 1 FROM approval WHERE request_id = :request_id"
                ),
                {"request_id": request_id},
            )
        ).scalar_one_or_none()
        if exists is None:
            raise ApprovalNotFoundError(request_id)

        reviewer = await self._select_reviewer()
        updated = (
            await self.session.execute(
                _UPDATE_REJECT,
                {
                    "request_id": request_id,
                    "reviewer_id": reviewer["user_id"],
                    "reject_reason": reject_reason,
                },
            )
        ).scalar_one_or_none()
        if updated is None:
            await self.session.rollback()
            raise AlreadyReviewedError(request_id)
        await self.session.commit()

        return approval_schema.RejectResponse(
            request_id=request_id,
            status="REJECTED",
            reviewed_by_name=reviewer["user_name"],
            reviewed_at=datetime.datetime.now(datetime.timezone.utc),
            reject_reason=reject_reason,
        )

    async def create_pending_approval(self, scene_image_id: int) -> None:
        """태깅 저장 트랜잭션 안에서 호출할 PENDING 행 생성 함수입니다.

        연출 이미지 안의 탐지 객체(=``tagging_result``)마다 승인 요청을
        하나씩 만듭니다. `PUT /tagging/scenes/{scene_id}`의 태깅 결과
        저장 로직이 아직 구현되지 않아 API로는 연결돼 있지 않습니다.
        저장 로직이 생기면 같은 트랜잭션 안에서 이 메서드를 호출하도록
        연결해야 합니다. 커밋은 호출자가 트랜잭션 전체를 커밋할 때
        함께 이뤄지도록 이 메서드에서는 commit하지 않습니다.

        Args:
            scene_image_id: 태깅이 완료된 연출 이미지 ID입니다.
        """
        await self.session.execute(
            _CREATE_PENDING_APPROVAL, {"scene_image_id": scene_image_id}
        )

    async def _select_reviewer(self) -> sqlalchemy.RowMapping:
        """권한 체계가 없는 현재 단계에서 고정 로그인 계정을 검수자로 씁니다."""
        reviewer = (
            (
                await self.session.execute(
                    _SELECT_REVIEWER, {"login_id": self.settings.mvp_login_id}
                )
            )
            .mappings()
            .one()
        )
        return reviewer
