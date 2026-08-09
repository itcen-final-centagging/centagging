"""크롤링 원문 텍스트 -> 카탈로그 허용값 정규화 규칙.

VLM을 쓰지 않는다. 오늘의집 원본(product.json)의
name / summary / specifications / options / ai_attributes 텍스트만 근거로
값을 정한다.

원칙
----
1. 근거가 없으면 값을 만들지 않고 None을 반환한다. (추측 금지)
2. 모든 반환값은 app/core/catalog_spec.py의 허용값 안에 들어간다.
3. 순수 함수만 둔다. 파일 I/O도, 외부 API 호출도 하지 않는다.
   "이 값이 어디서 나왔는지(source)"는 호출부(metadata_builder)가 기록한다.
"""

from __future__ import annotations

import re

from app.core import catalog_spec

# ===========================================================================
# 색상
# ===========================================================================
COLOR_KEYWORDS: dict[str, list[str]] = {
    "블랙": ["블랙", "차콜", "챠콜", "검정", "먹색"],
    "화이트": [
        "화이트",
        "아이보리",
        "크림",
        "웜화이트",
        "오프화이트",
        "스노우",
        "백색",
        "무광백색",
    ],
    "베이지": ["베이지", "샌드", "밀크", "오트", "라떼"],
    "네이비": ["네이비"],
    "카키": ["카키", "올리브"],
    "그레이": ["그레이", "그레이지", "실버", "은색"],
    "브라운": [
        "브라운",
        "카멜",
        "월넛",
        "멀바우",
        "헤이즐넛",
        "메이플",
        "오크",
        "티크",
        "애쉬",
        "내추럴",
        "내츄럴",
        "원목색",
        "모카",
        "초코",
    ],
    "레드": ["레드", "버건디", "와인"],
    "옐로우": ["옐로우", "머스타드", "노랑"],
    "블루": ["블루", "인디고", "청록"],
    "핑크": ["핑크", "로즈", "인디핑크"],
    "퍼플": ["퍼플", "라벤더", "바이올렛"],
    "그린": ["그린", "세이지", "민트"],
    "오렌지": ["오렌지", "코랄", "테라코타"],
}

# 색상 키워드가 겹쳐 보이는 조합어는 여기서 먼저 결론을 낸다.
COLOR_PRIORITY_OVERRIDE: dict[str, str] = {
    "카키그린": "그린",
    "네이비블루": "네이비",
    "블랙우드": "블랙",
    "블랙오크": "블랙",
    "다크그레이": "그레이",
    "파인그레이": "그레이",
    "스카이블루": "블루",
    "하바나옐로우": "옐로우",
    "로즈우드": "브라운",
    "로즈골드": "핑크",
}


def normalize_color(text: str | None) -> str | None:
    """텍스트에서 허용 색상 1개를 뽑는다.

    Args:
        text: 옵션·스펙 등 원문 텍스트입니다.

    Returns:
        허용 색상 이름입니다. 근거가 없으면 None입니다.
    """
    if not text:
        return None

    for combo, color in COLOR_PRIORITY_OVERRIDE.items():
        if combo in text:
            return color

    hits: list[tuple[int, int, str]] = []
    for color, keywords in COLOR_KEYWORDS.items():
        for keyword in keywords:
            position = text.find(keyword)
            if position >= 0:
                hits.append((-len(keyword), position, color))

    if not hits:
        return None

    hits.sort()
    return hits[0][2]


def last_segment(text: str | None, separator: str = "_") -> str:
    """구분자로 나눈 마지막 조각을 반환한다.

    Args:
        text: 옵션 원문 텍스트입니다.
        separator: 자를 구분자입니다.

    Returns:
        마지막 조각입니다. 입력이 비어 있으면 빈 문자열입니다.
    """
    if not text:
        return ""
    return text.rsplit(separator, 1)[-1].strip()


def text_before(text: str | None, marker: str) -> str:
    """표시어 앞부분만 반환한다.

    Args:
        text: 옵션 원문 텍스트입니다.
        marker: 기준이 되는 표시어입니다.

    Returns:
        표시어 앞 텍스트입니다. 표시어가 없으면 원문 그대로입니다.
    """
    if not text:
        return ""
    return text.split(marker, 1)[0].strip()


