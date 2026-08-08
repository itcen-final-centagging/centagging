"""업로드 이미지 파일의 유효성을 검사합니다."""

import dataclasses
import io

import fastapi
import PIL
import PIL.Image

MAX_FILE_SIZE = 10 * 1024 * 1024
ALLOWED_IMAGE_FORMATS = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
}


class ImageValidationError(ValueError):
    """업로드 이미지가 허용 조건을 충족하지 못한 경우 발생합니다."""

    def __init__(self, message: str, status_code: int = 422) -> None:
        """검증 오류 메시지와 HTTP 상태 코드를 저장합니다.

        Args:
            message: 사용자에게 전달할 검증 실패 사유입니다.
            status_code: API 응답에 사용할 HTTP 상태 코드입니다.
        """
        super().__init__(message)
        self.status_code = status_code


@dataclasses.dataclass(frozen=True)
class ImageMetadata:
    """디코딩으로 확인한 이미지 메타데이터입니다."""

    origin_name: str
    mime_type: str
    file_size: int
    width_px: int
    height_px: int


@dataclasses.dataclass(frozen=True)
class ValidatedImage:
    """검증을 통과한 원본 바이트와 이미지 메타데이터입니다."""

    content: bytes = dataclasses.field(repr=False)
    metadata: ImageMetadata


async def validate_image(upload: fastapi.UploadFile) -> ValidatedImage:
    """JPEG 또는 PNG 업로드의 크기와 실제 이미지 정보를 검증합니다.

    Args:
        upload: multipart/form-data로 전달된 이미지 파일입니다.

    Returns:
        후속 처리에 사용할 원본 바이트와 이미지 메타데이터입니다.

    Raises:
        ImageValidationError: 파일이 업로드 허용 조건을 위반한 경우입니다.
    """
    if upload.content_type not in ALLOWED_IMAGE_FORMATS.values():
        raise ImageValidationError(
            "JPEG 또는 PNG 이미지만 업로드할 수 있습니다.",
            status_code=415,
        )

    content = await upload.read(MAX_FILE_SIZE + 1)
    if len(content) > MAX_FILE_SIZE:
        raise ImageValidationError(
            "이미지 파일은 10MB 이하여야 합니다.",
            status_code=413,
        )

    try:
        with PIL.Image.open(io.BytesIO(content)) as image:
            image.load()
            image_format = image.format
            width_px, height_px = image.size
    except (
        PIL.Image.DecompressionBombError,
        OSError,
        PIL.UnidentifiedImageError,
    ) as error:
        raise ImageValidationError("유효한 이미지 파일이 아닙니다.") from error

    actual_mime_type = ALLOWED_IMAGE_FORMATS.get(image_format or "")
    if actual_mime_type is None or actual_mime_type != upload.content_type:
        raise ImageValidationError(
            "파일의 실제 이미지 형식과 MIME 타입이 일치하지 않습니다.",
            status_code=415,
        )

    return ValidatedImage(
        content=content,
        metadata=ImageMetadata(
            origin_name=upload.filename or "upload",
            mime_type=actual_mime_type,
            file_size=len(content),
            width_px=width_px,
            height_px=height_px,
        ),
    )
