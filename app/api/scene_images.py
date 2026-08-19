"""연출 이미지 업로드와 비동기 분석 작업 접수 API입니다."""

import logging
import pathlib
import uuid

import fastapi
import sqlalchemy

from app.api.examples import (
    SCENE_IMAGE_INVALID_IMAGE_RESPONSE,
    SCENE_IMAGE_TOO_LARGE_RESPONSE,
    SCENE_IMAGE_UNSUPPORTED_TYPE_RESPONSE,
    SCENE_IMAGE_UPLOAD_FAILED_RESPONSE,
    SCENE_IMAGE_UPLOAD_ACCEPTED_RESPONSE,
)
from app.core import config, database
from app.models.ai_job import AiJobType
from app.repositories import ai_job_repository
from app.schemas import ai_job as ai_job_schema
from app.schemas import common as common_schema
from app.services import image_validation

_LOGGER = logging.getLogger(__name__)

router = fastapi.APIRouter(
    tags=["scene-images"],
)

UPLOAD_ERROR_MESSAGE = "이미지 업로드 처리에 실패했습니다."
_IMAGE_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
}
_SELECT_FIXED_USER_ID = sqlalchemy.text("""
    SELECT user_id
    FROM app_user
    WHERE login_id = :login_id
      AND is_active = TRUE
    """)
_INSERT_SCENE_IMAGE = sqlalchemy.text("""
    INSERT INTO scene_image (
        user_id,
        image_url,
        origin_name,
        mime_type,
        file_size,
        analysis_error,
        analysis_status,
        width_px,
        height_px
    )
    VALUES (
        :user_id,
        :image_url,
        :origin_name,
        :mime_type,
        :file_size,
        :analysis_error,
        :analysis_status,
        :width_px,
        :height_px
    )
    RETURNING scene_image_id
    """)


def _save_image(path: pathlib.Path, content: bytes) -> None:
    """검증된 원본 이미지를 로컬 저장소에 기록합니다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _remove_image(path: pathlib.Path) -> None:
    """저장에 실패했거나 등록이 취소된 이미지 파일을 삭제합니다."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        _LOGGER.exception("업로드 파일 정리에 실패했습니다: %s", path)


async def _rollback(
    database_session: database.sqlalchemy_async.AsyncSession,
) -> None:
    """DB 오류 뒤에 현재 트랜잭션을 안전하게 되돌립니다."""
    try:
        await database_session.rollback()
    # 원래 업로드 오류를 유지하되 rollback 실패도 로그로 남깁니다.
    except Exception:  # pylint: disable=broad-exception-caught
        _LOGGER.exception("이미지 업로드 트랜잭션 rollback에 실패했습니다.")


