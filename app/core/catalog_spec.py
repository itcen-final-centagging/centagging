"""SKU 카탈로그 메타데이터 스펙.

구조는 kosa-poc-main/image-generation/common/config.py (COLOR / PRODUCT_CATEGORY /
PRODUCT_ATTRIBUTE / COMMON_ATTRIBUTE 4개 블록 + 조회 함수)를 그대로 따른다.
다만 attributes의 JSON key는 영어(snake_case), value는 한국어로 쓴다
"카탈로그 attributes 스키마" 표를 그대로 따름 — 색상=color, 스타일=style, ...).
"""

# COLOR — 색상 허용값과 참고용 hex (kosa-poc-main/common/config.py 구조 그대로)
COLOR: dict[str, str] = {
    "블랙": "#000000",       # Black
    "화이트": "#FFFFFF",     # White
    "베이지": "#F5F5DC",     # Beige
    "네이비": "#000080",     # Navy
    "카키": "#708238",       # Khaki Green
    "그레이": "#808080",     # Gray
    "브라운": "#8B4513",     # Saddle Brown
    "레드": "#FF0000",       # Red
    "옐로우": "#FFD700",     # Gold Yellow
    "블루": "#0000FF",       # Blue
    "핑크": "#FFC0CB",       # Light Pink
    "퍼플": "#800080",       # Purple
    "그린": "#008000",       # Green
    "오렌지": "#FFA500",     # Orange
}

# PRODUCT_CATEGORY — 대분류 -> 고정 소분류 목록 (kosa-poc-main 구조 그대로)
PRODUCT_CATEGORY: dict[str, list[str]] = {
    "침대": ["침대프레임", "침대+메트리스", "침대부속가구"],
    "매트리스": ["매트리스", "토퍼"],
    "테이블·식탁·책상": ["거실·소파테이블", "사이드테이블", "식탁", "책상", "좌식테이블"],
    "소파": ["일반소파", "리클라이너", "소파베드", "좌식소파", "소파스툴"],
    "서랍·수납장": ["서랍장", "수납장", "캐비닛", "주방수납장", "협탁"],
    "거실장·TV장": ["일반거실장", "높은거실장·사이드보드", "TV스탠드"],
    "선반": ["벽선반", "스탠드선반", "앵글·조립식선반"],
    "진열장·책장": ["진열장,장식장", "책장", "매거진랙"],
    "의자": ["인테리어의자", "스툴·벤치", "빈백", "안락의자", "흔들의자", "학생·사무용의자",
            "게이밍의자", "좌식의자·자세보정의자", "바체어", "발받침"],
    "행거·옷장": ["옷장", "붙박이장", "드레스룸", "행거"],
    "거울": ["전신거울", "벽거울", "탁상거울"],
    "화장대·콘솔": ["일반화장대", "수납화장대", "좌식·미니화장대", "접이식화장대", "콘솔", "화장대+의자"],
}

CATEGORIES: list[str] = list(PRODUCT_CATEGORY.keys())

# COMMON_ATTRIBUTE — 모든 카테고리 공통 속성 (key=영어, value=한국어)
COMMON_ATTRIBUTE: dict[str, list] = {
    "color": ["블랙", "화이트", "베이지", "네이비", "카키", "그레이", "브라운", "레드",
              "옐로우", "블루", "핑크", "퍼플", "그린", "오렌지"],
    "style": ["모던", "클래식", "빈티지", "미니멀", "내추럴", "럭셔리", "인더스트리얼",
              "북유럽", "러블리"],
    # target_customer/target_age는 시각적으로 판단하기 어려운 보조 속성
    "target_customer": ["싱글", "신혼부부", "가족", "아이 있는 가정"],
    "target_age": ["전체 연령", "20대", "30대", "40대", "50대 이상"],
    "pattern": ["무지", "우드그레인", "마블", "라탄·위빙", "패브릭 텍스처", "그래픽"],
}

_MATERIAL_FULL = ["원목", "가공목(MDF 외)", "천연대리석", "세라믹", "철제/스틸", "플라스틱",
                  "라탄", "천연가죽", "인조가죽", "패브릭", "스웨이드", "메쉬", "벨벳"]
_MATERIAL_TABLE = _MATERIAL_FULL[:10]
_SIZE = ["싱글(S)", "슈퍼싱글(SS)", "더블(D)", "퀸(Q)", "킹(K)", "라지킹(LK)", "칼킹(CK)", "멀티싱글(MS)"]
_LEVELS = ["1단", "2단", "3단", "4단", "5단 이상"]
_BOOL = [True, False]


