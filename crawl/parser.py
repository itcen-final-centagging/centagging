"""BeautifulSoup으로 상품 페이지를 해석합니다. / Parses pages with BeautifulSoup."""

import datetime
import json
from typing import Any, Optional

import bs4

from crawl import config, models

# 상세 설명 HTML에서 이미지 주소가 담기는 속성들입니다. / Image URL attributes.
_IMAGE_ATTRIBUTES = ("src", "data-src", "data-original")


class ParseError(RuntimeError):
    """페이지 구조가 예상과 다를 때 발생합니다. / Raised on unexpected markup."""


def parse_product(html: str, source_url: str) -> models.Product:
    """상품 상세 페이지 HTML에서 상품 정보를 추출합니다.

    Args:
        html: 상품 상세 페이지의 HTML 문자열입니다.
        source_url: 수집한 페이지 주소입니다.

    Returns:
        태깅과 SKU 매칭에 사용할 Product 객체입니다.

    Raises:
        ParseError: 상품 데이터를 찾지 못했을 때 발생합니다.
    """
    soup = bs4.BeautifulSoup(html, "html.parser")
    goods = _extract_goods_payload(soup)
    production = goods.get("production", {})
    price = production.get("price", {})
    selling_price = int(price.get("sellingPrice", 0) or 0)
    regular_price = int(price.get("regularPrice", 0) or 0)
    return models.Product(
        goods_id=int(production.get("id", 0) or 0),
        source_url=source_url,
        crawled_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        name=str(production.get("name", "")),
        summary=_extract_summary(soup),
        brand_id=_to_optional_int(production.get("brandId")),
        brand_name=str(production.get("brandName", "")),
        category_id=_extract_category_id(goods),
        category_path=_extract_category_path(goods),
        first_option_name=str(production.get("firstDepthName", "")),
        second_option_name=str(production.get("secondDepthName", "")),
        selling_price=selling_price,
        regular_price=regular_price,
        discount_rate=_calculate_discount_rate(selling_price, regular_price),
        review_average=float(production.get("reviewAvg", 0) or 0),
        review_count=int(production.get("reviewCount", 0) or 0),
        scrap_count=int(production.get("scrapCount", 0) or 0),
        is_selling=bool(production.get("isSelling", False)),
        is_sold_out=bool(production.get("isSoldOut", False)),
        ai_attributes=_extract_ai_attributes(goods),
        specifications=_extract_specifications(production),
        options=_extract_options(production),
        images=_extract_images(goods, production),
        styling_card_urls=_extract_styling_card_urls(goods),
    )


def parse_app_info(payload: dict[str, Any]) -> models.AppInfo:
    """Airbridge 설정 응답에서 활용 가능한 값만 추립니다.

    Args:
        payload: Airbridge 설정 API가 돌려준 JSON 사전입니다.

    Returns:
        앱 이름과 마켓 주소 등을 담은 AppInfo 객체입니다.
    """
    return models.AppInfo(
        app_id=_to_optional_int(payload.get("appId")),
        app_name=str(payload.get("appName", "")),
        app_subdomain=str(payload.get("appSubdomain", "")),
        web_landing=str(payload.get("webLanding", "")),
        android_market=str(payload.get("androidMarket", "")),
        ios_market=str(payload.get("iosMarket", "")),
        app_icon_image_url=str(payload.get("appIconImageUrl", "")),
    )


def _extract_goods_payload(soup: bs4.BeautifulSoup) -> dict[str, Any]:
    """Next.js 초기 데이터에서 상품 캐시 항목을 찾습니다.

    Args:
        soup: 상세 페이지를 파싱한 BeautifulSoup 객체입니다.

    Returns:
        상품 정보가 담긴 사전입니다.

    Raises:
        ParseError: 스크립트나 상품 캐시를 찾지 못했을 때 발생합니다.
    """
    script = soup.find("script", id=config.NEXT_DATA_SCRIPT_ID)
    if not isinstance(script, bs4.Tag) or not script.string:
        raise ParseError(
            f"{config.NEXT_DATA_SCRIPT_ID} 스크립트를 찾지 못했습니다."
        )
    next_data = json.loads(script.string)
    page_props = next_data.get("props", {}).get("pageProps", {})
    queries = page_props.get("dehydratedState", {}).get("queries", [])
    for query in queries:
        query_key = query.get("queryKey", [])
        if query_key and query_key[0] == config.GOODS_QUERY_KEY:
            data = query.get("state", {}).get("data", {})
            if isinstance(data, dict):
                return data
    raise ParseError("상품 데이터 캐시를 찾지 못했습니다.")


def _extract_summary(soup: bs4.BeautifulSoup) -> str:
    """메타 태그에서 상품 요약 문구를 읽습니다.

    Args:
        soup: 상세 페이지를 파싱한 BeautifulSoup 객체입니다.

    Returns:
        요약 문구이며 없으면 빈 문자열입니다.
    """
    tag = soup.find("meta", attrs={"name": "description"})
    if not isinstance(tag, bs4.Tag):
        tag = soup.find("meta", attrs={"property": "og:description"})
    if isinstance(tag, bs4.Tag):
        return str(tag.get("content", ""))
    return ""


def _extract_category_id(goods: dict[str, Any]) -> Optional[str]:
    """관리 카테고리 식별자를 읽습니다.

    Args:
        goods: 상품 데이터 사전입니다.

    Returns:
        카테고리 식별자 문자열이며 없으면 None입니다.
    """
    category_id = goods.get("adminCategory", {}).get("id")
    return None if category_id is None else str(category_id)


def _extract_category_path(goods: dict[str, Any]) -> list[str]:
    """대분류부터 이어지는 카테고리 이름 목록을 만듭니다.

    Args:
        goods: 상품 데이터 사전입니다.

    Returns:
        카테고리 이름 목록입니다.
    """
    return [
        str(category.get("title", ""))
        for category in goods.get("categories", [])
        if category.get("title")
    ]