# ===========================================================================
# 소재
# ===========================================================================
MATERIAL_KEYWORDS: dict[str, list[str]] = {
    "천연가죽": ["천연가죽", "천연면피", "소가죽", "통가죽", "우피"],
    "인조가죽": [
        "인조가죽",
        "인조피혁",
        "인조레더",
        "실리콘레더",
        "레자",
        "pu레더",
        "pvc레더",
        "합성피혁",
    ],
    "스웨이드": ["스웨이드"],
    "벨벳": ["벨벳", "벨보아"],
    "메쉬": ["메쉬", "매쉬"],
    "패브릭": [
        "패브릭",
        "아쿠아텍스",
        "원단",
        "린넨",
        "리넨",
        "면혼방",
        "폴리에스터",
        "극세사",
        "마이크로화이버",
        "쉐닐",
        "부클",
        "직물",
    ],
    "라탄": ["라탄", "위빙"],
    "천연대리석": ["천연대리석", "대리석", "마블스톤"],
    "세라믹": ["세라믹", "포세린"],
    "유리": ["강화유리", "유리"],
    "철제/스틸": [
        "스테인리스",
        "스테인레스",
        "스틸",
        "steel",
        "철제",
        "철재",
        "금속",
        "분체도장",
        "알루미늄",
        "크롬",
    ],
    "플라스틱": ["플라스틱", "abs", "pp수지", "pvc", "아크릴", "폴리프로필렌"],
    "원목": [
        "원목",
        "고무나무",
        "러버우드",
        "자작나무",
        "소나무",
        "삼나무",
        "오크원목",
        "월넛원목",
        "통원목",
    ],
    "가공목(MDF 외)": [
        "mdf",
        "lpm",
        "pb",
        "e0",
        "e1",
        "파티클보드",
        "무늬목",
        "합판",
        "hpm",
        "pet마감",
        "강화마이카",
        "집성목",
        "가공목",
    ],
}

# 카테고리 허용값이 축약형인 경우의 별칭 (예: 의자는 "가죽"만 허용)
MATERIAL_ALIAS: dict[str, list[str]] = {
    "가공목(MDF 외)": ["가공목"],
    "철제/스틸": ["금속", "스틸", "철제"],
    "천연가죽": ["가죽"],
    "인조가죽": ["가죽"],
    "천연대리석": ["대리석"],
}


def _fit_material(canonical: str, allowed: list[str]) -> str | None:
    """정규 소재명을 해당 카테고리의 허용값 표기로 맞춘다."""
    if not allowed:
        return canonical
    if canonical in allowed:
        return canonical
    for alias in MATERIAL_ALIAS.get(canonical, []):
        if alias in allowed:
            return alias
    return None


def _material_hits(text: str) -> list[str]:
    """텍스트에 등장한 소재를 등장 순서대로 돌려준다."""
    lowered = text.lower()
    hits: list[tuple[int, int, str]] = []
    for canonical, keywords in MATERIAL_KEYWORDS.items():
        for keyword in keywords:
            position = lowered.find(keyword.lower())
            if position >= 0:
                hits.append((position, -len(keyword), canonical))
    hits.sort()

    ordered: list[str] = []
    for _position, _length, canonical in hits:
        if canonical not in ordered:
            ordered.append(canonical)
    return ordered


def material_chunks(text: str) -> list[str]:
    """소재 원문을 쉼표·슬래시·줄바꿈 기준 절로 나눈다.

    Args:
        text: `주요 소재` 원문입니다.

    Returns:
        절 목록입니다.
    """
    return [
        chunk.strip() for chunk in re.split(r"[,/\n]", text) if chunk.strip()
    ]


def normalize_material(
    text: str | None,
    category: str,
    attribute: str = "material",
    prefer: tuple[str, ...] = (),
    focus_words: tuple[str, ...] = (),
) -> str | None:
    """소재 원문에서 대표 소재 1개를 뽑아 허용값으로 정규화한다.

    판정 순서는 다음과 같다.

        1. `focus_words`(예: 프레임, 상판)가 들어 있는 절의 소재
        2. `prefer` 계열 소재 (예: 프레임은 철제/스틸, 소파는 표면 소재)
        3. 원문에 먼저 등장한 소재 (오늘의집은 보통 주자재를 앞에 쓴다)

    해당 카테고리에서 허용하지 않는 소재는 건너뛴다.

    Args:
        text: `주요 소재` 등의 원문입니다.
        category: 고정 대분류입니다.
        attribute: 소재 계열 속성 key입니다.
        prefer: 우선 채택할 정규 소재명입니다.
        focus_words: 이 단어가 들어간 절을 먼저 보게 합니다.

    Returns:
        허용값 표기의 소재명입니다. 근거가 없으면 None입니다.
    """
    if not text:
        return None

    try:
        allowed = catalog_spec.allowed_values(category, attribute)
    except KeyError:
        return None

    candidates: list[str] = []

    if focus_words:
        for chunk in material_chunks(text):
            if any(word in chunk for word in focus_words):
                candidates.extend(_material_hits(chunk))

    ordered = _material_hits(text)
    candidates.extend(name for name in prefer if name in ordered)
    candidates.extend(ordered)

    for canonical in candidates:
        fitted = _fit_material(canonical, allowed)
        if fitted is not None:
            return fitted
    return None


