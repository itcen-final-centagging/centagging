"""승인 요청(연출 이미지 태깅 결과 검수) API입니다."""

import datetime
import typing

import fastapi

from app.dependencies import get_approval_service
from app.schemas import approval as approval_schema
from app.services import approval_service

router = fastapi.APIRouter(prefix="/approvals", tags=["approvals"])

_NOT_FOUND = {
    "code": "APPROVAL_NOT_FOUND",
    "message": "승인 요청을 찾을 수 없습니다.",
}
_ALREADY_REVIEWED = {
    "code": "ALREADY_REVIEWED",
    "message": "이미 승인 또는 반려된 요청입니다.",
}
_NO_REGISTRABLE_CROP = {
    "code": "NO_REGISTRABLE_CROP",
    "message": "등록 가능한 크롭이 없습니다.",
}
_REJECT_REASON_REQUIRED = {
    "code": "REJECT_REASON_REQUIRED",
    "message": "반려 사유를 입력해야 합니다.",
}


@router.get("", response_model=approval_schema.ApprovalListResponse)
async def list_approvals(
    status: typing.Literal["PENDING", "ACTIVE", "REJECTED", "ALL"] = (
        "PENDING"
    ),
    requested_from: typing.Optional[datetime.datetime] = fastapi.Query(
        default=None, alias="requestedFrom"
    ),
    requested_to: typing.Optional[datetime.datetime] = fastapi.Query(
        default=None, alias="requestedTo"
    ),
    service: approval_service.ApprovalService = fastapi.Depends(
        get_approval_service
    ),
) -> approval_schema.ApprovalListResponse:
    """조건에 맞는 승인 요청 전체 목록을 최신 요청순으로 조회합니다.

    프론트가 무한 스크롤로 소비하므로 페이지네이션은 없습니다.

    Args:
        status: PENDING | ACTIVE | REJECTED | ALL 중 하나입니다.
        requested_from: 이 시각 이후 요청된 건만 조회합니다.
        requested_to: 이 시각 이전 요청된 건만 조회합니다.
        service: 승인 요청 조회·처리 서비스입니다.

    Returns:
        승인 요청 목록입니다.
    """
    return await service.list_approvals(status, requested_from, requested_to)


@router.get(
    "/{request_id}", response_model=approval_schema.ApprovalDetailResponse
)
async def get_approval_detail(
    request_id: int,
    service: approval_service.ApprovalService = fastapi.Depends(
        get_approval_service
    ),
) -> approval_schema.ApprovalDetailResponse:
    """승인 요청 1건을 객체 단위 매핑과 함께 조회합니다.

    Args:
        request_id: 조회할 승인 요청 ID입니다.
        service: 승인 요청 조회·처리 서비스입니다.

    Returns:
        연출 이미지·객체별 매칭 정보·승인 가능 여부가 담긴 상세입니다.

    Raises:
        fastapi.HTTPException: 요청이 없는 경우(404)입니다.
    """
    try:
        return await service.get_detail(request_id)
    except approval_service.ApprovalNotFoundError as error:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND
        ) from error


@router.post(
    "/{request_id}/confirm", response_model=approval_schema.ConfirmResponse
)
async def confirm_approval(
    request_id: int,
    service: approval_service.ApprovalService = fastapi.Depends(
        get_approval_service
    ),
) -> approval_schema.ConfirmResponse:
    """승인 요청을 확정하고 크롭을 SKU 이미지로 등록합니다.

    Args:
        request_id: 확정할 승인 요청 ID입니다.
        service: 승인 요청 조회·처리 서비스입니다.

    Returns:
        승인 상태와, 새로 등록됐다면 그 SKU 이미지 정보입니다. 이 크롭이
        해당 SKU에 이미 등록돼 있었다면 재등록하지 않고 건너뜁니다.

    Raises:
        fastapi.HTTPException: 요청이 없거나(404), 이미 처리됐거나(409),
            등록 가능한 크롭이 없는 경우(422)입니다.
    """
    try:
        return await service.confirm(request_id)
    except approval_service.ApprovalNotFoundError as error:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND
        ) from error
    except approval_service.AlreadyReviewedError as error:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_409_CONFLICT,
            detail=_ALREADY_REVIEWED,
        ) from error
    except approval_service.NoRegistrableCropError as error:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_NO_REGISTRABLE_CROP,
        ) from error


@router.post(
    "/{request_id}/reject", response_model=approval_schema.RejectResponse
)
async def reject_approval(
    request_id: int,
    body: approval_schema.RejectRequest,
    service: approval_service.ApprovalService = fastapi.Depends(
        get_approval_service
    ),
) -> approval_schema.RejectResponse:
    """승인 요청을 반려합니다.

    Args:
        request_id: 반려할 승인 요청 ID입니다.
        body: 반려 사유가 담긴 요청 본문입니다.
        service: 승인 요청 조회·처리 서비스입니다.

    Returns:
        반려 상태와 사유가 담긴 응답입니다.

    Raises:
        fastapi.HTTPException: 반려 사유가 없거나(400), 요청이
            없거나(404), 이미 처리된 경우(409)입니다.
    """
    try:
        return await service.reject(request_id, body.reject_reason)
    except approval_service.RejectReasonRequiredError as error:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_400_BAD_REQUEST,
            detail=_REJECT_REASON_REQUIRED,
        ) from error
    except approval_service.ApprovalNotFoundError as error:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND
        ) from error
    except approval_service.AlreadyReviewedError as error:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_409_CONFLICT,
            detail=_ALREADY_REVIEWED,
        ) from error
