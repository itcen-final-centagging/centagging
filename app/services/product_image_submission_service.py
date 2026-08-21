"""관리자 제품 이미지 등록 요청의 상태 전이와 SKU 반영을 처리합니다."""

import asyncio
import hashlib
import io
import json
import logging
import typing

import sqlalchemy
from sqlalchemy.ext import asyncio as sqlalchemy_async
from PIL import Image

from app.core import config
from app.models import sku as sku_models
from app.schemas import product_image_submission as submission_schema
from app.services import image_processing_service, sku_service
from app.services.fused_metadata import build_metadata_text
from app.services.gemini_service import GeminiService
from app.services.image_preprocessing_service import preprocess_for_embedding
from app.services.sku_image_storage import SkuImageStorage

_LOGGER = logging.getLogger(__name__)


class SubmissionNotFoundError(RuntimeError):
    """요청한 제품 이미지 등록 건이 없을 때 발생합니다."""


class SubmissionAccessDeniedError(RuntimeError):
    """본인이 작성하지 않은 요청을 일반 관리자가 조회할 때 발생합니다."""


class SubmissionStateError(RuntimeError):
    """현재 상태에서 허용되지 않는 상태 전이를 시도할 때 발생합니다."""


class SubmissionValidationError(ValueError):
    """제출에 필요한 기존/신규 SKU 정보가 부족할 때 발생합니다."""


class SubmissionSkuCodeConflictError(RuntimeError):
    """승인 시 신규 SKU 코드가 이미 존재할 때 발생합니다."""


_INSERT_DRAFT = sqlalchemy.text("""
    INSERT INTO product_image_submission (
        image_url, image_type, status, requested_by
    )
    VALUES (:image_url, :image_type, 'DRAFT', :requested_by)
    RETURNING submission_id
    """)

_SELECT_DETAIL = sqlalchemy.text("""
    SELECT p.submission_id,
           p.status,
           p.target_type,
           p.image_url,
           p.image_type,
           p.proposed_sku_code,
           p.proposed_product_name,
           p.proposed_brand,
           p.proposed_price,
           p.proposed_category,
           p.proposed_sub_category,
           p.proposed_attributes,
           p.requested_by,
           p.requested_at,
           p.submitted_at,
           p.reviewed_at,
           p.reject_reason,
           p.final_sku_id,
           p.final_sku_image_id,
           target.sku_code AS target_sku_code,
           target.product_name AS target_product_name,
           target.brand AS target_brand,
           target.price AS target_price,
           target.category AS target_category,
           target.sub_category AS target_sub_category,
           target_image.image_url AS target_main_image_url,
           requester.user_name AS requested_by_name,
           reviewer.user_name AS reviewed_by_name
      FROM product_image_submission p
      JOIN app_user requester ON requester.user_id = p.requested_by
      LEFT JOIN sku_catalog target ON target.sku_id = p.target_sku_id
      LEFT JOIN LATERAL (
          SELECT si.image_url
            FROM sku_image si
           WHERE si.sku_id = target.sku_id
             AND si.image_type = 'MAIN'
           ORDER BY si.sku_image_id
           LIMIT 1
      ) target_image ON TRUE
      LEFT JOIN app_user reviewer ON reviewer.user_id = p.reviewed_by
     WHERE p.submission_id = :submission_id
    """)

_SELECT_LIST = sqlalchemy.text("""
    SELECT p.submission_id,
           p.status,
           p.target_type,
           p.image_url,
           p.image_type,
           p.proposed_sku_code,
           p.proposed_product_name,
           p.proposed_brand,
           p.proposed_price,
           p.proposed_category,
           p.proposed_sub_category,
           p.proposed_attributes,
           p.requested_by,
           p.requested_at,
           p.submitted_at,
           p.reviewed_at,
           p.reject_reason,
           p.final_sku_id,
           p.final_sku_image_id,
           target.sku_code AS target_sku_code,
           target.product_name AS target_product_name,
           target_image.image_url AS target_main_image_url,
           requester.user_name AS requested_by_name,
           reviewer.user_name AS reviewed_by_name
      FROM product_image_submission p
      JOIN app_user requester ON requester.user_id = p.requested_by
      LEFT JOIN sku_catalog target ON target.sku_id = p.target_sku_id
      LEFT JOIN LATERAL (
          SELECT si.image_url
            FROM sku_image si
           WHERE si.sku_id = target.sku_id
             AND si.image_type = 'MAIN'
           ORDER BY si.sku_image_id
           LIMIT 1
      ) target_image ON TRUE
      LEFT JOIN app_user reviewer ON reviewer.user_id = p.reviewed_by
     WHERE (:is_super_admin OR p.requested_by = :requester_id)
       AND (:status = 'ALL' OR p.status = :status)
     ORDER BY p.requested_at DESC
    """)