# ===========================================================================
# 침구 사이즈 / 수량 / 구간
# ===========================================================================
SIZE_KOREAN: dict[str, str] = {
    "멀티싱글": "멀티싱글(MS)",
    "슈퍼싱글": "슈퍼싱글(SS)",
    "라지킹": "라지킹(LK)",
    "칼킹": "칼킹(CK)",
    "싱글": "싱글(S)",
    "더블": "더블(D)",
    "퀸": "퀸(Q)",
    "킹": "킹(K)",
}

SIZE_LABEL: dict[str, str] = {
    "MS": "멀티싱글(MS)",
    "LK": "라지킹(LK)",
    "CK": "칼킹(CK)",
    "SS": "슈퍼싱글(SS)",
    "S": "싱글(S)",
    "D": "더블(D)",
    "Q": "퀸(Q)",
    "K": "킹(K)",
}

_SIZE_TOKENS = ["MS", "LK", "CK", "SS", "S", "D", "Q", "K"]
_LEVEL_RE = re.compile(r"(\d+)\s*단")
_SEAT_RE = re.compile(r"(\d+)\s*인용?")
_THICK_RE = re.compile(r"(\d+)\s*cm", re.IGNORECASE)


def normalize_bed_size(text: str | None) -> str | None:
    """옵션 텍스트에서 침구 사이즈를 뽑는다.

    한글 표기를 영문 약어보다 먼저 보고, MS·LK·CK 같은 긴 토큰을 S·K보다
    먼저 검사한다.

    Args:
        text: 옵션 원문 텍스트입니다.

    Returns:
        허용 사이즈 라벨입니다. 근거가 없으면 None입니다.
    """
    if not text:
        return None

    for korean, label in SIZE_KOREAN.items():
        if korean in text:
            return label

    upper = text.upper()
    for token in _SIZE_TOKENS:
        if re.search(rf"(?<![A-Z]){token}(?![A-Z])", upper):
            return SIZE_LABEL[token]
    return None


def normalize_level_count(text: str | None, allowed: list[str]) -> str | None:
    """`4단서랍장` -> `4단`. 5 이상은 `5단 이상`.

    Args:
        text: 상품명·옵션 텍스트입니다.
        allowed: 해당 속성의 허용값입니다.

    Returns:
        단 수 라벨입니다. 근거가 없으면 None입니다.
    """
    if not text:
        return None
    match = _LEVEL_RE.search(text)
    if not match:
        return None
    level = int(match.group(1))
    label = "5단 이상" if level >= 5 else f"{level}단"
    return label if (not allowed or label in allowed) else None


def normalize_seating_capacity(
    text: str | None, allowed: list[str]
) -> str | None:
    """`4인용 6인용 식탁` -> 가장 작은 인원 기준 `4인`.

    Args:
        text: 상품명·옵션 텍스트입니다.
        allowed: 해당 속성의 허용값입니다.

    Returns:
        사용인원 라벨입니다. 근거가 없으면 None입니다.
    """
    if not text:
        return None
    seats = [int(value) for value in _SEAT_RE.findall(text)]
    seats = [seat for seat in seats if 1 <= seat <= 20]
    if not seats:
        return None
    seat = min(seats)
    label = "8인 이상" if seat >= 8 else f"{seat}인"
    return label if (not allowed or label in allowed) else None


def normalize_thickness(text: str | None) -> str | None:
    """매트리스 두께(cm)를 구간 라벨로 바꾼다.

    Args:
        text: 상품명·옵션 텍스트입니다.

    Returns:
        두께 구간 라벨입니다. 근거가 없으면 None입니다.
    """
    if not text:
        return None
    match = _THICK_RE.search(text)
    if not match:
        return None
    thickness = int(match.group(1))
    if thickness <= 10:
        return "10cm 이하"
    if thickness <= 20:
        return "11~20cm"
    if thickness <= 30:
        return "21~30cm"
    return "31cm 이상"


