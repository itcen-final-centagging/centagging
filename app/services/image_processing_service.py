"""업로드 이미지 디코딩과 탐지 객체 영역 크롭을 제공합니다."""

import io

from PIL import Image, ImageOps, UnidentifiedImageError


class InvalidImageError(ValueError):
    """업로드된 이미지가 유효하지 않을 때 발생합니다."""

class InvalidBoundingBoxError(ValueError):
    """bounding box 좌표가 유효하지 않을 때 발생합니다."""


def decode_image(image_bytes: bytes) -> Image.Image:
    """이미지 바이트를 RGB PIL 이미지로 변환합니다.

    Args:
        image_bytes: JPEG 또는 PNG 이미지 바이트입니다.

    Returns:
        방향이 보정된 RGB 이미지입니다.

    Raises:
        InvalidImageError: 이미지가 비었거나 유효하지 않은 경우입니다.
    """
    if not image_bytes:
        raise InvalidImageError("이미지 바이트가 비어 있습니다.")

    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            if img.format not in {"JPEG", "PNG"}:
                raise InvalidImageError(
                    "JPEG 이미지나 PNG  이미지만 가능합니다."
                )
            img.load()
            normalized = ImageOps.exif_transpose(img)
            return normalized.convert("RGB")

    except (OSError, UnidentifiedImageError) as error:
        raise InvalidImageError(
            "이미지를 열 수 없습니다. 유효한 이미지 파일인지 확인하세요."
        ) from error


def get_crop_image(image: Image.Image, bbox: dict[str, float]) -> Image.Image:
    """0~1000 정규화 좌표로 이미지에서 탐지 객체 영역을 잘라냅니다.

    Args:
        image: 원본 장면 이미지입니다.
        bbox: `xmin`, `ymin`, `xmax`, `ymax` 키를 가진 0~1000 정규화
            좌표입니다.

    Returns:
        bbox 영역만큼 잘라낸 이미지입니다.
    """
    xmin = bbox["xmin"]
    ymin = bbox["ymin"]
    xmax = bbox["xmax"]
    ymax = bbox["ymax"]

    if not (0<= xmin < xmax <= 1000):
        raise InvalidBoundingBoxError(
            "bbox는 0 <= xmin < xmax <= 1000을 만족해야 합니다."
        )

    if not (0 <= ymin < ymax <= 1000):
        raise InvalidBoundingBoxError(
            "bbox는 0 <= ymin < ymax <= 1000을 만족해야 합니다."
        )

    left = round(xmin / 1000 * image.width)
    right = round(xmax / 1000 * image.width)
    upper = round(ymin / 1000 * image.height)
    lower = round(ymax / 1000 * image.height)

    if left >= right or upper >= lower:
        raise InvalidBoundingBoxError(
            "픽셀 변환 후 크롭 영역의 폭 또는 높이가 0입니다."
        )

    return image.crop((left, upper, right, lower))