@router.post(
    "/tagging",
    response_model=common_schema.SuccessResponse[
        ai_job_schema.AiJobAcceptedResponse
    ],
    status_code=fastapi.status.HTTP_202_ACCEPTED,
    summary="연출 이미지 업로드 및 가구 객체 탐지 작업 접수",
    description=(
        "multipart/form-data로 받은 연출 이미지를 검증한 뒤 원본 파일과 "
        "메타데이터를 저장하고 VLM 가구 객체 탐지 작업을 대기열에 접수합니다. "
        "탐지 결과는 즉시 반환하지 않으며, 응답의 job_id로 "
        "GET /ai-jobs/{job_id}를 폴링해 확인합니다.\n\n"
        "- 허용 형식: JPEG, PNG (파일의 실제 형식과 MIME 타입이 일치해야 합니다)\n"
        "- 최대 용량: 10MB\n"
        "- 202 Accepted는 분석 완료가 아닌 작업 접수 완료를 뜻합니다.\n"
        "- 검증·저장 실패 시 업로드된 파일과 DB 기록은 함께 정리됩니다."
    ),
    response_description=(
        "공통 성공 응답으로 연출 이미지 ID와 대기 중인 AI 작업 ID를 반환합니다."
    ),
    responses={
        202: SCENE_IMAGE_UPLOAD_ACCEPTED_RESPONSE,
        413: SCENE_IMAGE_TOO_LARGE_RESPONSE,
        415: SCENE_IMAGE_UNSUPPORTED_TYPE_RESPONSE,
        422: SCENE_IMAGE_INVALID_IMAGE_RESPONSE,
        500: SCENE_IMAGE_UPLOAD_FAILED_RESPONSE,
    },
)
# 보상 트랜잭션 상태를 유지하므로 지역 변수가 많습니다.
async def upload_scene_image(  # pylint: disable=too-many-locals
    file: fastapi.UploadFile = fastapi.File(
        ...,
        description=(
            "업로드할 연출 이미지 파일입니다. JPEG 또는 PNG, 10MB 이하."
        ),
    ),
    database_session: database.sqlalchemy_async.AsyncSession = fastapi.Depends(
        database.get_database_session
    ),
) -> common_schema.SuccessResponse[ai_job_schema.AiJobAcceptedResponse]:
    """이미지를 저장하고 가구 탐지 작업을 비동기로 접수합니다.

    검증, 파일 저장, DB 기록과 탐지 상태 전환을 하나의 보상 트랜잭션으로
    관리하므로 지역 변수를 단계별로 유지합니다.

    Args:
        file: multipart/form-data의 이미지 파일입니다.
        database_session: 요청 범위에서 사용하는 PostgreSQL 세션입니다.

    Returns:
        저장된 scene_image ID와 대기 작업 UUID입니다.

    Raises:
        fastapi.HTTPException: 이미지 검증 또는 저장에 실패한 경우입니다.
    """
    saved_path: pathlib.Path | None = None
    try:
        try:
            validated = await image_validation.validate_image(file)
        except image_validation.ImageValidationError as error:
            raise fastapi.HTTPException(
                status_code=error.status_code,
                detail=str(error),
            ) from error

        settings = config.get_settings()
        user_result = await database_session.execute(
            _SELECT_FIXED_USER_ID,
            {"login_id": settings.mvp_login_id},
        )
        user_id = user_result.scalar_one_or_none()
        if user_id is None:
            _LOGGER.error("활성 MVP 사용자의 ID를 확인할 수 없습니다.")
            raise fastapi.HTTPException(
                status_code=500,
                detail=UPLOAD_ERROR_MESSAGE,
            )

        extension = _IMAGE_EXTENSIONS[validated.metadata.mime_type]
        filename = f"{uuid.uuid4()}.{extension}"
        saved_path = (
            pathlib.Path(settings.image_storage_root)
            / "scene-images"
            / filename
        )
        _save_image(saved_path, validated.content)

        image_url = f"/uploads/scene-images/{filename}"
        result = await database_session.execute(
            _INSERT_SCENE_IMAGE,
            {
                "user_id": int(user_id),
                "image_url": image_url,
                "origin_name": validated.metadata.origin_name,
                "mime_type": validated.metadata.mime_type,
                "file_size": validated.metadata.file_size,
                "analysis_error": None,
                "analysis_status": "pending",
                "width_px": validated.metadata.width_px,
                "height_px": validated.metadata.height_px,
            },
        )
        scene_image_id = int(result.scalar_one())
        job = await ai_job_repository.create_job(
            database_session,
            scene_image_id,
            AiJobType.DETECT_SCENE,
            input_payload={"image_url": image_url},
        )
    except fastapi.HTTPException:
        raise
    # 파일 시스템과 DB 오류 모두 같은 보상 정리 절차가 필요합니다.
    except Exception as error:  # pylint: disable=broad-exception-caught
        await _rollback(database_session)
        if saved_path is not None:
            _remove_image(saved_path)
        raise fastapi.HTTPException(
            status_code=500,
            detail=UPLOAD_ERROR_MESSAGE,
        ) from error
    finally:
        await file.close()

    return common_schema.success_response(
        ai_job_schema.AiJobAcceptedResponse(
            scene_image_id=scene_image_id,
            job_id=job.job_id,
        )
    )