def normalize_length(width_mm: int | None) -> str | None:
    """거실장 가로 길이(mm)를 구간 라벨로 바꾼다.

    Args:
        width_mm: 가로 길이(mm)입니다.

    Returns:
        길이 구간 라벨입니다. 값이 없으면 None입니다.
    """
    if not width_mm:
        return None
    width_cm = width_mm / 10
    if width_cm <= 120:
        return "120cm 이하"
    if width_cm <= 160:
        return "121~160cm"
    if width_cm <= 200:
        return "161~200cm"
    return "201cm 이상"


# ===========================================================================
# 치수
# ===========================================================================
_DIM_LABELLED = re.compile(
    r"W\s*(\d{2,5})\s*[xX*×]\s*D\s*(\d{2,5})\s*[xX*×]\s*H\s*(\d{2,5})",
    re.IGNORECASE,
)
_DIM_PLAIN = re.compile(r"(\d{2,5})\s*[xX*×]\s*(\d{2,5})\s*[xX*×]\s*(\d{2,5})")


def parse_dimensions(text: str | None) -> dict[str, int] | None:
    """`크기` 원문에서 W/D/H(mm)를 뽑는다. cm 표기는 mm로 환산한다.

    Args:
        text: specifications의 `크기` 원문입니다.

    Returns:
        width/depth/height(mm) 딕셔너리입니다. 못 읽으면 None입니다.
    """
    if not text:
        return None

    match = _DIM_LABELLED.search(text) or _DIM_PLAIN.search(text)
    if not match:
        return None

    width, depth, height = (int(value) for value in match.groups())
    if "cm" in text.lower() and max(width, depth, height) < 400:
        width, depth, height = width * 10, depth * 10, height * 10
    return {"width": width, "depth": depth, "height": height}


# ===========================================================================
# 불리언 / 열거형
# ===========================================================================
# 속성 -> (True 근거 키워드, False 근거 키워드). False를 먼저 확인한다.
BOOLEAN_KEYWORDS: dict[str, tuple[list[str], list[str]]] = {
    "has_legs": (["다리", "레그", "각재"], ["다리 없음", "무다리", "다리없음"]),
    "has_armrest": (
        ["팔걸이", "암레스트"],
        ["팔걸이 없음", "무팔걸이", "암리스", "팔걸이없음"],
    ),
    "has_headrest": (
        ["헤드레스트", "머리받침", "목받침"],
        ["헤드레스트 없음", "헤드리스"],
    ),
    "has_stool": (
        ["스툴 포함", "오토만 포함"],
        ["스툴 없음", "스툴미포함", "스툴없음", "추가 구매"],
    ),
    "has_headboard": (
        ["헤드보드", "헤드쿠션", "헤드 있음", "헤드형"],
        ["헤드리스", "헤드 없음", "무헤드"],
    ),
    "has_storage": (["수납", "서랍"], ["수납 없음", "무수납"]),
    "has_drawer": (["서랍"], ["서랍 없음", "무서랍"]),
    "has_wheels": (["바퀴", "캐스터"], ["바퀴 없음", "무바퀴"]),
    "has_backrest": (["등받이", "백레스트"], ["등받이 없음", "무등받이"]),
    "has_mirror": (["거울 포함", "거울포함"], ["거울 미포함", "거울없음"]),
    "has_frame": (["프레임 있음"], ["프레임리스", "무프레임", "노프레임"]),
}

