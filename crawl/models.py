"""크롤링 결과를 담는 데이터 모델입니다. / Data models for crawled results."""

import dataclasses
from typing import Any, Optional


@dataclasses.dataclass(frozen=True)
class ProductImage:
    """상품과 연결된 이미지 한 장입니다. / A single image tied to a product.

    Attributes:
        role: 이미지 용도입니다(main, sub, detail, styling).
        url: 원본 이미지 주소입니다.
        source: 이미지를 얻은 위치 설명입니다.
    """

    role: str
    url: str
    source: str


@dataclasses.dataclass(frozen=True)
class ProductOption:
    """SKU 단위 판매 옵션입니다. / A sellable option at SKU level.

    Attributes:
        option_id: 오늘의집 옵션 식별자입니다.
        is_main: 대표 옵션 여부입니다.
        first_option: 첫 번째 옵션 값입니다(예: 사이즈).
        second_option: 두 번째 옵션 값입니다(예: 색상).
        selling_price: 실제 판매가입니다.
        regular_price: 정가입니다.
        stock: 재고 수량이며 -1은 무제한을 뜻합니다.
    """

    option_id: int
    is_main: bool
    first_option: str
    second_option: str
    selling_price: int
    regular_price: int
    stock: int


@dataclasses.dataclass(frozen=True)
class Product:  # pylint: disable=too-many-instance-attributes
    """태깅과 SKU 매칭에 사용할 상품 정보입니다. / Product data for tagging.

    상품 한 건을 그대로 담는 값 객체라 필드 수가 많습니다.
    / The class mirrors one product record, so it has many fields.

    Attributes:
        goods_id: 오늘의집 상품 번호입니다.
        source_url: 수집한 상세 페이지 주소입니다.
        crawled_at: 수집 시각(ISO 8601)입니다.
        name: 상품명입니다.
        summary: 상품 요약 설명입니다.
        brand_id: 브랜드 식별자입니다.
        brand_name: 브랜드명입니다.
        category_id: 관리 카테고리 식별자입니다.
        category_path: 대분류부터 이어지는 카테고리 이름 목록입니다.
        first_option_name: 첫 번째 옵션 축의 이름입니다.
        second_option_name: 두 번째 옵션 축의 이름입니다.
        selling_price: 판매가입니다.
        regular_price: 정가입니다.
        discount_rate: 정가 대비 할인율(%)입니다.
        review_average: 리뷰 평균 점수입니다.
        review_count: 리뷰 개수입니다.
        scrap_count: 스크랩 수입니다.
        is_selling: 판매 중 여부입니다.
        is_sold_out: 품절 여부입니다.
        ai_attributes: 오늘의집이 제공하는 AI 요약 속성입니다.
        specifications: 상품 정보 고시 항목입니다.
        options: 판매 옵션 목록입니다.
        images: 수집한 이미지 목록입니다.
        styling_card_urls: 유저 스타일링샷 게시물 주소 목록입니다.
    """

    goods_id: int
    source_url: str
    crawled_at: str
    name: str
    summary: str
    brand_id: Optional[int]
    brand_name: str
    category_id: Optional[str]
    category_path: list[str]
    first_option_name: str
    second_option_name: str
    selling_price: int
    regular_price: int
    discount_rate: int
    review_average: float
    review_count: int
    scrap_count: int
    is_selling: bool
    is_sold_out: bool
    ai_attributes: dict[str, str]
    specifications: dict[str, str]
    options: list[ProductOption]
    images: list[ProductImage]
    styling_card_urls: list[str]

    def to_dict(self) -> dict[str, Any]:
        """JSON 저장을 위해 사전 형태로 변환합니다.

        Returns:
            중첩 데이터클래스까지 펼친 사전입니다.
        """
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class AppInfo:
    """Airbridge 설정에서 추린 앱 메타데이터입니다. / App metadata subset.

    Attributes:
        app_id: Airbridge에 등록된 앱 번호입니다.
        app_name: 앱 이름입니다.
        app_subdomain: Airbridge 서브도메인 식별자입니다.
        web_landing: 웹 랜딩 주소입니다.
        android_market: 안드로이드 마켓 주소입니다.
        ios_market: iOS 마켓 주소입니다.
        app_icon_image_url: 앱 아이콘 이미지 주소입니다.
    """

    app_id: Optional[int]
    app_name: str
    app_subdomain: str
    web_landing: str
    android_market: str
    ios_market: str
    app_icon_image_url: str

    def to_dict(self) -> dict[str, Any]:
        """JSON 저장을 위해 사전 형태로 변환합니다.

        Returns:
            앱 메타데이터 사전입니다.
        """
        return dataclasses.asdict(self)