# PRODUCT_ATTRIBUTE — 카테고리별 속성 (key=영어, value=한국어 / true·false는 그대로 bool)
PRODUCT_ATTRIBUTE: dict[str, dict[str, list]] = {
    "침대": {
        "bed_type": ["성인용", "아동용", "패밀리침대", "수납침대"],
        "size": _SIZE,
        "has_headboard": _BOOL,
        "frame_type": ["하단오픈형", "하단밀폐형", "하단수납형", "매트일체형"],
        "material": _MATERIAL_FULL,
        "wood_tone": ["밝은 우드톤", "중간 우드톤", "어두운 우드톤"],
        "head_type": ["일자형", "곡선형", "수납형", "쿠션형", "패널형"],
        "base_type": ["통깔판", "멀티깔판"],
        "product_type": ["프레임만", "프레임+매트리스"],
    },
    "매트리스": {
        "mattress_type": ["스프링", "메모리폼", "라텍스", "하이브리드"],
        "size": _SIZE,
        "firmness": ["하드", "미디엄", "소프트"],
        "thickness": ["10cm 이하", "11~20cm", "21~30cm", "31cm 이상"],
        "features": ["방수커버", "항균", "통풍", "분리형"],
    },
    "테이블·식탁·책상": {
        "shape": ["원형", "사각형", "타원형", "기타"],
        "top_material": _MATERIAL_TABLE,
        "frame_material": _MATERIAL_TABLE,
        "leg_type": ["4다리", "T자형", "X자형", "원형베이스"],
        "has_storage": _BOOL,
        "wood_tone": ["밝은 우드톤", "중간 우드톤", "어두운 우드톤"],
        "seating_capacity": ["2인", "4인", "6인", "8인 이상"],
    },
    "소파": {
        "sofa_type": ["기본형(일자형)", "카우치형", "코너형", "모듈형", "좌식형", "침대형"],
        "material": ["천연가죽", "인조가죽", "스웨이드", "패브릭"],
        "has_legs": _BOOL,
        "has_armrest": _BOOL,
        "has_headrest": _BOOL,
        "has_stool": _BOOL,
    },
    "서랍·수납장": {
        "storage_type": ["서랍장", "수납장", "캐비닛", "주방 수납장", "협탁"],
        "drawer_count": ["1단", "2단", "3단", "4단", "5단 이상"],
        "material": ["원목", "가공목", "금속", "플라스틱", "라탄", "유리"],
        "wood_tone": ["밝은 우드톤", "중간 우드톤", "어두운 우드톤"],
        "door_type": ["미닫이형", "여닫이형", "폴딩형", "플랩형"],
        "has_legs": _BOOL,
        "has_wheels": _BOOL,
        "has_drawer": _BOOL,
    },
    "거실장·TV장": {
        "tv_stand_type": ["일반형", "높은형", "확장형", "전면수납형(책장형)", "스탠드형", "이젤형"],
        "length": ["120cm 이하", "121~160cm", "161~200cm", "201cm 이상"],
        "material": _MATERIAL_FULL,
        "frame_material": _MATERIAL_FULL,
        "level_count": _LEVELS,
        "has_legs": _BOOL,
    },
    "선반": {
        "shelf_type": ["벽선반", "스탠드선반", "앵글·조립식선반"],
        "material": _MATERIAL_FULL,
        "frame_material": _MATERIAL_FULL,
        "shelf_count": _LEVELS,
    },
    "진열장·책장": {
        "storage_type": ["진열장", "장식장", "책장", "매거진랙"],
        "material": _MATERIAL_FULL,
        "frame_material": _MATERIAL_FULL,
        "door_type": ["유리도어", "오픈형", "밀폐형"],
    },
    "의자": {
        "chair_type": ["인테리어의자", "스툴·벤치", "빈백", "안락의자", "흔들의자", "학생·사무용의자",
                       "게이밍의자", "좌식의자", "자세보정의자", "바체어", "발받침"],
        "material": ["원목", "가공목", "금속", "패브릭", "가죽", "메쉬", "플라스틱"],
        "has_wheels": _BOOL,
        "has_backrest": _BOOL,
        "has_armrest": _BOOL,
    },
    "행거·옷장": {
        "wardrobe_type": ["긴 옷장", "짧은 옷장", "서랍 옷장", "선반 옷장", "선반장", "서랍장",
                          "액세서리장", "이불장"],
        "layout_type": ["ㅡ자형", "ㄷ자형", "ㄱ자형"],
        "mobility_type": ["이동식", "고정식"],
        "door_type": ["여닫이", "슬라이딩", "오픈형"],
        "storage_features": ["서랍 포함", "선반 포함", "수납 없음"],
        "material": ["원목", "가공목", "금속", "플라스틱"],
    },
    "거울": {
        "installation_type": ["벽걸이형", "스탠드형", "설치형", "부착형"],
        "shape": ["정사각형", "직사각형", "원형", "타원형", "아치형", "다각형", "유니크형"],
        "has_frame": _BOOL,
        "frame_material": ["원목", "금속", "플라스틱"],
    },
    "화장대·콘솔": {
        "vanity_type": ["일반형", "수납형", "좌식형", "콘솔형", "접이식", "전신거울형", "벽걸이선반형", "미니형"],
        "has_mirror": _BOOL,
        "storage_type": ["서랍형", "선반형", "복합형"],
        "material": ["원목", "가공목", "유리", "금속"],
    },
}

