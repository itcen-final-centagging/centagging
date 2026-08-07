"""정답 SKU 이미지 5장을 보고 VLM으로 메타데이터를 추출하는 스크립트.
전체 흐름:
    1. 상품 이미지 5장 읽기
       대표 이미지 1장 + 각도 이미지 4장
    2. catalog_spec.py에서
       해당 대분류의 메타데이터와 허용값 조회
    3. 허용값을 포함한 VLM 프롬프트 생성
    4. Gemini VLM에 이미지 5장 + 프롬프트 전달
    5. VLM 응답의 메타데이터 검증
    6. answer_sku.json에 저장

실행 방법:

    python scripts/extract_answer_sku_metadata.py
"""
import json
import pathlib
import sys

from dotenv import find_dotenv, load_dotenv
from PIL import Image



# 프로젝트 경로 및 환경변수 설정
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent

sys.path.insert(
    0,
    str(PROJECT_ROOT),
)

load_dotenv(
    find_dotenv(usecwd=True),
    override=False,
)


from app.core import catalog_spec, config  # noqa: E402
from app.services import gemini_service  # noqa: E402



# 정답 SKU 기본 정보

# 상품 코드
SKU_CODE = "CHR-DIN-001"

# 상품명
PRODUCT_NAME = "TEODORES 테오도레스"

# 브랜드
BRAND = "IKEA"

# catalog_spec.CATEGORY_TREE에 정의된 대분류
CATEGORY = "의자"

# catalog_spec.CATEGORY_TREE에 정의된 소분류
SUB_CATEGORY = "식탁의자"



# 2. 정답 SKU 이미지 설정

IMAGE_DIR = (
    PROJECT_ROOT
    / "data"
    / "catalog"
    / "answer_sku"
    / "CHR-DIN-001"
)


# 이미지 파일 이름
IMAGE_FILENAMES = [
    "main.jpg",
    "angle_1.png",
    "angle_2.png",
    "angle_3.png",
    "angle_4.png",
]



# 결과 저장 경로
OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "catalog"
    / "answer_sku.json"
)



# 이미지 읽기
def load_images() -> list[Image.Image]:
    """정답 SKU 이미지 5장을 읽어온다.
    Returns:
        PIL Image 객체 목록.
    Raises:
        FileNotFoundError:
            이미지 파일이 존재하지 않을 경우.
    """
    images: list[Image.Image] = []

    for filename in IMAGE_FILENAMES:
        image_path = IMAGE_DIR / filename

        if not image_path.exists():
            raise FileNotFoundError(
                f"이미지를 찾을 수 없습니다: {image_path}\n"
                f"이미지 5장을 다음 폴더에 넣어주세요:\n"
                f"{IMAGE_DIR}"
            )

        image = Image.open(image_path)
        # Gemini에 넘길 이미지가 RGB가 되도록 통일한다.
        image = image.convert("RGB")
        images.append(image)

    return images

# VLM 프롬프트 생성
def build_prompt() -> str:
    """catalog_spec을 기준으로 VLM 프롬프트를 생성한다.
    catalog_spec에 정의된 속성과 허용값을 자동으로 가져오기 때문에
    메타데이터 허용값을 이 스크립트에서 별도로 관리하지 않는다.
    Returns:
        Gemini에 전달할 프롬프트 문자열.
    """
    lines = [
        "당신은 가구 상품 사진을 보고 상품 메타데이터를 분류하는 "
        "전문가입니다.",
        "",
        "아래 이미지는 동일한 가구 상품을 여러 각도에서 촬영한 "
        "사진입니다.",
        "",
        "모든 이미지를 종합해서 하나의 상품으로 판단하세요.",
        "",
        "각 속성마다 반드시 괄호 안에 제시된 허용값 중에서 "
        "가장 적절한 값을 하나만 선택하세요.",
        "",
        "허용값에 없는 새로운 값을 만들어내지 마세요.",
        "",
        f"상품 대분류: {CATEGORY}",
        f"상품 소분류: {SUB_CATEGORY}",
        "",
        "메타데이터:",
    ]

    # catalog_spec에서 공통 속성 키(색상, 스타일, 무늬)와 해당 대분류 전용 속성(유형, 주요소재, 등받이 형태 등)을 합쳐 반환한다.
    for attribute in catalog_spec.attribute_names(CATEGORY):
        # 예) 색상에 맞는 허용값을 가져온다.
        values = catalog_spec.allowed_values( CATEGORY, attribute)
        lines.append(
            f"- {attribute}: {', '.join(values)}"
        )

    # JSON 응답 형식
    lines += [
        "",
        "반드시 아래 JSON 형식으로만 답하세요.",
        "JSON 이외의 설명은 작성하지 마세요.",
        "",
        "{",
        '  "attributes": {',
        '    "속성명": "선택한 값"',
        "  },",
        '  "vlm_reason": "전체 이미지를 종합하여 '
        '판단한 이유를 한두 문장으로 설명"',
        "}",
        "",
        "주의사항:",
        "1. 위에서 제시한 모든 속성을 반드시 포함하세요.",
        "2. 각 속성의 값은 반드시 허용값 중 하나여야 합니다.",
        "3. 허용값과 다른 표현을 사용하지 마세요.",
        "4. 여러 이미지를 종합하여 판단하세요.",
    ]

    return "\n".join(lines)



