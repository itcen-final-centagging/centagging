"""업로드 이미지 디코딩과 탐지 객체 영역 크롭을 제공합니다."""

import dataclasses
import io
import pathlib

from PIL import Image, ImageOps, UnidentifiedImageError

from app.schemas.tagging import BoundingBox


class InvalidImageError(ValueError):
    """업로드된 이미지가 유효하지 않을 때 발생합니다."""


@dataclasses.dataclass(frozen=True)
class CroppedObject:
    """장면 이미지에서 잘라낸 탐지 객체 1건입니다.

    Attributes:
        crop_index: ``scene_image.bbox_coord`` 배열의 인덱스입니다.
        bbox: 응답 스키마에 그대로 넣을 정규화 좌표입니다.
        image: 임베딩 호출에 사용할 PIL 이미지입니다.
        image_bytes: XAI 채점에 사용할 JPEG 바이트입니다.
    """

    crop_index: int
    bbox: BoundingBox
    image: Image.Image
    image_bytes: bytes


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
    left = round(bbox["xmin"] / 1000 * image.width)
    right = round(bbox["xmax"] / 1000 * image.width)
    upper = round(bbox["ymin"] / 1000 * image.height)
    lower = round(bbox["ymax"] / 1000 * image.height)

    return image.crop((left, upper, right, lower))


def crop_scene_objects(
    image_path: pathlib.Path,
    bbox_coords: list[dict[str, float]],
) -> list[CroppedObject]:
    """장면 이미지를 열어 bbox 목록만큼 탐지 객체를 잘라냅니다.

    Args:
        image_path: 장면 원본 이미지 경로입니다.
        bbox_coords: 0~1000 정규화 좌표 목록입니다.

    Returns:
        crop_index 오름차순의 크롭 결과 목록입니다.

    Raises:
        InvalidImageError: 원본 장면 이미지를 열 수 없는 경우입니다.
    """
    try:
        with Image.open(image_path) as scene_image:
            scene_image.load()
            return [
                _build_cropped_object(scene_image, index, bbox)
                for index, bbox in enumerate(bbox_coords)
            ]
    except (OSError, UnidentifiedImageError) as error:
        raise InvalidImageError(
            "장면 이미지를 열 수 없습니다. 저장된 경로를 확인하세요."
        ) from error


def _build_cropped_object(
    scene_image: Image.Image,
    crop_index: int,
    bbox: dict[str, float],
) -> CroppedObject:
    """크롭 1건과 채점용 JPEG 바이트를 함께 만듭니다.

    Args:
        scene_image: 열려 있는 장면 원본 이미지입니다.
        crop_index: ``bbox_coords`` 배열에서의 인덱스입니다.
        bbox: 0~1000 정규화 좌표입니다.

    Returns:
        임베딩용 이미지와 채점용 바이트를 담은 크롭 결과입니다.
    """
    crop_image = get_crop_image(image=scene_image, bbox=bbox)
    return CroppedObject(
        crop_index=crop_index,
        bbox=BoundingBox(**bbox),
        image=crop_image,
        image_bytes=parse_image_to_bytes(crop_image),
    )


def parse_image_to_bytes(image: Image.Image) -> bytes:
    """PIL 이미지를 JPEG 바이트로 변환합니다. (크롭 이미지용)"""
    buf = io.BytesIO()
    image.convert("RGB").save(
        buf, format="JPEG", optimize=True
    )  # ← convert 추가
    return buf.getvalue()


def read_sku_image_bytes(image_url: str) -> bytes | None:
    """sku_image.image_url이 가리키는 파일을 JPEG 바이트로 읽습니다.

    Args:
        image_url: sku_image 테이블의 image_url 값입니다.

    Returns:
        JPEG 바이트이며, 파일을 못 읽으면 None입니다.
        후보 1건이 실패해도 나머지 채점은 계속하도록 예외 대신 None입니다.
    """
    try:
        with Image.open(pathlib.Path(image_url)) as sku_image:
            buf = io.BytesIO()
            sku_image.convert("RGB").save(buf, format="JPEG", quality=90)
            return buf.getvalue()
    except OSError:
        return None
