"""수집 결과를 파일로 저장합니다. / Persists crawled results to files."""

import json
import logging
import pathlib
import urllib.parse

from curl_cffi import requests as curl_requests

from crawl import fetcher as fetcher_module
from crawl import models

_LOGGER = logging.getLogger(__name__)

# 저장할 때 인정하는 이미지 확장자입니다. / Accepted image file extensions.
_ALLOWED_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif")

# Content-Type과 확장자 대응표입니다. / Content type to extension mapping.
_CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/avif": ".avif",
}

# 확장자를 알 수 없을 때 사용할 값입니다. / Fallback file extension.
_DEFAULT_EXTENSION = ".jpg"


def save_product(
    product: models.Product, output_dir: pathlib.Path
) -> pathlib.Path:
    """상품 정보를 JSON 파일로 저장합니다.

    Args:
        product: 저장할 상품 정보입니다.
        output_dir: 결과를 모아둘 최상위 디렉터리입니다.

    Returns:
        저장한 JSON 파일 경로입니다.
    """
    product_dir = output_dir / str(product.goods_id)
    product_dir.mkdir(parents=True, exist_ok=True)
    json_path = product_dir / "product.json"
    json_path.write_text(
        json.dumps(product.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return json_path


def save_app_info(
    app_info: models.AppInfo, output_dir: pathlib.Path
) -> pathlib.Path:
    """앱 메타데이터를 JSON 파일로 저장합니다.

    Args:
        app_info: 저장할 앱 메타데이터입니다.
        output_dir: 결과를 모아둘 최상위 디렉터리입니다.

    Returns:
        저장한 JSON 파일 경로입니다.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "app_info.json"
    json_path.write_text(
        json.dumps(app_info.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return json_path


def download_images(
    product: models.Product,
    output_dir: pathlib.Path,
    fetcher: fetcher_module.Fetcher,
    limit: int,
) -> list[pathlib.Path]:
    """상품 이미지를 내려받아 파일로 저장합니다.

    Args:
        product: 이미지 목록을 가진 상품 정보입니다.
        output_dir: 결과를 모아둘 최상위 디렉터리입니다.
        fetcher: 이미지 요청에 사용할 Fetcher입니다.
        limit: 내려받을 최대 이미지 수입니다.

    Returns:
        저장에 성공한 이미지 파일 경로 목록입니다.
    """
    image_dir = output_dir / str(product.goods_id) / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    saved_paths: list[pathlib.Path] = []
    manifest: list[dict[str, str]] = []
    for index, image in enumerate(product.images[:limit]):
        try:
            content, content_type = fetcher.fetch_image(image.url)
        except curl_requests.RequestsError as error:
            # 이미지 한 장의 실패로 전체 수집을 멈추지 않습니다.
            _LOGGER.warning("이미지 저장 실패 %s: %s", image.url, error)
            continue
        file_name = (
            f"{index:03d}_{image.role}"
            f"{_guess_extension(image.url, content_type)}"
        )
        file_path = image_dir / file_name
        file_path.write_bytes(content)
        saved_paths.append(file_path)
        manifest.append(
            {
                "file_name": file_name,
                "role": image.role,
                "url": image.url,
                "source": image.source,
            }
        )
    manifest_path = image_dir / "index.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return saved_paths


def _guess_extension(url: str, content_type: str) -> str:
    """응답 형식과 주소를 보고 확장자를 정합니다.

    Args:
        url: 이미지 주소입니다.
        content_type: 응답의 Content-Type 헤더 값입니다.

    Returns:
        점을 포함한 확장자 문자열입니다.
    """
    media_type = content_type.split(";")[0].strip().lower()
    if media_type in _CONTENT_TYPE_EXTENSIONS:
        return _CONTENT_TYPE_EXTENSIONS[media_type]
    path = urllib.parse.urlparse(url).path
    suffix = pathlib.PurePosixPath(path).suffix.lower()
    if suffix in _ALLOWED_EXTENSIONS:
        return suffix
    return _DEFAULT_EXTENSION
