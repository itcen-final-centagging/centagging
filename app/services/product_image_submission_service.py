"""관리자 제품 이미지 등록 요청의 상태 전이와 SKU 반영을 처리합니다."""

import asyncio
import json
import logging
import typing

import sqlalchemy
from sqlalchemy import orm
from sqlalchemy.ext import asyncio as sqlalchemy_async

from app.core import config
from app.models import sku as sku_models
from app.models.app_user import AppUser
from app.models.product_image_submission import ProductImageSubmission
from app.models.product_image_submission_job import ProductImageSubmissionJob
from app.repositories import product_image_submission_job_repository
from app.schemas import product_image_submission as submission_schema
from app.services import sku_service
from app.services.gemini_service import GeminiService
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


def _detail_select(
    *, include_target_details: bool
) -> sqlalchemy.Select[typing.Any]:
    """목록/상세 조회가 공유하는 조인·컬럼 뼈대를 만듭니다.

    ``target``(연결/생성된 SKU), ``requester``/``reviewer``(app_user)를
    조인하고, target의 대표 이미지(``image_type='MAIN'`` 중 가장 먼저
    등록된 것)를 상관 서브쿼리로 붙인다. 상세 조회만 target의 나머지
    속성 컬럼(brand/price/category/sub_category)을 추가로 담는다.
    """
    target = orm.aliased(sku_models.SkuCatalog, name="target")
    requester = orm.aliased(AppUser, name="requester")
    reviewer = orm.aliased(AppUser, name="reviewer")

    target_main_image_url = (
        sqlalchemy.select(sku_models.SkuImage.image_url)
        .where(
            sku_models.SkuImage.sku_id == target.sku_id,
            sku_models.SkuImage.image_type == "MAIN",
        )
        .order_by(sku_models.SkuImage.sku_image_id)
        .limit(1)
        .correlate(target)
        .scalar_subquery()
    )

    latest_job_id = (
        sqlalchemy.select(ProductImageSubmissionJob.job_id)
        .where(
            ProductImageSubmissionJob.submission_id
            == ProductImageSubmission.submission_id
        )
        .order_by(ProductImageSubmissionJob.created_at.desc())
        .limit(1)
        .correlate(ProductImageSubmission)
        .scalar_subquery()
    )

    columns: list[sqlalchemy.ColumnElement[typing.Any]] = [
        ProductImageSubmission.submission_id,
        ProductImageSubmission.status,
        ProductImageSubmission.target_type,
        ProductImageSubmission.image_url,
        ProductImageSubmission.image_type,
        ProductImageSubmission.proposed_sku_code,
        ProductImageSubmission.proposed_product_name,
        ProductImageSubmission.proposed_brand,
        ProductImageSubmission.proposed_price,
        ProductImageSubmission.proposed_category,
        ProductImageSubmission.proposed_sub_category,
        ProductImageSubmission.proposed_attributes,
        ProductImageSubmission.requested_by,
        ProductImageSubmission.requested_at,
        ProductImageSubmission.submitted_at,
        ProductImageSubmission.reviewed_at,
        ProductImageSubmission.reject_reason,
        ProductImageSubmission.final_sku_id,
        ProductImageSubmission.final_sku_image_id,
        target.sku_code.label("target_sku_code"),
        target.product_name.label("target_product_name"),
    ]
    if include_target_details:
        columns.extend(
            [
                target.sku_id.label("target_sku_id"),
                target.brand.label("target_brand"),
                target.price.label("target_price"),
                target.category.label("target_category"),
                target.sub_category.label("target_sub_category"),
                target.attributes.label("target_attributes"),
            ]
        )
    columns.extend(
        [
            target_main_image_url.label("target_main_image_url"),
            latest_job_id.label("job_id"),
            requester.user_name.label("requested_by_name"),
            reviewer.user_name.label("reviewed_by_name"),
        ]
    )

    return (
        sqlalchemy.select(*columns)
        .join(
            requester, requester.user_id == ProductImageSubmission.requested_by
        )
        .outerjoin(
            target, target.sku_id == ProductImageSubmission.target_sku_id
        )
        .outerjoin(
            reviewer, reviewer.user_id == ProductImageSubmission.reviewed_by
        )
    )


_SELECT_DETAIL = _detail_select(include_target_details=True).where(
    ProductImageSubmission.submission_id
    == sqlalchemy.bindparam("submission_id")
)

_SELECT_LIST = _detail_select(include_target_details=False).order_by(
    ProductImageSubmission.requested_at.desc()
)