# Gemini 호출
def ask_gemini(
    service: gemini_service.GeminiService,
    images: list[Image.Image],
    prompt: str,
) -> dict:
    """Gemini VLM에 이미지와 프롬프트를 전달한다.
    Args:
        service:
            프로젝트 공용 GeminiService.
        images:
            정답 SKU 이미지 목록.
        prompt:
            build_prompt()로 생성한 프롬프트.
    Returns:
        Gemini가 반환한 JSON을 Python dict로 변환한 결과.
    """

    return service.generate_vlm_json(
        images=images,
        prompt=prompt,
    )


# VLM 결과 검증
def validate_attributes(
    attributes: dict,
) -> None:
    """VLM이 반환한 메타데이터가 허용값인지 검증한다.
    검증 대상:
        catalog_spec.attribute_names(CATEGORY)
    검증 내용:
        - 모든 속성이 존재하는가?
        - 각 값이 허용값 목록에 포함되는가?
    Raises:
        ValueError:
            필수 속성이 없거나 허용되지 않은 값이 있는 경우.
    """

    expected_attributes = (
        catalog_spec.attribute_names(CATEGORY)
    )

    # 1. 필수 속성 누락 검사
    missing_attributes = [
        attribute
        for attribute in expected_attributes
        if attribute not in attributes
    ]

    if missing_attributes:
        raise ValueError(
            "다음 속성이 누락되었습니다: "
            f"{missing_attributes}"
        )


    # 2. 허용값 검사
    for attribute in expected_attributes:
        value = attributes[attribute]

        allowed = catalog_spec.allowed_values(
            CATEGORY,
            attribute,
        )

        if value not in allowed:
            raise ValueError(
                f"'{attribute}'의 값이 허용되지 않습니다: "
                f"{value!r}\n"
                f"허용값: {allowed}"
            )


# 결과 저장
def save_result(
    attributes: dict,
    vlm_reason: str | None = None,
) -> None:
    """검증된 정답 SKU 정보를 answer_sku.json에 저장한다.

    같은 sku_code가 이미 존재하면 기존 데이터를 삭제하고
    새로운 결과로 교체한다.
    """

    sku_record = {
        "sku_code": SKU_CODE,
        "product_name": PRODUCT_NAME,
        "brand": BRAND,
        "category": CATEGORY,
        "sub_category": SUB_CATEGORY,
        "attributes": attributes,
    }


    # VLM 판단 이유가 있으면 저장
    if vlm_reason:
        sku_record["vlm_reason"] = vlm_reason



    # 기존 파일 읽기
    if OUTPUT_PATH.exists():
        existing_records = json.loads(
            OUTPUT_PATH.read_text(
                encoding="utf-8",
            )
        )
    else:
        existing_records = []


    # 같은 SKU 제거
    existing_records = [
        record
        for record in existing_records
        if record.get("sku_code") != SKU_CODE
    ]
    # 새 결과 추가
    existing_records.append(
        sku_record
    )

    # 폴더 생성
    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # JSON 저장
    OUTPUT_PATH.write_text(
        json.dumps(
            existing_records,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


    print(
        f"저장 완료: {OUTPUT_PATH}"
    )

# 전체 실행

def main() -> None:
    """정답 SKU 메타데이터 추출 전체 과정을 실행한다."""
    # GeminiService 초기화
    print(
        "0) GeminiService 초기화 중..."
    )

    settings = config.get_settings()

    service = gemini_service.GeminiService(
        settings
    )

    if not service.is_configured:
        raise RuntimeError(
            "GEMINI_API_KEY가 설정되지 않았습니다. "
            ".env 파일을 확인해주세요."
        )

    # 1. 이미지 읽기
    print("1) 정답 SKU 이미지 5장을 불러오는 중...")
    images = load_images()

    print(f"   이미지 {len(images)}장 로드 완료")

    # 2. 프롬프트 생성
    print("2) catalog_spec 기준으로 "
               "VLM 프롬프트를 만드는 중...")

    prompt = build_prompt()


    # 3. Gemini 호출

    print("3) Gemini VLM에 이미지 5장을 전달하는 중...")

    result = ask_gemini(
        service=service,
        images=images,
        prompt=prompt,
    )


    # 4. attributes 추출
    if "attributes" not in result:
        raise ValueError( "Gemini 응답에 'attributes'가 없습니다.")

    attributes = result["attributes"]


    # 5. 메타데이터 검증
    print( "4) VLM 결과가 catalog_spec의 "
           "허용값인지 검증하는 중...")

    validate_attributes(attributes)



    # 5. 결과 저장
    print("5) 정답 SKU 메타데이터를 저장하는 중...")

    save_result(
        attributes=attributes,
        vlm_reason=result.get("vlm_reason"),
    )


    # 6. 결과 출력
    print("\n=== 정답 SKU 메타데이터 추출 완료 ===")

    print(
        json.dumps(
            attributes,
            ensure_ascii=False,
            indent=2,
        )
    )


    if result.get("vlm_reason"):
        print("\n=== Gemini 판단 이유 ===")

        print( result["vlm_reason"])


# Entry Point
if __name__ == "__main__":
    main()