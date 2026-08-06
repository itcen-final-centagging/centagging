"""상품 수집 흐름을 묶는 모듈입니다. / Orchestrates the crawling flow."""

import logging
import os
import pathlib
from typing import Optional

from crawl import config
from crawl import fetcher as fetcher_module
from crawl import models, parser, storage

_LOGGER = logging.getLogger(__name__)


class OhouseCrawler:
    """오늘의집 상품 페이지를 수집합니다. / Crawls ohou.se product pages."""

    def __init__(
        self,
        output_dir: pathlib.Path = config.DEFAULT_OUTPUT_DIR,
        fetcher: Optional[fetcher_module.Fetcher] = None,
    ) -> None:
        """저장 경로와 HTTP 클라이언트를 준비합니다.

        Args:
            output_dir: 결과를 저장할 최상위 디렉터리입니다.
            fetcher: 재사용할 Fetcher이며 없으면 새로 만듭니다.
        """
        self._output_dir = output_dir
        self._fetcher = fetcher or fetcher_module.Fetcher()

    def crawl_goods(
        self, goods_id: int, image_limit: int = 0
    ) -> models.Product:
        """상품 하나를 수집해 JSON과 이미지를 저장합니다.

        Args:
            goods_id: 오늘의집 상품 번호입니다.
            image_limit: 내려받을 이미지 수이며 0이면 받지 않습니다.

        Returns:
            수집한 Product 객체입니다.

        Raises:
            parser.ParseError: 페이지에서 상품 데이터를 찾지 못했을 때입니다.
            curl_cffi.requests.RequestsError: 페이지 요청이 실패했을 때입니다.
        """
        url = config.GOODS_URL_TEMPLATE.format(goods_id=goods_id)
        html = self._fetcher.fetch_text(url)
        product = parser.parse_product(html, url)
        json_path = storage.save_product(product, self._output_dir)
        _LOGGER.info(
            "상품 %s 저장 완료: %s (이미지 후보 %d장)",
            goods_id,
            json_path,
            len(product.images),
        )
        if image_limit > 0:
            saved = storage.download_images(
                product, self._output_dir, self._fetcher, image_limit
            )
            _LOGGER.info("이미지 %d장 저장 완료", len(saved))
        return product

    def crawl_app_info(self) -> Optional[models.AppInfo]:
        """Airbridge 설정에서 앱 메타데이터를 수집합니다.

        Returns:
            수집한 AppInfo이며 토큰이 없으면 None입니다.
        """
        web_token = os.getenv(config.AIRBRIDGE_TOKEN_ENV, "")
        if not web_token:
            _LOGGER.warning(
                "%s 환경변수가 없어 앱 메타데이터 수집을 건너뜁니다.",
                config.AIRBRIDGE_TOKEN_ENV,
            )
            return None
        payload = self._fetcher.fetch_json(
            config.AIRBRIDGE_CONFIG_URL, params={"webToken": web_token}
        )
        app_info = parser.parse_app_info(payload)
        storage.save_app_info(app_info, self._output_dir)
        return app_info

    def close(self) -> None:
        """내부 HTTP 세션을 정리합니다."""
        self._fetcher.close()
