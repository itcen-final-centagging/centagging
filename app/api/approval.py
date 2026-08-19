"""최종 관리자의 태깅 결과 승인 API입니다."""

import typing

import fastapi

from app import dependencies
from app.schemas import approval as approval_schema
from app.schemas import common as common_schema
from app.services import approval_service

router = fastapi.APIRouter(prefix="/approvals", tags=["approvals"])


@router.get(
    "",
    response_model=common_schema.SuccessResponse[
        approval_schema.ApprovalListResponse
    ],
)
async def list_approvals(
    status: typing.Literal["PENDING", "ACTIVE", "REJECTED", "ALL"] = "PENDING",
    _: dependencies.AdminUser = fastapi.Depends(dependencies.get_admin_user),
    service: approval_service.ApprovalService = fastapi.Depends(
        dependencies.get_approval_service
    ),
) -> common_schema.SuccessResponse[approval_schema.ApprovalListResponse]:
    """관리자가 상태별 승인 요청 목록을 조회합니다."""
    return common_schema.success_response(await service.list_approvals(status))


@router.get(
    "/{request_id}",
    response_model=common_schema.SuccessResponse[
        approval_schema.ApprovalDetailResponse
    ],
)
async def get_approval_detail(
    request_id: int,
    _: dependencies.AdminUser = fastapi.Depends(dependencies.get_admin_user),
    service: approval_service.ApprovalService = fastapi.Depends(
        dependencies.get_approval_service
    ),
) -> common_schema.SuccessResponse[approval_schema.ApprovalDetailResponse]:
    """승인 요청 한 건의 원본·객체·SKU 상세를 조회합니다."""
    try:
        return common_schema.success_response(
            await service.get_detail(request_id)
        )
    except approval_service.ApprovalNotFoundError as error:
        raise fastapi.HTTPException(
            status_code=404, detail="승인 요청이 없습니다."
        ) from error


@router.post(
    "/{request_id}/confirm",
    response_model=common_schema.SuccessResponse[
        approval_schema.ConfirmResponse
    ],
)
async def confirm_approval(
    request_id: int,
    user: dependencies.AdminUser = fastapi.Depends(
        dependencies.require_super_admin
    ),
    service: approval_service.ApprovalService = fastapi.Depends(
        dependencies.get_approval_service
    ),
) -> common_schema.SuccessResponse[approval_schema.ConfirmResponse]:
    """최종 관리자가 객체 크롭을 SKU 스타일링 이미지로 승인합니다."""
    try:
        return common_schema.success_response(
            await service.confirm(
                request_id,
                user["user_id"],
                user["user_name"],
            )
        )
    except approval_service.ApprovalNotFoundError as error:
        raise fastapi.HTTPException(
            status_code=404, detail="승인 요청이 없습니다."
        ) from error
    except approval_service.AlreadyReviewedError as error:
        raise fastapi.HTTPException(
            status_code=409, detail="이미 처리된 요청입니다."
        ) from error


@router.post(
    "/{request_id}/reject",
    response_model=common_schema.SuccessResponse[
        approval_schema.RejectResponse
    ],
)
async def reject_approval(
    request_id: int,
    body: approval_schema.RejectRequest,
    user: dependencies.AdminUser = fastapi.Depends(
        dependencies.require_super_admin
    ),
    service: approval_service.ApprovalService = fastapi.Depends(
        dependencies.get_approval_service
    ),
) -> common_schema.SuccessResponse[approval_schema.RejectResponse]:
    """최종 관리자가 사유와 함께 승인 요청을 반려합니다."""
    try:
        return common_schema.success_response(
            await service.reject(
                request_id,
                body.reject_reason,
                user["user_id"],
                user["user_name"],
            )
        )
    except approval_service.ApprovalNotFoundError as error:
        raise fastapi.HTTPException(
            status_code=404, detail="승인 요청이 없습니다."
        ) from error
    except approval_service.AlreadyReviewedError as error:
        raise fastapi.HTTPException(
            status_code=409, detail="이미 처리된 요청입니다."
        ) from error