# 속성 -> {허용값: [원문 키워드]}
ENUM_KEYWORDS: dict[str, dict[str, list[str]]] = {
    "sofa_type": {
        "카우치형": ["카우치"],
        "코너형": ["코너형", "ㄱ자", "L자"],
        "모듈형": ["모듈"],
        "좌식형": ["좌식"],
        "침대형": ["소파베드", "침대형"],
        "기본형(일자형)": ["일자형", "기본형", "인용소파", "인용 소파"],
    },
    "shape": {
        "타원형": ["타원"],
        "정사각형": ["정사각"],
        "직사각형": ["직사각"],
        "원형": ["원형", "라운드"],
        "아치형": ["아치"],
        "다각형": ["다각", "팔각", "육각"],
        "사각형": ["사각"],
    },
    "leg_type": {
        "T자형": ["T자", "T형"],
        "X자형": ["X자", "X형"],
        "원형베이스": ["원형베이스", "원형 베이스"],
        "4다리": ["4다리", "사각다리", "네다리"],
    },
    "door_type": {
        "미닫이형": ["미닫이"],
        "슬라이딩": ["슬라이딩"],
        "여닫이형": ["여닫이", "일반도어"],
        "여닫이": ["여닫이", "일반도어"],
        "폴딩형": ["폴딩", "접이"],
        "플랩형": ["플랩"],
        "유리도어": ["유리도어"],
        "오픈형": ["오픈형", "개방형", "도어없음"],
        "밀폐형": ["밀폐"],
    },
    "installation_type": {
        "벽걸이형": ["벽걸이", "벽부착"],
        "스탠드형": ["스탠드", "거치형"],
        "부착형": ["부착"],
        "설치형": ["설치형"],
    },
    "mattress_type": {
        "메모리폼": ["메모리폼"],
        "라텍스": ["라텍스"],
        "하이브리드": ["하이브리드 스프링"],
        "스프링": ["스프링", "본넬", "포켓"],
    },
    "firmness": {
        "하드": ["하드", "단단"],
        "소프트": ["소프트", "부드러"],
        "미디엄": ["미디엄", "중간"],
    },
    "layout_type": {
        "ㄷ자형": ["ㄷ자"],
        "ㄱ자형": ["ㄱ자", "코너"],
        "ㅡ자형": ["ㅡ자", "일자"],
    },
    "mobility_type": {
        "이동식": ["이동식", "바퀴"],
        "고정식": ["고정식", "붙박이"],
    },
    "wood_tone": {
        "밝은 우드톤": [
            "내추럴우드",
            "라이트우드",
            "밝은우드",
            "메이플",
            "비치",
        ],
        "중간 우드톤": ["미디엄우드", "티크", "체리"],
        "어두운 우드톤": ["다크우드", "월넛", "웬지", "멀바우", "어두운우드"],
    },
    "frame_type": {
        "하단수납형": ["하단수납", "수납형 프레임"],
        "하단밀폐형": ["하단밀폐", "밀폐형"],
        "매트일체형": ["일체형"],
        "하단오픈형": ["평상형", "저상형", "하단오픈"],
    },
    "product_type": {
        "프레임+매트리스": ["매트리스 포함", "프레임+매트리스"],
        "프레임만": ["프레임만", "침대프레임"],
    },
    "bed_type": {
        "수납침대": ["수납침대"],
        "패밀리침대": ["패밀리"],
        "아동용": ["아동", "키즈", "주니어"],
        "성인용": ["성인"],
    },
    "storage_features": {
        "서랍 포함": ["서랍 포함", "서랍포함"],
        "선반 포함": ["선반 포함", "선반포함"],
        "수납 없음": ["수납 없음"],
    },
    # 소분류만으로는 놓치는 유형 — 상품명에 더 구체적인 표기가 있을 때 쓴다.
    "tv_stand_type": {
        "높은형": ["높은거실장", "높은 거실장", "높은형", "사이드보드"],
        "전면수납형(책장형)": ["책장형"],
        "이젤형": ["이젤"],
        "스탠드형": ["tv스탠드", "티비스탠드"],
        "확장형": ["확장형"],
        "일반형": ["일반거실장"],
    },
    "vanity_type": {
        "전신거울형": ["전신거울형"],
        "벽걸이선반형": ["벽걸이선반"],
        "접이식": ["접이식"],
        "수납형": ["수납 화장대", "수납화장대"],
        "좌식형": ["좌식"],
        "미니형": ["미니 화장대", "미니화장대"],
        "콘솔형": ["콘솔"],
    },
    "shelf_type": {
        "앵글·조립식선반": ["앵글", "조립식", "경량랙"],
        "벽선반": ["벽선반", "월선반"],
        "스탠드선반": ["스탠드선반"],
    },
    "chair_type": {
        "게이밍의자": ["게이밍"],
        "학생·사무용의자": ["사무용", "학생용", "컴퓨터 의자", "책상 의자"],
        "바체어": ["바체어", "바 체어"],
        "안락의자": ["안락의자", "라운지체어"],
        "흔들의자": ["흔들의자", "락킹체어"],
        "빈백": ["빈백"],
        "발받침": ["발받침", "오토만"],
        "스툴·벤치": ["스툴", "벤치"],
    },
}


