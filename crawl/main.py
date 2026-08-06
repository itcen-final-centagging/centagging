"""크롤러 명령줄 진입점입니다. / Command line entry point for the crawler."""

import argparse
import logging
import pathlib
import sys

from curl_cffi import requests as curl_requests

from crawl import config, ohouse_crawler
from crawl import parser as parser_module

_LOGGER = logging.getLogger("crawl")


def build_arg_parser() -> argparse.ArgumentParser:
    """명령줄 인자 정의를 만듭니다.

    Returns:
        설정을 마친 ArgumentParser 객체입니다.
    """
    arg_parser = argparse.ArgumentParser(
        prog="python -m crawl.main",
        description="오늘의집 상품 데이터와 이미지를 수집합니다.",
    )
    arg_parser.add_argument(
        "goods_ids",
        nargs="+",
        type=int,
        help="수집할 상품 번호입니다. 예: 329364",
    )
    arg_parser.add_argument(
        "--output-dir",
        type=pathlib.Path,
        default=config.DEFAULT_OUTPUT_DIR,
        help="결과를 저장할 디렉터리입니다.",
    )
    arg_parser.add_argument(
        "--images",
        action="store_true",
        help="상품 이미지를 함께 내려받습니다.",
    )
    arg_parser.add_argument(
        "--image-limit",
        type=int,
        default=config.DEFAULT_IMAGE_LIMIT,
        help="상품 한 개당 내려받을 최대 이미지 수입니다.",
    )
    arg_parser.add_argument(
        "--app-info",
        action="store_true",
        help="Airbridge 앱 메타데이터도 함께 저장합니다.",
    )
    return arg_parser


def main(argv: list[str]) -> int:
    """명령줄 인자를 읽어 상품을 수집합니다.

    Args:
        argv: 프로그램 이름을 제외한 명령줄 인자 목록입니다.

    Returns:
        모두 성공하면 0, 하나라도 실패하면 1입니다.
    """
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    args = build_arg_parser().parse_args(argv)
    crawler = ohouse_crawler.OhouseCrawler(output_dir=args.output_dir)
    image_limit = args.image_limit if args.images else 0
    has_error = False
    try:
        if args.app_info:
            crawler.crawl_app_info()
        for goods_id in args.goods_ids:
            try:
                product = crawler.crawl_goods(goods_id, image_limit)
            except (
                curl_requests.RequestsError,
                parser_module.ParseError,
            ) as error:
                # 상품 하나의 실패가 남은 목록 수집을 막지 않게 합니다.
                _LOGGER.error("상품 %s 수집 실패: %s", goods_id, error)
                has_error = True
                continue
            _LOGGER.info(
                "%s | %s | %s원 | 리뷰 %s개",
                product.goods_id,
                product.name,
                f"{product.selling_price:,}",
                f"{product.review_count:,}",
            )
    finally:
        crawler.close()
    return 1 if has_error else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
