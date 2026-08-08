import io
from PIL import Image, ImageOps, UnidentifiedImageError

class InvalidImageError(ValueError):
    """업로드된 이미지가 유효하지 않을 때 발생합니다."""


def decode_image(image_bytes: bytes) -> Image.Image:
    if not image_bytes:
        raise InvalidImageError("이미지 바이트가 비어 있습니다.")

    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            if  img.format not in {"JPEG", "PNG"}:
                raise InvalidImageError(
                    "JPEG 이미지나 PNG  이미지만 가능합니다."
                )
            img.load()
            normalized = ImageOps.exif_transpose(img)
            return normalized.convert("RGB")

    except (OSError, UnidentifiedImageError) as error:
        raise InvalidImageError("이미지를 열 수 없습니다. 유효한 이미지 파일인지 확인하세요.")