_SELECT_LATEST_SUBMISSION_JOB = sqlalchemy.text("""
    SELECT result_payload
      FROM product_image_submission_job
     WHERE submission_id = :submission_id
       AND status = 'SUCCEEDED'
     ORDER BY created_at DESC
     LIMIT 1
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
        """일괄 업로드 파일마다 독립적인 DRAFT 요청 + 추천 작업을 만듭니다."""
        submissions: list[ProductImageSubmission] = []
        try:
            for filename, content in images:
                image_url = sku_service.save_uploaded_image(
                    self.settings, "submissions", filename, content
                )
                submission = ProductImageSubmission(
                    image_url=image_url,
                    image_type="MAIN",
                    status="DRAFT",
                    requested_by=requester_id,
                )
                self.session.add(submission)
                await self.session.flush()
                submissions.append(submission)

            job_by_submission_id = {
                submission.submission_id: (
                    await product_image_submission_job_repository.create_job(
                        self.session, submission.submission_id
                    )
                )
                for submission in submissions
            }
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

        return [
            self._to_item(
                await self._get_detail(submission.submission_id),
                job_id=job_by_submission_id[submission.submission_id].job_id,
            )
            for submission in submissions
        ]

    async def list_submissions(
        self,
        *,
        requester_id: int,
        is_super_admin: bool,
        status: str,
    ) -> submission_schema.ProductImageSubmissionListResponse:
        """역할과 승인 상태가 허용하는 등록 요청만 조회합니다."""
        filters: list[sqlalchemy.ColumnElement[bool]] = []
        if not is_super_admin:
            filters.append(ProductImageSubmission.requested_by == requester_id)
        if status != "ALL":
            filters.append(ProductImageSubmission.status == status)
        stmt = _SELECT_LIST.where(*filters) if filters else _SELECT_LIST
        rows = (await self.session.execute(stmt)).mappings().all()
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
        if not is_super_admin and int(row["requested_by"]) != requester_id:
            raise SubmissionAccessDeniedError()
        return await self._to_detail(row)

    async def configure_draft(
        self,
        submission_id: int,
        request: submission_schema.ConfigureProductImageSubmissionRequest,
        *,
        requester_id: int,
        is_super_admin: bool,
    ) -> submission_schema.ProductImageSubmissionDetail:
        """초안에 기존 SKU 연결 또는 신규 SKU 메타데이터를 저장합니다."""
        submission = await self._get_for_update(submission_id)
        self._assert_access(submission, requester_id, is_super_admin)
        if submission.status != "DRAFT":
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

        submission.target_type = request.target_type
        submission.target_sku_id = target_sku_id
        submission.proposed_sku_code = request.proposed_sku_code
        submission.proposed_product_name = request.proposed_product_name
        submission.proposed_brand = request.proposed_brand
        submission.proposed_price = request.proposed_price
        submission.proposed_category = request.proposed_category
        submission.proposed_sub_category = request.proposed_sub_category
        submission.proposed_attributes = json.loads(
            json.dumps(request.proposed_attributes, ensure_ascii=False)
        )
        submission.image_type = request.image_type

        await self.session.commit()
        return await self._to_detail(await self._get_detail(submission_id))

    async def submit(
        self,
        submission_id: int,
        *,
        requester_id: int,
        is_super_admin: bool,
    ) -> submission_schema.ProductImageSubmissionDetail:
        """구성이 끝난 초안을 최종 관리자 승인 대기열로 보냅니다."""
        submission = await self._get_for_update(submission_id)
        self._assert_access(submission, requester_id, is_super_admin)
        if submission.status != "DRAFT":
            raise SubmissionStateError(submission_id)
        self._assert_ready_for_submit(submission)
        submission.status = "PENDING"
        submission.submitted_at = sqlalchemy.func.now()
        await self.session.commit()
        return await self._to_detail(await self._get_detail(submission_id))

    async def approve(
        self,
        submission_id: int,
        *,
        reviewer_id: int,
    ) -> submission_schema.ProductImageSubmissionDetail:
        """최종 관리자가 PENDING 요청을 실제 SKU 이미지로 반영합니다.

        임베딩은 업로드 시점(Worker)에 계산해 캐시해 둔
        ``draft_embedding``/``draft_embedding_pipeline_version``/
        ``draft_embedding_image_sha256``을 그대로 복사한다. 이 값이
        비어 있으면(추천 파이프라인 실패 등) SKU 이미지는 미색인 상태로
        남고, 이후 배치 재색인으로 채울 수 있다.
        """
        submission = await self._get_for_update(submission_id)
        if submission.status != "PENDING":
            raise SubmissionStateError(submission_id)

        text_embedding: list[float] | None = None
        if submission.target_type != "EXISTING":
            text_embedding = await asyncio.to_thread(
                self.gemini_service.embed_text,
                _build_registration_text(submission),
            )

        try:
            if submission.target_type == "EXISTING":
                final_sku_id = int(submission.target_sku_id)
            else:
                sku = sku_models.SkuCatalog(
                    sku_code=str(submission.proposed_sku_code),
                    product_name=str(submission.proposed_product_name),
                    brand=submission.proposed_brand,
                    price=submission.proposed_price,
                    category=submission.proposed_category,
                    sub_category=submission.proposed_sub_category,
                    attributes=_as_attributes(submission.proposed_attributes),
                    text_embedding=text_embedding,
                )
                self.session.add(sku)
                await self.session.flush()
                final_sku_id = int(sku.sku_id)

            sku_image = sku_models.SkuImage(
                sku_id=final_sku_id,
                image_url=submission.image_url,
                image_type=submission.image_type,
                embedding=(
                    submission.draft_embedding.to_list()
                    if submission.draft_embedding is not None
                    else None
                ),
                embedding_pipeline_version=(
                    submission.draft_embedding_pipeline_version
                ),
                embedding_image_sha256=(
                    submission.draft_embedding_image_sha256
                ),
                indexed_at=(
                    sqlalchemy.func.now()
                    if submission.draft_embedding is not None
                    else None
                ),
            )
            self.session.add(sku_image)
            await self.session.flush()

            submission.status = "APPROVED"
            submission.reviewed_by = reviewer_id
            submission.reviewed_at = sqlalchemy.func.now()
            submission.final_sku_id = final_sku_id
            submission.final_sku_image_id = sku_image.sku_image_id
            submission.reject_reason = None

            await self.session.commit()
        except sqlalchemy.exc.IntegrityError as error:
            await self.session.rollback()
            raise SubmissionSkuCodeConflictError(submission_id) from error
        return await self._to_detail(await self._get_detail(submission_id))

    async def reject(
        self,
        submission_id: int,
        *,
        reject_reason: str,
        reviewer_id: int,
    ) -> submission_schema.ProductImageSubmissionDetail:
        """최종 관리자가 PENDING 요청을 반려합니다."""
        submission = await self._get_for_update(submission_id)
        if submission.status != "PENDING":
            raise SubmissionStateError(submission_id)
        submission.status = "REJECTED"
        submission.reviewed_by = reviewer_id
        submission.reviewed_at = sqlalchemy.func.now()
        submission.reject_reason = reject_reason.strip()
        await self.session.commit()
        return await self._to_detail(await self._get_detail(submission_id))

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
    ) -> ProductImageSubmission:
        submission = (
            await self.session.execute(
                sqlalchemy.select(ProductImageSubmission)
                .where(ProductImageSubmission.submission_id == submission_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if submission is None:
            raise SubmissionNotFoundError(submission_id)
        return submission

    @staticmethod
    def _assert_access(
        submission: ProductImageSubmission,
        requester_id: int,
        is_super_admin: bool,
    ) -> None:
        if not is_super_admin and submission.requested_by != requester_id:
            raise SubmissionAccessDeniedError()

    @staticmethod
    def _assert_ready_for_submit(submission: ProductImageSubmission) -> None:
        if submission.target_type == "EXISTING" and submission.target_sku_id:
            return
        if (
            submission.target_type == "NEW"
            and submission.proposed_sku_code
            and submission.proposed_product_name
        ):
            return
        raise SubmissionValidationError(
            "기존 SKU 또는 신규 SKU 필수 정보를 입력해야 합니다."
        )

    def _to_item(
        self,
        row: sqlalchemy.RowMapping,
        *,
        job_id: typing.Any | None = None,
    ) -> submission_schema.ProductImageSubmissionItem:
        target_main_image_url = row["target_main_image_url"]
        return submission_schema.ProductImageSubmissionItem(
            final_sku_id=row["final_sku_id"],
            final_sku_image_id=row["final_sku_image_id"],
            image_type=typing.cast(
                submission_schema.SkuImageType, row["image_type"]
            ),
            image_url=str(row["image_url"]),
            job_id=job_id if job_id is not None else row["job_id"],
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

    async def _to_detail(
        self,
        row: sqlalchemy.RowMapping,
    ) -> submission_schema.ProductImageSubmissionDetail:
        candidates: list[
            submission_schema.ProductImageSubmissionCandidateSku
        ] = []
        if row["target_type"] == "EXISTING":
            candidates = await self._fetch_recommend_candidates(
                int(row["submission_id"])
            )
            target_sku_id = row["target_sku_id"]
            if target_sku_id is not None and not any(
                candidate.sku_id == int(target_sku_id)
                for candidate in candidates
            ):
                target_main_image_url = row["target_main_image_url"]
                candidates.insert(
                    0,
                    submission_schema.ProductImageSubmissionCandidateSku(
                        sku_id=int(target_sku_id),
                        sku_code=str(row["target_sku_code"]),
                        product_name=str(row["target_product_name"]),
                        match_rank=0,
                        brand=row["target_brand"],
                        price=row["target_price"],
                        category=row["target_category"],
                        sub_category=row["target_sub_category"],
                        attributes=_as_attributes(row["target_attributes"]),
                        image_url=(
                            self.sku_image_storage.public_url(
                                target_main_image_url
                            )
                            if target_main_image_url
                            else None
                        ),
                        via_search=True,
                    ),
                )
        return submission_schema.ProductImageSubmissionDetail(
            **self._to_item(row).model_dump(),
            proposed_attributes=_as_attributes(row["proposed_attributes"]),
            proposed_brand=row["proposed_brand"],
            proposed_category=row["proposed_category"],
            proposed_price=row["proposed_price"],
            proposed_sub_category=row["proposed_sub_category"],
            target_attributes=_as_attributes(row["target_attributes"]),
            target_brand=row["target_brand"],
            target_category=row["target_category"],
            target_price=row["target_price"],
            target_sub_category=row["target_sub_category"],
            candidates=candidates,
        )

    async def _fetch_recommend_candidates(
        self, submission_id: int
    ) -> list[submission_schema.ProductImageSubmissionCandidateSku]:
        """추천 당시 함께 제시됐던 후보 SKU 목록을 다시 만듭니다.

        가장 최근 SUCCEEDED 작업의 result_payload에서 sku_candidates를
        그대로 복원한다. 최종 확정이 검색(SEARCH)으로 직접 연결한
        SKU여도 추천 자체는 그 전에 한 번 실행됐으므로 후보는 그대로
        남아 있다. 이 요청에 추천 이력 자체가 없을 때만 빈 목록을
        반환하며, 조회·파싱에 실패해도 승인 화면 표시가 막히지 않도록
        예외를 삼킨다.
        """
        try:
            payload = await self.session.scalar(
                _SELECT_LATEST_SUBMISSION_JOB,
                {"submission_id": submission_id},
            )
            if not isinstance(payload, dict):
                return []
            raw_candidates = payload.get("sku_candidates")
            if not isinstance(raw_candidates, list):
                return []

            candidates: list[
                submission_schema.ProductImageSubmissionCandidateSku
            ] = []
            for rank, candidate in enumerate(raw_candidates, start=1):
                if not isinstance(candidate, dict):
                    continue
                matched_image = candidate.get("matched_sku_image") or {}
                image_url = matched_image.get("image_url")
                similarity_score = candidate.get("similarity_score")
                xai_result = candidate.get("xai_result") or {}
                candidates.append(
                    submission_schema.ProductImageSubmissionCandidateSku(
                        sku_id=int(candidate["sku_id"]),
                        sku_code=str(candidate["sku_code"]),
                        product_name=str(candidate["product_name"]),
                        match_rank=rank,
                        category=candidate.get("category"),
                        sub_category=candidate.get("sub_category"),
                        attributes=candidate.get("attrs") or {},
                        image_url=(
                            self.sku_image_storage.public_url(image_url)
                            if image_url
                            else None
                        ),
                        similarity_score=(
                            float(similarity_score) / 100
                            if similarity_score is not None
                            else None
                        ),
                        xai_common=str(xai_result.get("common") or ""),
                        xai_difference=str(xai_result.get("difference") or ""),
                    )
                )
            return candidates
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception(
                "추천 후보 목록을 다시 만들지 못했습니다: submission_id=%s",
                submission_id,
            )
            return []


def _as_attributes(value: object) -> dict[str, typing.Any]:
    """DB JSONB 값을 API 스키마에 맞는 속성 객체로 정규화합니다."""
    return value if isinstance(value, dict) else {}


def _build_registration_text(submission: ProductImageSubmission) -> str:
    """신규 SKU의 text_embedding에 넣을 텍스트를 만듭니다.

    scripts/embedding/text_builder.py::build_embedding_text와 같은 순서
    (상품명 -> 카테고리 -> 속성)를 써서, 초기 카탈로그 시드로 만들어진
    sku_catalog.text_embedding과 같은 텍스트 관례를 따르게 합니다.
    """
    lines = [str(submission.proposed_product_name)]

    category_line = f"카테고리: {submission.proposed_category}"
    if submission.proposed_sub_category:
        category_line += f" > {submission.proposed_sub_category}"
    lines.append(category_line)

    attributes = _as_attributes(submission.proposed_attributes)
    if attributes:
        attr_text = ", ".join(
            f"{key}: {value}" for key, value in attributes.items()
        )
        lines.append(f"속성: {attr_text}")

    return "\n".join(lines)