# SKU 카탈로그 빌더 전용 (POC에는 없는, 크롤러 데이터를 위한 보조 정의)
# 오늘의집 category_path[1] (원문) -> PRODUCT_CATEGORY 의 12개 고정 대분류
CATEGORY_MAP: dict[str, str] = {
    "소파": "소파",
    "의자": "의자",
    "테이블·식탁·책상": "테이블·식탁·책상",
    "침대": "침대",
    "매트리스·토퍼": "매트리스",
    "매트리스": "매트리스",
    "서랍·수납장": "서랍·수납장",
    "거실장·TV장": "거실장·TV장",
    "선반": "선반",
    "진열장·책장": "진열장·책장",
    "행거·옷장": "행거·옷장",
    "거울": "거울",
    "화장대·콘솔": "화장대·콘솔",
}

# sku_code 접두어 (카테고리별) - DB 표시용, POC에는 없는 이번 단계 전용 값
CATEGORY_CODE: dict[str, str] = {
    "소파": "SOFA", "의자": "CHR", "테이블·식탁·책상": "TBL", "침대": "BED",
    "매트리스": "MATT", "서랍·수납장": "DRW", "거실장·TV장": "TV", "선반": "SHLF",
    "진열장·책장": "BOOK", "행거·옷장": "WRD", "거울": "MIR", "화장대·콘솔": "VAN",
}


# 메타데이터 조회 함수
def attribute_names(category: str) -> list[str]:
    """해당 대분류에서 사용하는 전체 속성명(영어 key)을 반환한다.

    공통 속성(COMMON_ATTRIBUTE: color/style/target_customer/target_age/pattern)과
    해당 대분류 전용 속성(PRODUCT_ATTRIBUTE[category])을 합쳐 반환한다.
    """
    if category not in PRODUCT_ATTRIBUTE:
        raise KeyError(f"정의되지 않은 대분류입니다: {category}")

    return list(COMMON_ATTRIBUTE.keys()) + list(PRODUCT_ATTRIBUTE[category].keys())


def allowed_values(category: str, attribute: str) -> list:
    """해당 대분류와 속성(영어 key)에서 허용되는 값(한국어 또는 bool)을 반환한다."""
    if category not in PRODUCT_ATTRIBUTE:
        raise KeyError(f"정의되지 않은 대분류입니다: {category}")

    if attribute in COMMON_ATTRIBUTE:
        return COMMON_ATTRIBUTE[attribute]

    if attribute in PRODUCT_ATTRIBUTE[category]:
        return PRODUCT_ATTRIBUTE[category][attribute]

    raise KeyError(f"'{category}'에서 정의되지 않은 속성입니다: {attribute}")


def validate_attrs(category: str, attrs: dict) -> list[str]:
    """정의된 key 누락/허용값 외 값 사용을 검사해 오류 리스트를 반환한다."""
    errs = []
    expected = attribute_names(category)
    missing = [k for k in expected if k not in attrs]
    extra = [k for k in attrs if k not in expected]
    if missing:
        errs.append(f"key 누락: {missing}")
    if extra:
        errs.append(f"정의되지 않은 key: {extra}")
    for k, v in attrs.items():
        if v is None or isinstance(v, list):
            continue
        try:
            allowed = allowed_values(category, k)
        except KeyError:
            continue
        if not allowed:  # 빈 리스트 = 자유 입력 속성, 검증 skip
            continue
        if v not in allowed:
            errs.append(f"{k} 허용값 외: {v!r}")
    return errs
