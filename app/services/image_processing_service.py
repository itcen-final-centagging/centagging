"""장면 이미지에서 탐지 객체 영역을 잘라내는 서비스입니다."""

from PIL import Image


def get_crop_image(image: Image.Image, bbox: dict[str, float]) -> Image.Image:
    """0~1000 정규화 좌표로 이미지에서 탐지 객체 영역을 잘라냅니다.

    Args:
        image: 원본 장면 이미지입니다.
        bbox: `xmin`, `ymin`, `xmax`, `ymax` 키를 가진 0~1000 정규화
            좌표입니다.

    Returns:
        bbox 영역만큼 잘라낸 이미지입니다.
    """
    left = round(bbox["xmin"] / 1000 * image.width)
    right = round(bbox["xmax"] / 1000 * image.width)
    upper = round(bbox["ymin"] / 1000 * image.height)
    lower = round(bbox["ymax"] / 1000 * image.height)

    return image.crop((left, upper, right, lower))
