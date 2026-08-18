"""관리자 제품 이미지 등록 초안·승인 API입니다."""

import typing

import fastapi

from app import dependencies
from app.schemas import common as common_schema
from app.schemas import product_image_submission as submission_schema
from app.services import image_validation, product_image_submission_service

router = fastapi.APIRouter(
    prefix="/product-image-submissions",
    tags=["product-image-submissions"],
)

_MAX_BATCH_IMAGE_COUNT = 20


def _is_super_admin(user: dependencies.AdminUser) -> bool:
    """요청자 범위 제한을 풀 수 있는지 반환합니다."""
    return user["role"] == "SUPER_ADMIN"


@router.post(
    "",
    response_model=common_schema.SuccessResponse[
        submission_schema.ProductImageSubmissionBatchResponse
    ],
    status_code=fastapi.status.HTTP_201_CREATED,
)
async def create_product_image_drafts(
    images: list[fastapi.UploadFile] = fastapi.File(...),
    user: dependencies.AdminUser = fastapi.Depends(dependencies.get_admin_user),
    service: product_image_submission_service.ProductImageSubmissionService = (
        fastapi.Depends(dependencies.get_product_image_submission_service)
    ),
) -> common_schema.SuccessResponse[
    submission_schema.ProductImageSubmissionBatchResponse
]:
    """제품 이미지 여러 장을 독립적인 ``DRAFT`` 항목으로 업로드합니다.

    한 요청의 파일은 함께 업로드하지만, 각각 기존 SKU 연결 또는 신규 SKU
    생성을 별도로 선택하고 개별 승인할 수 있습니다.
    """
    if not images:
        raise fastapi.HTTPException(
            status_code=422, detail="이미지를 한 장 이상 업로드해야 합니다."
        )
    if len(images) > _MAX_BATCH_IMAGE_COUNT:
        raise fastapi.HTTPException(
            status_code=422,
            detail=f"이미지는 한 번에 최대 {_MAX_BATCH_IMAGE_COUNT}장까지 가능합니다.",
        )

    validated_images: list[tuple[str, bytes]] = []
    for image in images:
        try:
            validated = await image_validation.validate_image(image)
        except image_validation.ImageValidationError as error:
            raise fastapi.HTTPException(
                status_code=error.status_code, detail=str(error)
            ) from error
        validated_images.append(
            (validated.metadata.origin_name, validated.content)
        )

    items = await service.create_drafts(validated_images, user["user_id"])
    return common_schema.success_response(
        submission_schema.ProductImageSubmissionBatchResponse(items=items)
    )


@router.get(
    "",
    response_model=common_schema.SuccessResponse[
        submission_schema.ProductImageSubmissionListResponse
    ],
)
async def list_product_image_submissions(
    status: typing.Literal[
        "DRAFT", "PENDING", "APPROVED", "REJECTED", "ALL"
    ] = "ALL",
    user: dependencies.AdminUser = fastapi.Depends(dependencies.get_admin_user),
    service: product_image_submission_service.ProductImageSubmissionService = (
        fastapi.Depends(dependencies.get_product_image_submission_service)
    ),
) -> common_schema.SuccessResponse[
    submission_schema.ProductImageSubmissionListResponse
]:
    """역할 및 상태 범위에 맞는 제품 이미지 등록 요청을 조회합니다."""
    return common_schema.success_response(
        await service.list_submissions(
            requester_id=user["user_id"],
            is_super_admin=_is_super_admin(user),
            status=status,
        )
    )


@router.get(
    "/{submission_id}",
    response_model=common_schema.SuccessResponse[
        submission_schema.ProductImageSubmissionDetail
    ],
)
async def get_product_image_submission(
    submission_id: int,
    user: dependencies.AdminUser = fastapi.Depends(dependencies.get_admin_user),
    service: product_image_submission_service.ProductImageSubmissionService = (
        fastapi.Depends(dependencies.get_product_image_submission_service)
    ),
) -> common_schema.SuccessResponse[
    submission_schema.ProductImageSubmissionDetail
]:
    """본인 요청 또는 최종 관리자가 한 건의 상세 메타데이터를 조회합니다."""
    try:
        return common_schema.success_response(
            await service.get_submission(
                submission_id,
                requester_id=user["user_id"],
                is_super_admin=_is_super_admin(user),
            )
        )
    except product_image_submission_service.SubmissionNotFoundError as error:
        raise fastapi.HTTPException(
            status_code=404, detail="등록 요청이 없습니다."
        ) from error
    except (
        product_image_submission_service.SubmissionAccessDeniedError
    ) as error:
        raise fastapi.HTTPException(
            status_code=403, detail="조회 권한이 없습니다."
        ) from error


