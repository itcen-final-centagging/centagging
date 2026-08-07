"""CenTagging SKU 카탈로그 메타데이터 스펙.

계획된 카탈로그 구성과 SKU 이미지에서 추출할 메타데이터의
허용값을 정의한다.

이 모듈은 다음 작업에서 공통으로 참조하는 단일 기준이다.

- SKU 카탈로그 생성
- VLM 메타데이터 생성
- 메타데이터 검증
- SKU 검색/매칭 데이터 생성

카탈로그 구성:
    4개 대분류 × 3개 소분류

SKU 이미지 구성:
    SKU당 대표 이미지 1장 + 각도 이미지 4장 = 5장
"""


# 카탈로그 분류 체계
CATEGORY_TREE: dict[str, list[str]] = {
    "의자": [
        "식탁의자",
        "사무용의자",
        "스툴·바의자",
    ],
    "테이블": [
        "식탁",
        "책상",
        "거실·사이드테이블",
    ],
    "소파·안락가구": [
        "일반 소파",
        "암체어·안락의자",
        "소파베드·카우치",
    ],
    "수납가구": [
        "책장·선반유닛",
        "수납장·장식장",
        "서랍장·침대협탁",
    ],
}


# 공통 속성
COMMON_ATTRIBUTES: dict[str, list[str]] = {
    "색상": [
        "화이트",
        "블랙",
        "그레이",
        "베이지",
        "브라운",
        "네이비",
        "그린",
        "블루",
    ],
    "스타일": [
        "북유럽",
        "모던",
        "미니멀",
        "내추럴",
        "클래식",
        "인더스트리얼",
    ],
    "무늬": [
        "무지",
        "우드그레인",
        "라탄·위빙",
    ],
}


# 대분류별 전용 속성
CATEGORY_ATTRIBUTES: dict[str, dict[str, list[str]]] = {

    # 의자
    # 소분류: 식탁의자 / 사무용의자 / 스툴·바의자
    # 유형은 소분류와 겹치지 않도록 형태·사용 방식 중심으로 정의

    "의자": {
        "유형": [
            "일반형",
            "회전형",
            "접이식",
            "벤치형",
            "스툴형",
            "바체어형",
        ],
        "주요 소재": [
            "우드",
            "플라스틱",
            "금속",
            "메쉬",
            "패브릭",
            "가죽",
        ],
        "등받이 형태": [
            "하이백",
            "미드백",
            "등받이 없음",
        ],
        "다리 형태": [
            "4다리",
            "5스타 캐스터",
            "중심봉",
            "3다리",
        ],
        "팔걸이": [
            "있음",
            "없음",
        ],
    },



    # 테이블
    # 소분류: 식탁 / 책상 / 거실·사이드테이블
    # 유형은 용도가 아닌 구조·사용 방식 중심으로 정의

    "테이블": {
        "유형": [
            "일반형",
            "확장형",
            "접이식",
            "높이조절형",
            "다단형",
        ],
        "형태": [
            "원형",
            "사각형",
            "타원형",
        ],
        "상판 소재": [
            "우드",
            "유리",
            "금속",
        ],
        "프레임 소재": [
            "우드",
            "금속",
        ],
        "다리 형태": [
            "4다리",
            "T자형",
            "X자형",
            "원형베이스",
        ],
        "우드톤": [
            "밝은 우드톤",
            "중간 우드톤",
            "어두운 우드톤",
            "해당 없음",
        ],
    },



    # 소파·안락가구
    # 소분류: 일반 소파 / 암체어·안락의자 / 소파베드·카우치
    # 유형은 제품명 대신 구조·기능 중심으로 정의
    "소파·안락가구": {
        "유형": [
            "일반형",
            "모듈형",
            "리클라이너형",
            "접이식",
            "변형형",
        ],
        "인원": [
            "1인",
            "2인",
            "3인",
            "4인 이상",
        ],
        "형태": [
            "기본형",
            "카우치형",
            "코너형",
            "일자형",
            "곡선형",
        ],
        "주요 소재": [
            "패브릭",
            "가죽",
            "벨벳",
        ],
        "팔걸이": [
            "있음",
            "없음",
        ],
        "헤드레스트": [
            "있음",
            "없음",
        ],
    },



    # 수납가구
    # 소분류: 책장·선반유닛 / 수납장·장식장 / 서랍장·침대협탁
    # 유형은 제품명 대신 구조·사용 방식 중심으로 정의
    "수납가구": {
        "유형": [
            "오픈형",
            "폐쇄형",
            "혼합형",
            "모듈형",
            "다단형",
        ],
        "설치 형태": [
            "스탠드형",
            "벽부착형",
            "이동형",
        ],
        "단 수": [
            "1단",
            "2단",
            "3단",
            "4단",
            "5단 이상",
        ],
        "주요 소재": [
            "우드",
            "금속",
            "유리",
        ],
        "도어 형태": [
            "오픈형",
            "여닫이형",
            "미닫이형",
            "유리도어",
            "플랩형",
        ],
        "서랍": [
            "있음",
            "없음",
        ],
        "우드톤": [
            "밝은 우드톤",
            "중간 우드톤",
            "어두운 우드톤",
            "해당 없음",
        ],
    },
}


# SKU / 이미지 구성

SKU_PER_SUB_CATEGORY: int = 12

MAIN_IMAGES_PER_SKU: int = 1

ANGLE_IMAGES_PER_SKU: int = 4

IMAGES_PER_SKU: int = (
    MAIN_IMAGES_PER_SKU + ANGLE_IMAGES_PER_SKU
)


# 메타데이터 조회 함수
def attribute_names(category: str) -> list[str]:
    """해당 대분류에서 사용하는 전체 속성명을 반환한다.
    공통 속성과 해당 대분류 전용 속성을 합쳐 반환한다.
    예:
        의자
        -> 색상
        -> 스타일
        -> 무늬
        -> 유형
        -> 주요 소재
        -> 등받이 형태
        -> 다리 형태
        -> 팔걸이
    """

    if category not in CATEGORY_TREE:
        raise KeyError(
            f"정의되지 않은 대분류입니다: {category}"
        )

    return (list(COMMON_ATTRIBUTES.keys()) + list(CATEGORY_ATTRIBUTES[category].keys()))


def allowed_values(category: str, attribute: str,) -> list[str]:
    """해당 대분류와 속성에서 허용되는 값을 반환한다."""
    if category not in CATEGORY_TREE:
        raise KeyError(
            f"정의되지 않은 대분류입니다: {category}"
        )

    # 공통 속성
    if attribute in COMMON_ATTRIBUTES:
        return COMMON_ATTRIBUTES[attribute]

    # 대분류별 전용 속성
    if attribute in CATEGORY_ATTRIBUTES[category]:
        return CATEGORY_ATTRIBUTES[category][attribute]

    raise KeyError(
        f"'{category}'에서 정의되지 않은 속성입니다: "
        f"{attribute}"
    )


def total_sub_category_count() -> int:
    """전체 소분류 수를 반환한다."""
    return sum(
        len(sub_categories) for sub_categories in CATEGORY_TREE.values()
    )


def total_sku_count() -> int:
    """전체 SKU 수를 반환한다.
    4개 대분류 × 3개 소분류 × 12 SKU = 144 SKU
    """
    return (total_sub_category_count() * SKU_PER_SUB_CATEGORY)


def total_image_count() -> int:
    """전체 SKU 이미지 수를 반환한다.
    SKU당 대표 이미지 1장 + 각도 이미지 4장 = 5장
    144 SKU × 5장 = 720장
    """

    return (
        total_sku_count()
        * IMAGES_PER_SKU
    )
