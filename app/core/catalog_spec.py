"""SKU 카탈로그 메타데이터 스펙.

원본 크롤링 데이터에서 추출할 SKU 메타데이터의 고정 규약을 정의한다.

원칙:
1. attributes의 key는 영어 snake_case를 사용한다.
2. attributes의 value는 한국어 허용값을 사용한다.
3. 정의된 허용값 외의 값은 사용하지 않는다.
4. 원본 데이터에서 확인할 수 없는 속성은 추측하지 않고 None을 사용한다.
5. 존재 여부를 나타내는 속성은 bool을 사용하지 않고
   "있음" / "없음" / "모름" 중 하나를 사용한다.
6. 모든 카테고리는 공통 속성 + 카테고리별 속성을 사용한다.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# COLOR
# ---------------------------------------------------------------------------
# 색상 허용값과 참고용 HEX

COLOR: dict[str, str] = {
    "블랙": "#000000",
    "화이트": "#FFFFFF",
    "베이지": "#F5F5DC",
    "네이비": "#000080",
    "카키": "#708238",
    "그레이": "#808080",
    "브라운": "#8B4513",
    "레드": "#FF0000",
    "옐로우": "#FFD700",
    "블루": "#0000FF",
    "핑크": "#FFC0CB",
    "퍼플": "#800080",
    "그린": "#008000",
    "오렌지": "#FFA500",
}

# ---------------------------------------------------------------------------
# PRODUCT_CATEGORY
# ---------------------------------------------------------------------------
# 대분류 -> 고정 소분류 목록

PRODUCT_CATEGORY: dict[str, list[str]] = {
    "침대": [
        "침대프레임",
        "침대+메트리스",
        "침대부속가구",
    ],
    "매트리스": [
        "매트리스",
        "토퍼",
    ],
    "테이블·식탁·책상": [
        "거실·소파테이블",
        "사이드테이블",
        "식탁",
        "책상",
        "좌식테이블",
    ],
    "소파": [
        "일반소파",
        "리클라이너",
        "소파베드",
        "좌식소파",
        "소파스툴",
    ],
    "서랍·수납장": [
        "서랍장",
        "수납장",
        "캐비닛",
        "주방수납장",
        "협탁",
    ],
    "거실장·TV장": [
        "일반거실장",
        "높은거실장·사이드보드",
        "TV스탠드",
    ],
    "선반": [
        "벽선반",
        "스탠드선반",
        "앵글·조립식선반",
    ],
    "진열장·책장": [
        "진열장,장식장",
        "책장",
        "매거진랙",
    ],
    "의자": [
        "인테리어의자",
        "스툴·벤치",
        "빈백",
        "안락의자",
        "흔들의자",
        "학생·사무용의자",
        "게이밍의자",
        "좌식의자·자세보정의자",
        "바체어",
        "발받침",
    ],
    "행거·옷장": [
        "옷장",
        "붙박이장",
        "드레스룸",
        "행거",
    ],
    "거울": [
        "전신거울",
        "벽거울",
        "탁상거울",
    ],
    "화장대·콘솔": [
        "일반화장대",
        "수납화장대",
        "좌식·미니화장대",
        "접이식화장대",
        "콘솔",
        "화장대+의자",
    ],
}

CATEGORIES: list[str] = list(PRODUCT_CATEGORY.keys())

# ---------------------------------------------------------------------------
# COMMON_ATTRIBUTE
# ---------------------------------------------------------------------------
# 모든 카테고리에서 공통으로 사용하는 속성

COMMON_ATTRIBUTE = {
    "color": [
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
    ],
    "style": [
        "모던",
        "클래식",
        "빈티지",
        "미니멀",
        "내추럴",
        "럭셔리",
        "인더스트리얼",
        "북유럽",
        "러블리",
    ],
    "pattern": [
        "무지",
        "우드그레인",
        "마블",
        "라탄·위빙",
        "패브릭 텍스처",
        "그래픽",
    ],
    # 상품 기본 정보
    "brand": None,
    "selling_price": None,
}
# ---------------------------------------------------------------------------
# 공통 허용값
# ---------------------------------------------------------------------------

_MATERIAL_FULL = [
    "원목",
    "가공목(MDF 외)",
    "천연대리석",
    "세라믹",
    "철제/스틸",
    "플라스틱",
    "라탄",
    "천연가죽",
    "인조가죽",
    "패브릭",
    "스웨이드",
    "메쉬",
    "벨벳",
]

_MATERIAL_TABLE = _MATERIAL_FULL[:10]

_SIZE = [
    "싱글(S)",
    "슈퍼싱글(SS)",
    "더블(D)",
    "퀸(Q)",
    "킹(K)",
    "라지킹(LK)",
    "칼킹(CK)",
    "멀티싱글(MS)",
]

_LEVELS = [
    "1단",
    "2단",
    "3단",
    "4단",
    "5단 이상",
]

# bool 대신 존재 여부를 명시적으로 표현한다.
_EXISTENCE = [
    "있음",
    "없음",
    "모름",
]

# ---------------------------------------------------------------------------
# PRODUCT_ATTRIBUTE
# ---------------------------------------------------------------------------
# 카테고리별 속성
#
# 모든 존재 여부 속성은:
#     "있음" / "없음" / "모름"
#
# 원본에서 확인할 수 없으면:
#     None
#
# 으로 처리한다.

PRODUCT_ATTRIBUTE: dict[str, dict[str, list[Any]]] = {
    "침대": {
        "bed_type": [
            "성인용",
            "아동용",
            "패밀리침대",
            "수납침대",
        ],
        "size": _SIZE,
        "has_headboard": _EXISTENCE,
        "frame_type": [
            "하단오픈형",
            "하단밀폐형",
            "하단수납형",
            "매트일체형",
        ],
        "material": _MATERIAL_FULL,
        "wood_tone": [
            "밝은 우드톤",
            "중간 우드톤",
            "어두운 우드톤",
        ],
        "head_type": [
            "일자형",
            "곡선형",
            "수납형",
            "쿠션형",
            "패널형",
        ],
        "base_type": [
            "통깔판",
            "멀티깔판",
        ],
        "product_type": [
            "프레임만",
            "프레임+매트리스",
        ],
    },
    "매트리스": {
        "mattress_type": [
            "스프링",
            "메모리폼",
            "라텍스",
            "하이브리드",
        ],
        "size": _SIZE,
        "firmness": [
            "하드",
            "미디엄",
            "소프트",
        ],
        "thickness": [
            "10cm 이하",
            "11~20cm",
            "21~30cm",
            "31cm 이상",
        ],
        "features": [
            "방수커버",
            "항균",
            "통풍",
            "분리형",
        ],
    },
    "테이블·식탁·책상": {
        "shape": [
            "원형",
            "사각형",
            "타원형",
            "기타",
        ],
        "top_material": _MATERIAL_TABLE,
        "frame_material": _MATERIAL_TABLE,
        "leg_type": [
            "4다리",
            "T자형",
            "X자형",
            "원형베이스",
        ],
        "has_storage": _EXISTENCE,
        "wood_tone": [
            "밝은 우드톤",
            "중간 우드톤",
            "어두운 우드톤",
        ],
        "seating_capacity": [
            "2인",
            "4인",
            "6인",
            "8인 이상",
        ],
    },
    "소파": {
        "sofa_type": [
            "기본형(일자형)",
            "카우치형",
            "코너형",
            "모듈형",
            "좌식형",
            "침대형",
        ],
        "material": [
            "천연가죽",
            "인조가죽",
            "스웨이드",
            "패브릭",
        ],
        "has_legs": _EXISTENCE,
        "has_armrest": _EXISTENCE,
        "has_headrest": _EXISTENCE,
        "has_stool": _EXISTENCE,
    },
    "서랍·수납장": {
        "storage_type": [
            "서랍장",
            "수납장",
            "캐비닛",
            "주방 수납장",
            "협탁",
        ],
        "drawer_count": [
            "1단",
            "2단",
            "3단",
            "4단",
            "5단 이상",
        ],
        "material": [
            "원목",
            "가공목",
            "금속",
            "플라스틱",
            "라탄",
            "유리",
        ],
        "wood_tone": [
            "밝은 우드톤",
            "중간 우드톤",
            "어두운 우드톤",
        ],
        "door_type": [
            "미닫이형",
            "여닫이형",
            "폴딩형",
            "플랩형",
        ],
        "has_legs": _EXISTENCE,
        "has_wheels": _EXISTENCE,
        "has_drawer": _EXISTENCE,
    },
    "거실장·TV장": {
        "tv_stand_type": [
            "일반형",
            "높은형",
            "확장형",
            "전면수납형(책장형)",
            "스탠드형",
            "이젤형",
        ],
        "length": [
            "120cm 이하",
            "121~160cm",
            "161~200cm",
            "201cm 이상",
        ],
        "material": _MATERIAL_FULL,
        "frame_material": _MATERIAL_FULL,
        "level_count": _LEVELS,
        "has_legs": _EXISTENCE,
    },
    "선반": {
        "shelf_type": [
            "벽선반",
            "스탠드선반",
            "앵글·조립식선반",
        ],
        "material": _MATERIAL_FULL,
        "frame_material": _MATERIAL_FULL,
        "shelf_count": _LEVELS,
    },
    "진열장·책장": {
        "storage_type": [
            "진열장",
            "장식장",
            "책장",
            "매거진랙",
        ],
        "material": _MATERIAL_FULL,
        "frame_material": _MATERIAL_FULL,
        "door_type": [
            "유리도어",
            "오픈형",
            "밀폐형",
        ],
    },
    "의자": {
        "chair_type": [
            "인테리어의자",
            "스툴·벤치",
            "빈백",
            "안락의자",
            "흔들의자",
            "학생·사무용의자",
            "게이밍의자",
            "좌식의자",
            "자세보정의자",
            "바체어",
            "발받침",
        ],
        "material": [
            "원목",
            "가공목",
            "금속",
            "패브릭",
            "가죽",
            "메쉬",
            "플라스틱",
        ],
        "has_wheels": _EXISTENCE,
        "has_backrest": _EXISTENCE,
        "has_armrest": _EXISTENCE,
    },
    "행거·옷장": {
        "wardrobe_type": [
            "긴 옷장",
            "짧은 옷장",
            "서랍 옷장",
            "선반 옷장",
            "선반장",
            "서랍장",
            "액세서리장",
            "이불장",
        ],
        "layout_type": [
            "ㅡ자형",
            "ㄷ자형",
            "ㄱ자형",
        ],
        "mobility_type": [
            "이동식",
            "고정식",
        ],
        "door_type": [
            "여닫이",
            "슬라이딩",
            "오픈형",
        ],
        "storage_features": [
            "서랍 포함",
            "선반 포함",
            "수납 없음",
        ],
        "material": [
            "원목",
            "가공목",
            "금속",
            "플라스틱",
        ],
    },
    "거울": {
        "installation_type": [
            "벽걸이형",
            "스탠드형",
            "설치형",
            "부착형",
        ],
        "shape": [
            "정사각형",
            "직사각형",
            "원형",
            "타원형",
            "아치형",
            "다각형",
            "유니크형",
        ],
        "has_frame": _EXISTENCE,
        "frame_material": [
            "원목",
            "금속",
            "플라스틱",
        ],
    },
    "화장대·콘솔": {
        "vanity_type": [
            "일반형",
            "수납형",
            "좌식형",
            "콘솔형",
            "접이식",
            "전신거울형",
            "벽걸이선반형",
            "미니형",
        ],
        "has_mirror": _EXISTENCE,
        "storage_type": [
            "서랍형",
            "선반형",
            "복합형",
        ],
        "material": [
            "원목",
            "가공목",
            "유리",
            "금속",
        ],
    },
}

# ---------------------------------------------------------------------------
# CATEGORY_MAP
# ---------------------------------------------------------------------------
# 오늘의집 원문 category_path[1] -> 프로젝트 대분류
# 오늘의집의 카테고리 체계를 우리 프로젝트의 카테고리 체계로 변환해서, 이후 SKU 생성·메타데이터 추출에서 일관되게 사용하기 위한 매핑표

CATEGORY_MAP: dict[str, str] = {
    "소파": "소파",
    "의자": "의자",
    "테이블·식탁·책상": "테이블·식탁·책상",
    "침대": "침대",
    "매트리스·토퍼": "매트리스",  # here
    "매트리스": "매트리스",
    "서랍·수납장": "서랍·수납장",
    "거실장·TV장": "거실장·TV장",
    "선반": "선반",
    "진열장·책장": "진열장·책장",
    "행거·옷장": "행거·옷장",
    "거울": "거울",
    "화장대·콘솔": "화장대·콘솔",
}

# ---------------------------------------------------------------------------
# CATEGORY_CODE
# ---------------------------------------------------------------------------
# SKU code 생성용 카테고리 코드

CATEGORY_CODE: dict[str, str] = {
    "소파": "SOFA",
    "의자": "CHR",
    "테이블·식탁·책상": "TBL",
    "침대": "BED",
    "매트리스": "MATT",
    "서랍·수납장": "DRW",
    "거실장·TV장": "TV",
    "선반": "SHLF",
    "진열장·책장": "BOOK",
    "행거·옷장": "WRD",
    "거울": "MIR",
    "화장대·콘솔": "VAN",
}


# ---------------------------------------------------------------------------
# 메타데이터 조회 함수
# ---------------------------------------------------------------------------


# 카테고리가 정의되어 있으면 공통 속성과 카테고리별 전용 속성명을 합쳐 반환하고, 없으면 오류를 발생시킨다.
def attribute_names(category: str) -> list[str]:
    """해당 대분류에서 사용하는 전체 속성명을 반환한다.

    공통 속성과 카테고리별 전용 속성을 합쳐 반환한다.
    """
    if category not in PRODUCT_ATTRIBUTE:
        raise KeyError(f"정의되지 않은 대분류입니다: {category}")

    return list(COMMON_ATTRIBUTE.keys()) + list(
        PRODUCT_ATTRIBUTE[category].keys()
    )


# 해당 카테고리의 특정 속성(attribute)에서 사용할 수 있는 허용값을 반환한다.
def allowed_values(
    category: str,
    attribute: str,
) -> list[Any] | list[str] | None | list[Any]:
    """해당 대분류와 속성에서 허용되는 값을 반환한다."""
    if category not in PRODUCT_ATTRIBUTE:
        raise KeyError(f"정의되지 않은 대분류입니다: {category}")
    # 공통 속성에서
    if attribute in COMMON_ATTRIBUTE:
        return COMMON_ATTRIBUTE[attribute]
    # 특정 카테고리의 속성(attribute)에서
    if attribute in PRODUCT_ATTRIBUTE[category]:
        return PRODUCT_ATTRIBUTE[category][attribute]

    raise KeyError(f"'{category}'에서 정의되지 않은 속성입니다: {attribute}")


# 메타데이터의 key와 각 속성값이 카테고리별 정의된 규칙과 허용값에 맞는지 검증한다.
def validate_attrs(
    category: str,
    attrs: dict[str, Any],
) -> list[str]:
    """메타데이터 key와 허용값을 검증한다.

    검증 규칙:
    - 정의되지 않은 key는 오류
    - 정의된 key가 누락되면 오류
    - None은 허용
    - 허용값 목록에 없는 값은 오류
    """
    errs: list[str] = []

    expected = attribute_names(category)

    missing = [key for key in expected if key not in attrs]

    extra = [key for key in attrs if key not in expected]

    if missing:
        errs.append(f"key 누락: {missing}")

    if extra:
        errs.append(f"정의되지 않은 key: {extra}")

    for key, value in attrs.items():
        if value is None:
            continue

        try:
            allowed = allowed_values(category, key)
        except KeyError:
            continue

        if not allowed:
            continue

        if value not in allowed:
            errs.append(f"{key} 허용값 외: {value!r}")

    return errs