@router.put(
    "/{submission_id}",
    response_model=common_schema.SuccessResponse[
        submission_schema.ProductImageSubmissionDetail
    ],
)
async def configure_product_image_submission(
    submission_id: int,
    body: submission_schema.ConfigureProductImageSubmissionRequest,
    user: dependencies.AdminUser = fastapi.Depends(dependencies.get_admin_user),
    service: product_image_submission_service.ProductImageSubmissionService = (
        fastapi.Depends(dependencies.get_product_image_submission_service)
    ),
) -> common_schema.SuccessResponse[
    submission_schema.ProductImageSubmissionDetail
]:
    """초안에 기존 SKU 연결 또는 신규 SKU 메타데이터를 저장합니다."""
    try:
        return common_schema.success_response(
            await service.configure_draft(
                submission_id,
                body,
                requester_id=user["user_id"],
                is_super_admin=_is_super_admin(user),
            )
        )
    except product_image_submission_service.SubmissionNotFoundError as error:
        raise fastapi.HTTPException(
            status_code=404, detail="등록 요청이 없습니다."
        ) from error
    except (
        product_image_submission_service.SubmissionAccessDeniedError
    ) as error:
        raise fastapi.HTTPException(
            status_code=403, detail="수정 권한이 없습니다."
        ) from error
    except product_image_submission_service.SubmissionStateError as error:
        raise fastapi.HTTPException(
            status_code=409, detail="초안만 수정할 수 있습니다."
        ) from error
    except product_image_submission_service.SubmissionValidationError as error:
        raise fastapi.HTTPException(
            status_code=422, detail=str(error)
        ) from error


@router.post(
    "/{submission_id}/submit",
    response_model=common_schema.SuccessResponse[
        submission_schema.ProductImageSubmissionDetail
    ],
)
async def submit_product_image_submission(
    submission_id: int,
    user: dependencies.AdminUser = fastapi.Depends(dependencies.get_admin_user),
    service: product_image_submission_service.ProductImageSubmissionService = (
        fastapi.Depends(dependencies.get_product_image_submission_service)
    ),
) -> common_schema.SuccessResponse[
    submission_schema.ProductImageSubmissionDetail
]:
    """구성한 초안을 최종 승인 대기열로 전송합니다."""
    try:
        return common_schema.success_response(
            await service.submit(
                submission_id,
                requester_id=user["user_id"],
                is_super_admin=_is_super_admin(user),
            )
        )
    except product_image_submission_service.SubmissionNotFoundError as error:
        raise fastapi.HTTPException(
            status_code=404, detail="등록 요청이 없습니다."
        ) from error
    except (
        product_image_submission_service.SubmissionAccessDeniedError
    ) as error:
        raise fastapi.HTTPException(
            status_code=403, detail="제출 권한이 없습니다."
        ) from error
    except product_image_submission_service.SubmissionStateError as error:
        raise fastapi.HTTPException(
            status_code=409, detail="초안만 제출할 수 있습니다."
        ) from error
    except product_image_submission_service.SubmissionValidationError as error:
        raise fastapi.HTTPException(
            status_code=422, detail=str(error)
        ) from error


@router.post(
    "/{submission_id}/approve",
    response_model=common_schema.SuccessResponse[
        submission_schema.ProductImageSubmissionDetail
    ],
)
async def approve_product_image_submission(
    submission_id: int,
    user: dependencies.AdminUser = fastapi.Depends(
        dependencies.require_super_admin
    ),
    service: product_image_submission_service.ProductImageSubmissionService = (
        fastapi.Depends(dependencies.get_product_image_submission_service)
    ),
) -> common_schema.SuccessResponse[
    submission_schema.ProductImageSubmissionDetail
]:
    """최종 관리자가 대기 요청을 SKU 카탈로그에 실제 반영합니다."""
    try:
        return common_schema.success_response(
            await service.approve(submission_id, reviewer_id=user["user_id"])
        )
    except product_image_submission_service.SubmissionNotFoundError as error:
        raise fastapi.HTTPException(
            status_code=404, detail="등록 요청이 없습니다."
        ) from error
    except product_image_submission_service.SubmissionStateError as error:
        raise fastapi.HTTPException(
            status_code=409, detail="대기 요청만 승인할 수 있습니다."
        ) from error
    except (
        product_image_submission_service.SubmissionSkuCodeConflictError
    ) as error:
        raise fastapi.HTTPException(
            status_code=409, detail="이미 사용 중인 SKU 코드입니다."
        ) from error


@router.post(
    "/{submission_id}/reject",
    response_model=common_schema.SuccessResponse[
        submission_schema.ProductImageSubmissionDetail
    ],
)
async def reject_product_image_submission(
    submission_id: int,
    body: submission_schema.RejectProductImageSubmissionRequest,
    user: dependencies.AdminUser = fastapi.Depends(
        dependencies.require_super_admin
    ),
    service: product_image_submission_service.ProductImageSubmissionService = (
        fastapi.Depends(dependencies.get_product_image_submission_service)
    ),
) -> common_schema.SuccessResponse[
    submission_schema.ProductImageSubmissionDetail
]:
    """최종 관리자가 사유를 남기고 대기 요청을 반려합니다."""
    try:
        return common_schema.success_response(
            await service.reject(
                submission_id,
                reject_reason=body.reject_reason,
                reviewer_id=user["user_id"],
            )
        )
    except product_image_submission_service.SubmissionNotFoundError as error:
        raise fastapi.HTTPException(
            status_code=404, detail="등록 요청이 없습니다."
        ) from error
    except product_image_submission_service.SubmissionStateError as error:
        raise fastapi.HTTPException(
            status_code=409, detail="대기 요청만 반려할 수 있습니다."
        ) from error