_SELECT_FOR_UPDATE = sqlalchemy.text("""
    SELECT submission_id,
           status,
           target_type,
           target_sku_id,
           proposed_sku_code,
           proposed_product_name,
           proposed_brand,
           proposed_price,
           proposed_category,
           proposed_sub_category,
           proposed_attributes,
           image_url,
           image_type,
           requested_by
      FROM product_image_submission
     WHERE submission_id = :submission_id
       FOR UPDATE
    """)

_UPDATE_DRAFT = sqlalchemy.text("""
    UPDATE product_image_submission
       SET target_type = :target_type,
           target_sku_id = :target_sku_id,
           proposed_sku_code = :proposed_sku_code,
           proposed_product_name = :proposed_product_name,
           proposed_brand = :proposed_brand,
           proposed_price = :proposed_price,
           proposed_category = :proposed_category,
           proposed_sub_category = :proposed_sub_category,
           proposed_attributes = CAST(:proposed_attributes AS jsonb),
           image_type = :image_type
     WHERE submission_id = :submission_id
       AND status = 'DRAFT'
    """)

_SUBMIT = sqlalchemy.text("""
    UPDATE product_image_submission
       SET status = 'PENDING', submitted_at = now()
     WHERE submission_id = :submission_id
       AND status = 'DRAFT'
    """)

_APPROVE = sqlalchemy.text("""
    UPDATE product_image_submission
       SET status = 'APPROVED',
           reviewed_by = :reviewed_by,
           reviewed_at = now(),
           final_sku_id = :final_sku_id,
           final_sku_image_id = :final_sku_image_id,
           reject_reason = NULL
     WHERE submission_id = :submission_id
       AND status = 'PENDING'
    """)

_REJECT = sqlalchemy.text("""
    UPDATE product_image_submission
       SET status = 'REJECTED',
           reviewed_by = :reviewed_by,
           reviewed_at = now(),
           reject_reason = :reject_reason
     WHERE submission_id = :submission_id
       AND status = 'PENDING'
    """)