def _extract_ai_attributes(goods: dict[str, Any]) -> dict[str, str]:
    """오늘의집이 제공하는 AI 속성을 사전으로 정리합니다.

    Args:
        goods: 상품 데이터 사전입니다.

    Returns:
        속성 이름과 값으로 이루어진 사전입니다.
    """
    return {
        str(attribute.get("key", "")): str(attribute.get("value", ""))
        for attribute in goods.get("aiProductAttributes", [])
        if attribute.get("key")
    }


def _extract_specifications(production: dict[str, Any]) -> dict[str, str]:
    """상품 정보 고시 항목을 사전으로 정리합니다.

    Args:
        production: 상품 상세 데이터 사전입니다.

    Returns:
        고시 항목 이름과 내용으로 이루어진 사전입니다.
    """
    notice = production.get("informationNoticeItems", {})
    return {
        str(item.get("displayName", "")): str(item.get("content", ""))
        for item in notice.get("items", [])
        if item.get("displayName")
    }


def _extract_options(production: dict[str, Any]) -> list[models.ProductOption]:
    """판매 옵션 목록을 SKU 단위로 변환합니다.

    Args:
        production: 상품 상세 데이터 사전입니다.

    Returns:
        ProductOption 목록입니다.
    """
    options: list[models.ProductOption] = []
    for option in production.get("options", []):
        price = option.get("price", {})
        options.append(
            models.ProductOption(
                option_id=int(option.get("id", 0) or 0),
                is_main=bool(option.get("isMain", False)),
                first_option=str(option.get("explain", "")),
                second_option=str(option.get("explain2", "")),
                selling_price=int(
                    price.get("sellingPrice", option.get("sellingCost", 0)) or 0
                ),
                regular_price=int(
                    price.get("regularPrice", option.get("undiscountedCost", 0))
                    or 0
                ),
                stock=int(option.get("stock", 0) or 0),
            )
        )
    return options


def _extract_images(
    goods: dict[str, Any], production: dict[str, Any]
) -> list[models.ProductImage]:
    """대표·추가·상세·스타일링 이미지를 한 목록으로 모읍니다.

    Args:
        goods: 상품 데이터 사전입니다.
        production: 상품 상세 데이터 사전입니다.

    Returns:
        중복을 제거한 ProductImage 목록입니다.
    """
    images: list[models.ProductImage] = []
    main_url = production.get("originalImageUrl") or production.get("imageUrl")
    if main_url:
        images.append(
            models.ProductImage(
                role="main",
                url=str(main_url),
                source="production.originalImageUrl",
            )
        )
    for sub_image in production.get("subImages", []):
        url = sub_image.get("originalImageUrl")
        if url:
            images.append(
                models.ProductImage(
                    role="sub", url=str(url), source="production.subImages"
                )
            )
    for url in extract_detail_image_urls(production.get("description", "")):
        images.append(
            models.ProductImage(
                role="detail", url=url, source="production.description"
            )
        )
    for card in goods.get("cards", []):
        url = card.get("originalImageUrl")
        if url:
            images.append(
                models.ProductImage(
                    role="styling", url=str(url), source="cards"
                )
            )
    return _deduplicate_images(images)


def extract_detail_image_urls(description_html: str) -> list[str]:
    """상세 설명 HTML에서 이미지 주소를 뽑아냅니다.

    Args:
        description_html: 상세 설명 영역의 HTML 문자열입니다.

    Returns:
        중복을 제거한 이미지 주소 목록입니다.
    """
    if not description_html:
        return []
    soup = bs4.BeautifulSoup(description_html, "html.parser")
    urls: list[str] = []
    for image_tag in soup.find_all("img"):
        for attribute in _IMAGE_ATTRIBUTES:
            url = image_tag.get(attribute)
            if isinstance(url, str) and url.startswith("http"):
                urls.append(url)
                break
    return list(dict.fromkeys(urls))


def _extract_styling_card_urls(goods: dict[str, Any]) -> list[str]:
    """유저 스타일링샷 게시물 주소를 모읍니다.

    Args:
        goods: 상품 데이터 사전입니다.

    Returns:
        게시물 주소 목록입니다.
    """
    urls: list[str] = []
    for card in goods.get("cards", []):
        landing_url = card.get("link", {}).get("landingUrl")
        if landing_url:
            urls.append(str(landing_url))
    return list(dict.fromkeys(urls))


def _deduplicate_images(
    images: list[models.ProductImage],
) -> list[models.ProductImage]:
    """같은 주소의 이미지를 한 번만 남깁니다.

    Args:
        images: 정리 전 이미지 목록입니다.

    Returns:
        주소 기준으로 중복을 제거한 목록입니다.
    """
    unique: dict[str, models.ProductImage] = {}
    for image in images:
        unique.setdefault(image.url, image)
    return list(unique.values())


def _calculate_discount_rate(selling_price: int, regular_price: int) -> int:
    """정가 대비 할인율을 백분율로 계산합니다.

    Args:
        selling_price: 실제 판매가입니다.
        regular_price: 정가입니다.

    Returns:
        내림 처리한 할인율(%)이며 계산할 수 없으면 0입니다.
    """
    if regular_price <= 0 or selling_price <= 0:
        return 0
    return int((regular_price - selling_price) * 100 / regular_price)


def _to_optional_int(value: Any) -> Optional[int]:
    """정수로 바꿀 수 있으면 정수를, 아니면 None을 돌려줍니다.

    Args:
        value: 변환할 원본 값입니다.

    Returns:
        정수 값이며 변환할 수 없으면 None입니다.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