def normalize_boolean(attribute: str, text: str | None) -> bool | None:
    """불리언 속성을 텍스트 근거로만 판정한다.

    Args:
        attribute: 불리언 속성 key입니다.
        text: 판정에 쓸 통합 텍스트입니다.

    Returns:
        True/False입니다. 근거가 없으면 None입니다.
    """
    if not text or attribute not in BOOLEAN_KEYWORDS:
        return None

    lowered = text.lower()
    positive, negative = BOOLEAN_KEYWORDS[attribute]
    for keyword in negative:
        if keyword.lower() in lowered:
            return False
    for keyword in positive:
        if keyword.lower() in lowered:
            return True
    return None


def normalize_enum(
    attribute: str, text: str | None, allowed: list[str]
) -> str | None:
    """키워드 사전으로 열거형 속성을 판정한다.

    Args:
        attribute: 속성 key입니다.
        text: 판정에 쓸 통합 텍스트입니다.
        allowed: 해당 속성의 허용값입니다.

    Returns:
        허용값 중 하나입니다. 근거가 없으면 None입니다.
    """
    if not text or attribute not in ENUM_KEYWORDS:
        return None

    lowered = text.lower()
    for value, keywords in ENUM_KEYWORDS[attribute].items():
        if allowed and value not in allowed:
            continue
        for keyword in keywords:
            if keyword.lower() in lowered:
                return value
    return None


# ===========================================================================
# 스타일 / 무늬
# ===========================================================================
STYLE_KEYWORDS: dict[str, list[str]] = {
    "모던": ["모던", "미드센츄리", "미드센추리"],
    "클래식": ["클래식", "앤틱", "엔틱"],
    "빈티지": ["빈티지", "레트로"],
    "미니멀": ["미니멀", "심플"],
    "내추럴": ["내추럴", "네추럴"],
    "럭셔리": ["럭셔리", "호텔식", "고급스러운"],
    "인더스트리얼": ["인더스트리얼"],
    "북유럽": ["북유럽", "스칸디나비아", "노르딕"],
    "러블리": ["러블리", "아기자기"],
}

PATTERN_KEYWORDS: dict[str, list[str]] = {
    "마블": ["대리석", "마블"],
    "라탄·위빙": ["라탄", "위빙"],
    "우드그레인": ["우드그레인", "나뭇결", "무늬목"],
    "그래픽": ["체크", "하운즈투스", "스트라이프", "프린트", "플라워"],
    "패브릭 텍스처": ["부클", "니트", "텍스처"],
}


def normalize_style(text: str | None) -> str | None:
    """상품명·요약에 스타일 단어가 명시된 경우에만 판정한다.

    Args:
        text: 상품명·요약 텍스트입니다.

    Returns:
        허용 스타일입니다. 근거가 없으면 None입니다.
    """
    if not text:
        return None
    for style, keywords in STYLE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                return style
    return None


def normalize_pattern(text: str | None) -> str | None:
    """상품명·소재 원문에 무늬 단서가 있을 때만 판정한다.

    Args:
        text: 상품명·소재 텍스트입니다.

    Returns:
        허용 무늬입니다. 근거가 없으면 None입니다.
    """
    if not text:
        return None
    for pattern, keywords in PATTERN_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                return pattern
    return None


# ===========================================================================
# 상품명
# ===========================================================================
_NAME_NOISE_PATTERNS = [
    r"^\s*\[[^\]]*\]\s*",
    r"^\s*\d+%\s*쿠폰\s*[|ㅣ]?\s*",
    r"^\s*쿠폰가\s*[\d.,]+만?\s*[|ㅣ]?\s*",
    r"[^|ㅣ]*쿠폰[^|ㅣ]*[|ㅣ]",
    r"^\s*지정일배송[^|ㅣ]*[|ㅣ]\s*",
    r"^\s*무료설치[^|ㅣ]*[|ㅣ]\s*",
    r"\s*\(\s*\d+\s*c(olors?)?\s*\)",
    r"\s*\d+\s*colors?\b",
]

_PROMO_HINTS = ("쿠폰", "할인", "증정", "무료설치", "무료배송", "지정일배송")


def clean_product_name(name: str | None) -> str:
    """상품명에서 프로모션 말머리와 색상 개수 표기를 지운다.

    Args:
        name: 크롤링 원본 상품명입니다.

    Returns:
        정리된 상품명입니다.
    """
    if not name:
        return ""

    cleaned = name
    for pattern in _NAME_NOISE_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    tokens = cleaned.split()
    while (
        tokens
        and not set("|ㅣ") & set(tokens[0])
        and any(hint in tokens[0] for hint in _PROMO_HINTS)
    ):
        tokens.pop(0)
    cleaned = " ".join(tokens)

    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip(" |ㅣ-,")