class ProductImageSubmissionService:
    """제품 이미지 초안·제출·최종 승인 처리를 담당합니다."""

    def __init__(
        self,
        session: sqlalchemy_async.AsyncSession,
        settings: config.Settings,
        gemini_service: GeminiService,
    ) -> None:
        """Initialize the product image submission service."""
        self.session = session
        self.settings = settings
        self.gemini_service = gemini_service
        self.sku_image_storage = SkuImageStorage(settings.sku_image_root)

    async def create_drafts(
        self,
        images: list[tuple[str, bytes]],
        requester_id: int,
    ) -> list[submission_schema.ProductImageSubmissionItem]:
        """일괄 업로드 파일마다 독립적인 DRAFT 요청을 만듭니다."""
        submission_ids: list[int] = []
        try:
            for filename, content in images:
                image_url = sku_service.save_uploaded_image(
                    self.settings, "submissions", filename, content
                )
                result = await self.session.execute(
                    _INSERT_DRAFT,
                    {
                        "image_type": "MAIN",
                        "image_url": image_url,
                        "requested_by": requester_id,
                    },
                )
                submission_ids.append(int(result.scalar_one()))
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        return [
            self._to_item(await self._get_detail(submission_id))
            for submission_id in submission_ids
        ]

    async def list_submissions(
        self,
        *,
        requester_id: int,
        is_super_admin: bool,
        status: str,
    ) -> submission_schema.ProductImageSubmissionListResponse:
        """역할과 승인 상태가 허용하는 등록 요청만 조회합니다."""
        rows = (
            (
                await self.session.execute(
                    _SELECT_LIST,
                    {
                        "is_super_admin": is_super_admin,
                        "requester_id": requester_id,
                        "status": status,
                    },
                )
            )
            .mappings()
            .all()
        )
        return submission_schema.ProductImageSubmissionListResponse(
            items=[self._to_item(row) for row in rows]
        )

    async def get_submission(
        self,
        submission_id: int,
        *,
        requester_id: int,
        is_super_admin: bool,
    ) -> submission_schema.ProductImageSubmissionDetail:
        """본인 요청 또는 최종 관리자가 요청 상세를 조회합니다."""
        row = await self._get_detail(submission_id)
        self._assert_access(row, requester_id, is_super_admin)
        return self._to_detail(row)

    async def configure_draft(
        self,
        submission_id: int,
        request: submission_schema.ConfigureProductImageSubmissionRequest,
        *,
        requester_id: int,
        is_super_admin: bool,
    ) -> submission_schema.ProductImageSubmissionDetail:
        """초안에 기존 SKU 연결 또는 신규 SKU 메타데이터를 저장합니다."""
        row = await self._get_for_update(submission_id)
        self._assert_access(row, requester_id, is_super_admin)
        if row["status"] != "DRAFT":
            raise SubmissionStateError(submission_id)

        target_sku_id: int | None = None
        if request.target_type == "EXISTING":
            if not request.target_sku_code:
                raise SubmissionValidationError(
                    "기존 SKU 코드를 선택해야 합니다."
                )
            sku = await sku_service.find_sku_by_code(
                self.session, request.target_sku_code
            )
            if sku is None:
                raise SubmissionValidationError(
                    "선택한 기존 SKU를 찾을 수 없습니다."
                )
            target_sku_id = sku.sku_id

        await self.session.execute(
            _UPDATE_DRAFT,
            {
                "image_type": request.image_type,
                "proposed_attributes": json.dumps(
                    request.proposed_attributes, ensure_ascii=False
                ),
                "proposed_brand": request.proposed_brand,
                "proposed_category": request.proposed_category,
                "proposed_price": request.proposed_price,
                "proposed_product_name": request.proposed_product_name,
                "proposed_sku_code": request.proposed_sku_code,
                "proposed_sub_category": request.proposed_sub_category,
                "submission_id": submission_id,
                "target_sku_id": target_sku_id,
                "target_type": request.target_type,
            },
        )
        await self.session.commit()
        return self._to_detail(await self._get_detail(submission_id))

    async def submit(
        self,
        submission_id: int,
        *,
        requester_id: int,
        is_super_admin: bool,
    ) -> submission_schema.ProductImageSubmissionDetail:
        """구성이 끝난 초안을 최종 관리자 승인 대기열로 보냅니다."""
        row = await self._get_for_update(submission_id)
        self._assert_access(row, requester_id, is_super_admin)
        if row["status"] != "DRAFT":
            raise SubmissionStateError(submission_id)
        self._assert_ready_for_submit(row)
        await self.session.execute(_SUBMIT, {"submission_id": submission_id})
        await self.session.commit()
        return self._to_detail(await self._get_detail(submission_id))

    async def approve(
        self,
        submission_id: int,
        *,
        reviewer_id: int,
    ) -> submission_schema.ProductImageSubmissionDetail:
        """최종 관리자가 PENDING 요청을 실제 SKU 이미지로 반영합니다."""
        row = await self._get_for_update(submission_id)
        if row["status"] != "PENDING":
            raise SubmissionStateError(submission_id)

        text_embedding: list[float] | None = None
        if row["target_type"] != "EXISTING":
            text_embedding = await asyncio.to_thread(
                self.gemini_service.embed_text,
                _build_registration_text(row),
            )

        try:
            if row["target_type"] == "EXISTING":
                final_sku_id = int(row["target_sku_id"])
            else:
                sku = sku_models.SkuCatalog(
                    sku_code=str(row["proposed_sku_code"]),
                    product_name=str(row["proposed_product_name"]),
                    brand=row["proposed_brand"],
                    price=row["proposed_price"],
                    category=row["proposed_category"],
                    sub_category=row["proposed_sub_category"],
                    attributes=_as_attributes(row["proposed_attributes"]),
                    text_embedding=text_embedding,
                )
                self.session.add(sku)
                await self.session.flush()
                final_sku_id = int(sku.sku_id)

            sku_image = sku_models.SkuImage(
                sku_id=final_sku_id,
                image_url=str(row["image_url"]),
                image_type=str(row["image_type"]),
            )
            self.session.add(sku_image)
            await self.session.flush()
            await self.session.execute(
                _APPROVE,
                {
                    "final_sku_id": final_sku_id,
                    "final_sku_image_id": sku_image.sku_image_id,
                    "reviewed_by": reviewer_id,
                    "submission_id": submission_id,
                },
            )
            await self.session.commit()
        except sqlalchemy.exc.IntegrityError as error:
            await self.session.rollback()
            raise SubmissionSkuCodeConflictError(submission_id) from error
        await self._index_approved_sku_image(sku_image, final_sku_id)
        return self._to_detail(await self._get_detail(submission_id))

    async def _index_approved_sku_image(
        self,
        sku_image: sku_models.SkuImage,
        sku_id: int,
    ) -> None:
        """승인된 이미지의 융합 임베딩을 만들고 실패 시 미색인으로 남깁니다."""
        try:
            sku = await self.session.get(sku_models.SkuCatalog, sku_id)
            if sku is None:
                raise RuntimeError(
                    f"승인 SKU를 찾을 수 없습니다: sku_id={sku_id}"
                )
            image_bytes = image_processing_service.read_sku_image_bytes(
                sku_image.image_url,
                self.settings.sku_image_root,
                self.settings.image_storage_root,
            )
            if image_bytes is None:
                raise RuntimeError("승인된 SKU 이미지를 읽을 수 없습니다.")
            image = await asyncio.to_thread(
                image_processing_service.decode_image,
                image_bytes,
            )
            processed_image = await asyncio.to_thread(
                preprocess_for_embedding,
                image,
                self.settings,
            )
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
                processed_image.image,
                metadata_text,
            )
            sku_image.embedding = embedding
            sku_image.embedding_pipeline_version = (
                self.settings.embedding_pipeline_version
            )
            sku_image.embedding_image_sha256 = _image_sha256(
                processed_image.image
            )
            sku_image.indexed_at = sqlalchemy.func.now()
            await self.session.commit()
        except (
            Exception
        ):  # noqa: BLE001 - 승인 상태는 보존하고 배치 재색인을 허용한다
            await self.session.rollback()
            _LOGGER.exception(
                "승인 SKU 이미지 융합 임베딩 생성 실패: sku_image_id=%s",
                sku_image.sku_image_id,
            )

    async def reject(
        self,
        submission_id: int,
        *,
        reject_reason: str,
        reviewer_id: int,
    ) -> submission_schema.ProductImageSubmissionDetail:
        """최종 관리자가 PENDING 요청을 반려합니다."""
        row = await self._get_for_update(submission_id)
        if row["status"] != "PENDING":
            raise SubmissionStateError(submission_id)
        await self.session.execute(
            _REJECT,
            {
                "reject_reason": reject_reason.strip(),
                "reviewed_by": reviewer_id,
                "submission_id": submission_id,
            },
        )
        await self.session.commit()
        return self._to_detail(await self._get_detail(submission_id))

    async def _get_detail(self, submission_id: int) -> sqlalchemy.RowMapping:
        row = (
            (
                await self.session.execute(
                    _SELECT_DETAIL, {"submission_id": submission_id}
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise SubmissionNotFoundError(submission_id)
        return row

    async def _get_for_update(
        self, submission_id: int
    ) -> sqlalchemy.RowMapping:
        row = (
            (
                await self.session.execute(
                    _SELECT_FOR_UPDATE, {"submission_id": submission_id}
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise SubmissionNotFoundError(submission_id)
        return row

    @staticmethod
    def _assert_access(
        row: sqlalchemy.RowMapping,
        requester_id: int,
        is_super_admin: bool,
    ) -> None:
        if not is_super_admin and int(row["requested_by"]) != requester_id:
            raise SubmissionAccessDeniedError()

    @staticmethod
    def _assert_ready_for_submit(row: sqlalchemy.RowMapping) -> None:
        if row["target_type"] == "EXISTING" and row["target_sku_id"]:
            return
        if (
            row["target_type"] == "NEW"
            and row["proposed_sku_code"]
            and row["proposed_product_name"]
        ):
            return
        raise SubmissionValidationError(
            "기존 SKU 또는 신규 SKU 필수 정보를 입력해야 합니다."
        )

    def _to_item(
        self,
        row: sqlalchemy.RowMapping,
    ) -> submission_schema.ProductImageSubmissionItem:
        target_main_image_url = row["target_main_image_url"]
        return submission_schema.ProductImageSubmissionItem(
            final_sku_id=row["final_sku_id"],
            final_sku_image_id=row["final_sku_image_id"],
            image_type=typing.cast(
                submission_schema.SkuImageType, row["image_type"]
            ),
            image_url=str(row["image_url"]),
            proposed_product_name=row["proposed_product_name"],
            proposed_sku_code=row["proposed_sku_code"],
            reject_reason=row["reject_reason"],
            requested_at=row["requested_at"],
            requested_by_name=str(row["requested_by_name"]),
            reviewed_at=row["reviewed_at"],
            reviewed_by_name=row["reviewed_by_name"],
            status=typing.cast(
                submission_schema.SubmissionStatus, row["status"]
            ),
            submission_id=int(row["submission_id"]),
            submitted_at=row["submitted_at"],
            target_main_image_url=(
                self.sku_image_storage.public_url(target_main_image_url)
                if target_main_image_url
                else None
            ),
            target_product_name=row["target_product_name"],
            target_sku_code=row["target_sku_code"],
            target_type=typing.cast(
                submission_schema.SubmissionTargetType | None,
                row["target_type"],
            ),
        )

    def _to_detail(
        self,
        row: sqlalchemy.RowMapping,
    ) -> submission_schema.ProductImageSubmissionDetail:
        return submission_schema.ProductImageSubmissionDetail(
            **self._to_item(row).model_dump(),
            proposed_attributes=_as_attributes(row["proposed_attributes"]),
            proposed_brand=row["proposed_brand"],
            proposed_category=row["proposed_category"],
            proposed_price=row["proposed_price"],
            proposed_sub_category=row["proposed_sub_category"],
            target_brand=row["target_brand"],
            target_category=row["target_category"],
            target_price=row["target_price"],
            target_sub_category=row["target_sub_category"],
        )


def _as_attributes(value: object) -> dict[str, typing.Any]:
    """DB JSONB 값을 API 스키마에 맞는 속성 객체로 정규화합니다."""
    return value if isinstance(value, dict) else {}


def _image_sha256(image: Image.Image) -> str:
    """전처리 이미지의 고정 PNG 표현을 재색인 식별자로 해시합니다."""
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG", optimize=False)
    return hashlib.sha256(buffer.getvalue()).hexdigest()


def _build_registration_text(row: sqlalchemy.RowMapping) -> str:
    """신규 SKU의 text_embedding에 넣을 텍스트를 만듭니다.

    scripts/embedding/text_builder.py::build_embedding_text와 같은 순서
    (상품명 -> 카테고리 -> 속성)를 써서, 초기 카탈로그 시드로 만들어진
    sku_catalog.text_embedding과 같은 텍스트 관례를 따르게 합니다.
    """
    lines = [str(row["proposed_product_name"])]

    category_line = f"카테고리: {row['proposed_category']}"
    if row["proposed_sub_category"]:
        category_line += f" > {row['proposed_sub_category']}"
    lines.append(category_line)

    attributes = _as_attributes(row["proposed_attributes"])
    if attributes:
        attr_text = ", ".join(
            f"{key}: {value}" for key, value in attributes.items()
        )
        lines.append(f"속성: {attr_text}")

    return "\n".join(lines)
