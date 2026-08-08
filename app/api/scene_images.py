"""연출 이미지 업로드와 유효성 검증 API입니다."""

import fastapi
import pydantic

from app.services import image_validation

router = fastapi.APIRouter(
    tags=["scene-images"],
)


class ImageValidationResponse(pydantic.BaseModel):
    """검증을 통과한 업로드 이미지의 메타데이터입니다."""

    status: str
    image: image_validation.ImageMetadata


@router.post("/tagging", response_model=ImageValidationResponse)
async def upload_scene_image(
    file: fastapi.UploadFile = fastapi.File(...),
) -> ImageValidationResponse:
    """연출 이미지 파일을 받아 형식, 용량 및 이미지 데이터를 검증합니다.

    Args:
        file: multipart/form-data의 이미지 파일입니다.

    Returns:
        검증 상태와 디코딩된 이미지 메타데이터입니다.

    Raises:
        fastapi.HTTPException: 업로드 파일이 검증 조건을 위반한 경우입니다.
    """
    try:
        validated = await image_validation.validate_image(file)
    except image_validation.ImageValidationError as error:
        raise fastapi.HTTPException(
            status_code=error.status_code,
            detail=str(error),
        ) from error
    finally:
        await file.close()

    return ImageValidationResponse(
        status="validated",
        image=validated.metadata,
    )
