"""SKU 이미지의 저장 경로와 공개 URL을 변환합니다."""

import io
import logging
import pathlib
import urllib.parse

from PIL import Image

_LEGACY_PREFIX = "data/images/"
_PUBLIC_PREFIX = "/sku-images/"
_UPLOAD_PUBLIC_PREFIX = "/uploads/"
_LOGGER = logging.getLogger(__name__)


class SkuImageStorage:
    """SKU 이미지 저장 키를 로컬 파일과 공개 URL로 해석합니다."""

    def __init__(self, root: str | pathlib.Path) -> None:
        """SKU 이미지 루트 경로를 설정합니다.

        Args:
            root: SKU 이미지가 저장된 로컬 디렉터리입니다.
        """
        self.root = pathlib.Path(root)

    def public_url(self, stored_path: str) -> str:
        """DB 저장 경로를 브라우저에서 접근할 URL로 변환합니다.

        Args:
            stored_path: DB의 ``sku_image.image_url`` 값입니다.

        Returns:
            ``/sku-images`` 경로 또는 기존 ``/uploads`` 공개 URL입니다.
        """
        normalized_path = urllib.parse.unquote(stored_path).replace("\\", "/")
        if normalized_path.startswith(_UPLOAD_PUBLIC_PREFIX):
            return urllib.parse.quote(normalized_path, safe="/")
        key = self._normalize_key(normalized_path)
        return _PUBLIC_PREFIX + urllib.parse.quote(key, safe="/")

    def storage_key(self, image_path: str | pathlib.Path) -> str:
        """로컬 이미지 경로를 저장 루트 기준 키로 변환합니다.

        Args:
            image_path: SKU 이미지 파일의 로컬 경로입니다.

        Returns:
            슬래시로 구분된 저장 루트 기준 상대 경로입니다.

        Raises:
            ValueError: 이미지가 설정된 저장 루트 밖에 있을 때 발생합니다.
        """
        try:
            relative_path = (
                pathlib.Path(image_path)
                .resolve()
                .relative_to(self.root.resolve())
            )
        except ValueError as error:
            raise ValueError("SKU 이미지가 저장 루트 밖에 있습니다.") from error
        return relative_path.as_posix()

    def read_jpeg(self, stored_path: str) -> bytes | None:
        """DB 저장 경로의 이미지를 JPEG 바이트로 읽습니다.

        Args:
            stored_path: DB의 ``sku_image.image_url`` 값입니다.

        Returns:
            JPEG 바이트이며 파일을 읽지 못하면 None입니다.
        """
        try:
            key = self._normalize_key(stored_path)
            path = self.root.joinpath(*key.split("/"))
            with Image.open(path) as image:
                buffer = io.BytesIO()
                image.convert("RGB").save(buffer, format="JPEG", quality=90)
                return buffer.getvalue()
        except (OSError, ValueError):
            _LOGGER.warning("SKU 이미지를 읽지 못했습니다: %s", stored_path)
            return None

    @staticmethod
    def _normalize_key(stored_path: str) -> str:
        key = urllib.parse.unquote(stored_path).replace("\\", "/").lstrip("/")
        if key.startswith(_LEGACY_PREFIX):
            key = key.removeprefix(_LEGACY_PREFIX)
        if key.startswith(_PUBLIC_PREFIX.lstrip("/")):
            key = key.removeprefix(_PUBLIC_PREFIX.lstrip("/"))
        if key.startswith(_UPLOAD_PUBLIC_PREFIX.lstrip("/")):
            key = key.removeprefix(_UPLOAD_PUBLIC_PREFIX.lstrip("/"))
        if not key or ".." in pathlib.PurePosixPath(key).parts:
            raise ValueError("올바르지 않은 SKU 이미지 경로입니다.")
        return key
