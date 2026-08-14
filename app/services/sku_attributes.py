"""카테고리별 SKU 속성(attributes) 스키마입니다."""

import typing

import pydantic

# AI 추출 프롬프트에서도 사용하는 색상 후보 목록입니다.
# BaseSkuAttributes.color의 Literal 값과 반드시 같은 목록이어야 합니다.
COLOR_OPTIONS: list[str] = [
    "블랙",
    "화이트",
    "베이지",
    "네이비",
    "카키",
    "그레이",
    "브라운",
    "레드",
    "옐로우",
    "블루",
    "핑크",
    "퍼플",
    "그린",
    "오렌지",
]


class BaseSkuAttributes(pydantic.BaseModel):
    """모든 카테고리에 공통인 속성입니다."""

    color: typing.Literal[
        "블랙",
        "화이트",
        "베이지",
        "네이비",
        "카키",
        "그레이",
        "브라운",
        "레드",
        "옐로우",
        "블루",
        "핑크",
        "퍼플",
        "그린",
        "오렌지",
    ]
    style: str
    pattern: str


class TableDeskAttributes(BaseSkuAttributes):
    """테이블·식탁·책상 (``sub_category``: 식탁, 책상 등)."""

    shape: str
    top_material: str
    frame_material: str
    leg_type: str
    has_storage: bool
    wood_tone: typing.Optional[str] = None
    seating_capacity: typing.Optional[str] = None


class SofaAttributes(BaseSkuAttributes):
    """소파."""

    sofa_type: str
    material: str
    has_legs: bool
    has_armrest: bool
    has_headrest: bool
    has_stool: bool
    target_customer: typing.Optional[str] = None


class BedAttributes(BaseSkuAttributes):
    """침대."""

    bed_type: str
    size: str
    has_headboard: bool
    frame_type: str
    material: str
    base_type: str
    product_type: str
    wood_tone: typing.Optional[str] = None
    head_type: typing.Optional[str] = None


class MattressAttributes(BaseSkuAttributes):
    """매트리스."""

    mattress_type: str
    size: str
    thickness: str
    features: typing.Optional[str] = None
    firmness: typing.Optional[str] = None


class ShelfAttributes(BaseSkuAttributes):
    """선반."""

    shelf_type: str
    material: str
    frame_material: str
    shelf_count: str


class StorageCabinetAttributes(BaseSkuAttributes):
    """서랍·수납장."""

    storage_type: str
    drawer_count: str
    material: str
    has_legs: bool
    has_wheels: bool
    has_drawer: bool
    wood_tone: typing.Optional[str] = None


class ChairAttributes(BaseSkuAttributes):
    """의자."""

    chair_type: str
    material: str
    has_wheels: bool
    has_backrest: bool
    has_armrest: bool


class MirrorAttributes(BaseSkuAttributes):
    """거울."""

    installation_type: str
    shape: str
    has_frame: bool


class WardrobeAttributes(BaseSkuAttributes):
    """행거·옷장."""

    layout_type: str
    mobility_type: str
    door_type: str
    storage_features: str
    material: str
    wardrobe_type: typing.Optional[str] = None


class TvStandAttributes(BaseSkuAttributes):
    """거실장·TV장."""

    tv_stand_type: str
    length: str
    material: str
    level_count: str
    has_legs: bool


class BookcaseAttributes(BaseSkuAttributes):
    """진열장·책장."""

    storage_type: str
    material: str
    frame_material: str
    door_type: str


class VanityAttributes(BaseSkuAttributes):
    """화장대·콘솔."""

    vanity_type: str
    has_mirror: bool
    storage_type: str
    material: str


SkuAttributes = typing.Union[
    TableDeskAttributes,
    SofaAttributes,
    BedAttributes,
    MattressAttributes,
    ShelfAttributes,
    StorageCabinetAttributes,
    ChairAttributes,
    MirrorAttributes,
    WardrobeAttributes,
    TvStandAttributes,
    BookcaseAttributes,
    VanityAttributes,
]

# data/catalog/answer/sku.json의 category 값과 그대로 일치합니다.
CATEGORY_ATTRIBUTE_MODELS: dict[str, type[pydantic.BaseModel]] = {
    "테이블·식탁·책상": TableDeskAttributes,
    "소파": SofaAttributes,
    "침대": BedAttributes,
    "매트리스": MattressAttributes,
    "선반": ShelfAttributes,
    "서랍·수납장": StorageCabinetAttributes,
    "의자": ChairAttributes,
    "거울": MirrorAttributes,
    "행거·옷장": WardrobeAttributes,
    "거실장·TV장": TvStandAttributes,
    "진열장·책장": BookcaseAttributes,
    "화장대·콘솔": VanityAttributes,
}


CATEGORY_TAXONOMY: dict[str, list[str]] = {
    "테이블·식탁·책상": ["소파테이블", "사이드테이블", "식탁", "책상"],
    "소파": ["일반소파", "리클라이너", "소파베드", "좌식소파"],
    "침대": ["침대프레임", "침대+매트리스", "침대부속가구"],
    "매트리스": ["매트리스"],
    "선반": ["벽선반", "스탠드선반", "조립식선반"],
    "서랍·수납장": ["서랍장", "수납장", "캐비닛", "협탁"],
    "의자": ["인테리어의자", "스툴·벤치", "안락의자", "사무용의자"],
    "거울": ["전신거울"],
    "행거·옷장": ["옷장", "붙박이장", "행거"],
    "거실장·TV장": ["일반거실장", "높은거실장", "TV스탠드"],
    "진열장·책장": ["진열장", "책장", "매거진랙"],
    "화장대·콘솔": ["수납화장대"],
}

SPACE_OPTIONS: list[str] = [
    "거실",
    "침실",
    "주방",
    "서재·홈오피스",
    "아이방",
    "드레스룸",
    "현관",
    "발코니·테라스",
]
