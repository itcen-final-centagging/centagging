"""연출 이미지 업로드, 저장 및 유효성 검증 API입니다."""

import logging
import pathlib
import uuid

import fastapi
import pydantic
import sqlalchemy

from app.core import config, database
from app.services import image_validation
from fastapi.concurrency import run_in_threadpool
from app.services import furniture_detection_service
from app.schemas.furniture_detection import DetectedObjectResponse

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


class ImageValidationResponse(pydantic.BaseModel):
    """저장된 업로드 이미지의 ID와 메타데이터입니다."""

    status: str
    scene_image_id: int
    image: image_validation.ImageMetadata
    detections: list[DetectedObjectResponse] = pydantic.Field(
        default_factory=list
    )


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


@router.post("/tagging", response_model=ImageValidationResponse)
async def upload_scene_image(
    file: fastapi.UploadFile = fastapi.File(...),
    database_session: database.sqlalchemy_async.AsyncSession = fastapi.Depends(
        database.get_database_session
    ),
) -> ImageValidationResponse:
    """이미지를 검증하고 원본 파일과 메타데이터를 함께 저장합니다.

    Args:
        file: multipart/form-data의 이미지 파일입니다.
        database_session: 요청 범위에서 사용하는 PostgreSQL 세션입니다.

    Returns:
        저장된 scene_image ID와 이미지 메타데이터입니다.

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
        await database_session.commit()
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

    try:
        detection_result = await run_in_threadpool(
            furniture_detection_service.detect_furniture_from_bytes,
            validated.content,
            settings
        )
    except Exception as error:
        raise fastapi.HTTPException(status_code = 502, detail="가구 탐지에 실패했습니다.") from error


    return ImageValidationResponse(
        status="validated",
        scene_image_id=scene_image_id,
        image=validated.metadata,
        detections=[
            DetectedObjectResponse(
                label=detection.label,
                box_2d=[
                    round(coordinate)
                    for coordinate in detection.box_2d
                ],
            )
            for detection in detection_result.detections
        ],
    )
