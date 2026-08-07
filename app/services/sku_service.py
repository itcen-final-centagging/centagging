"""신규 SKU 등록에 필요한 AI 추출·DB·스토리지 로직입니다.

Service functions backing the new-SKU-registration API: Gemini
metadata extraction, catalog lookups, transactional save, and local
image storage.
"""

import collections.abc
import json
import pathlib
import typing
import uuid

import sqlalchemy
from google import genai
from google.genai import types
from sqlalchemy.ext import asyncio as sqlalchemy_async

from app.core import config
from app.models import sku as sku_models

# 참고: kosa-poc-main/image-generation/common/config.py의 분류 체계를
# 단순화해 재사용합니다. / Simplified from the kosa-poc-main taxonomy.
_CATEGORY_TAXONOMY: dict[str, list[str]] = {
    "침대": ["침대프레임", "침대+매트리스", "침대부속가구"],
    "테이블·식탁·책상": ["소파테이블", "사이드테이블", "식탁", "책상"],
    "소파": ["일반소파", "리클라이너", "소파베드", "좌식소파"],
    "서랍·수납장": ["서랍장", "수납장", "캐비닛", "협탁"],
    "거실장·TV장": ["일반거실장", "높은거실장", "TV스탠드"],
    "선반": ["벽선반", "스탠드선반", "조립식선반"],
    "진열장·책장": ["진열장", "책장", "매거진랙"],
    "의자": ["인테리어의자", "스툴·벤치", "안락의자", "사무용의자"],
    "행거·옷장": ["옷장", "붙박이장", "행거"],
    "조명": ["스탠드조명", "천장조명", "무드등"],
}

_COLOR_OPTIONS = [
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

# schema.sql / kosa-poc-main 어디에도 없어 이번에 새로 정의합니다.
_SPACE_OPTIONS = [
    "거실",
    "침실",
    "주방",
    "서재·홈오피스",
    "아이방",
    "드레스룸",
    "현관",
    "발코니·테라스",
]

_UPLOAD_ROOT = pathlib.Path("uploads") / "sku"


class SkuConfigurationError(RuntimeError):
    """Gemini API 키가 누락된 경우 발생합니다."""


class SkuExtractionError(RuntimeError):
    """AI 메타데이터 추출이 실패한 경우 발생합니다."""


class SkuCodeDuplicateError(RuntimeError):
    """저장 시점에 SKU 코드가 이미 존재하는 경우 발생합니다."""


class ExtractedMetadata(typing.TypedDict):
    """AI가 추출한 SKU 메타데이터입니다."""

    category: typing.Optional[str]
    sub_category: typing.Optional[str]
    space: typing.Optional[str]
    attributes: dict[str, str]


def _build_extraction_prompt() -> str:
    """AI 메타데이터 추출에 사용할 프롬프트를 만듭니다.

    Returns:
        카테고리·공간·색상 후보와 출력 스키마를 담은 프롬프트
        문자열입니다.
    """
    categories = json.dumps(_CATEGORY_TAXONOMY, ensure_ascii=False)
    spaces = ", ".join(_SPACE_OPTIONS)
    colors = ", ".join(_COLOR_OPTIONS)
    return (
        "당신은 가구 상품 이미지를 분석하는 카탈로그 태거입니다. "
        "이미지 속 가구 1개를 보고 아래 스키마의 JSON만 출력하세요.\n"
        f"category는 다음 목록의 키 중 하나, sub_category는 그 값 "
        f"목록 중 하나를 고르세요: {categories}\n"
        f"space는 다음 중 하나를 고르세요: {spaces}\n"
        f"attributes.색상은 다음 중 가장 가까운 것을 고르세요: {colors}\n"
        "attributes.주요 소재는 이미지에서 보이는 대로 자유롭게 "
        "적으세요.\n"
        "확신할 수 없는 값은 빈 문자열로 두세요. 출력 스키마: "
        '{"category": "", "sub_category": "", "space": "", '
        '"attributes": {"색상": "", "주요 소재": ""}}'
    )


def extract_metadata(
    settings: config.Settings, image_bytes: bytes, mime_type: str
) -> ExtractedMetadata:
    """이미지에서 카테고리·하위카테고리·공간·속성을 추출합니다.

    Args:
        settings: Gemini API 키와 모델명이 담긴 애플리케이션 설정입니다.
        image_bytes: 분석할 이미지의 원본 바이트입니다.
        mime_type: 이미지의 MIME 타입입니다.

    Returns:
        추출된 category, sub_category, space, attributes입니다.

    Raises:
        SkuConfigurationError: Gemini API 키가 설정되지 않은 경우입니다.
        SkuExtractionError: Gemini 호출 또는 응답 파싱에 실패한
            경우입니다.
    """
    if not settings.gemini_api_key:
        raise SkuConfigurationError(
            "GEMINI_API_KEY is not configured. "
            "Create .env from .env.example."
        )

    try:
        client = genai.Client(api_key=settings.gemini_api_key)
        # google-genai의 Content 유니온 타입 스텁이 리스트 불변성과
        # 맞지 않아 명시적으로 캐스팅합니다 (외부 SDK 경계).
        contents = typing.cast(
            typing.Any,
            [
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                _build_extraction_prompt(),
            ],
        )
        response = client.models.generate_content(
            model=settings.gemini_vlm_model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            ),
        )
        if not response.text:
            raise RuntimeError("Gemini returned an empty response.")
        data = json.loads(response.text)
    except (
        Exception
    ) as error:  # External SDK boundary; re-raise a domain error.
        raise SkuExtractionError(
            "Gemini metadata extraction failed."
        ) from error

    attributes = data.get("attributes")
    return {
        "category": data.get("category") or None,
        "sub_category": data.get("sub_category") or None,
        "space": data.get("space") or None,
        "attributes": attributes if isinstance(attributes, dict) else {},
    }


def save_uploaded_image(sku_code: str, filename: str, content: bytes) -> str:
    """업로드된 이미지를 로컬 스토리지에 저장하고 공개 경로를 반환합니다.

    Args:
        sku_code: 이미지가 속한 SKU 코드입니다 (저장 경로 구분용).
        filename: 업로드된 원본 파일명입니다 (확장자 판별용).
        content: 이미지의 원본 바이트입니다.

    Returns:
        ``/uploads``로 정적 서빙되는 상대 경로입니다.
    """
    extension = pathlib.Path(filename).suffix.lower() or ".jpg"
    target_dir = _UPLOAD_ROOT / sku_code
    target_dir.mkdir(parents=True, exist_ok=True)
    target_name = f"{uuid.uuid4().hex}{extension}"
    (target_dir / target_name).write_bytes(content)
    return f"/uploads/sku/{sku_code}/{target_name}"


async def find_sku_by_code(
    session: sqlalchemy_async.AsyncSession, sku_code: str
) -> typing.Optional[sku_models.SkuCatalog]:
    """SKU 코드와 정확히 일치하는 SKU를 조회합니다.

    Args:
        session: 비동기 DB 세션입니다.
        sku_code: 조회할 SKU 코드입니다.

    Returns:
        일치하는 SKU가 있으면 해당 레코드, 없으면 None입니다.
    """
    result = await session.execute(
        sqlalchemy.select(sku_models.SkuCatalog).where(
            sku_models.SkuCatalog.sku_code == sku_code
        )
    )
    return result.scalar_one_or_none()


async def find_skus_by_product_name(
    session: sqlalchemy_async.AsyncSession,
    product_name: str,
    limit: int = 10,
) -> collections.abc.Sequence[sku_models.SkuCatalog]:
    """상품명과 정확히 일치하는 SKU 목록을 조회합니다.

    Args:
        session: 비동기 DB 세션입니다.
        product_name: 조회할 상품명입니다.
        limit: 최대 반환 건수입니다.

    Returns:
        일치하는 SKU 목록입니다 (0건 이상).
    """
    result = await session.execute(
        sqlalchemy.select(sku_models.SkuCatalog)
        .where(sku_models.SkuCatalog.product_name == product_name)
        .limit(limit)
    )
    return result.scalars().all()


async def create_sku(  # pylint: disable=too-many-arguments
    session: sqlalchemy_async.AsyncSession,
    *,
    sku_code: str,
    product_name: str,
    brand: typing.Optional[str],
    price: typing.Optional[int],
    space: typing.Optional[str],
    category: typing.Optional[str],
    sub_category: typing.Optional[str],
    attributes: dict[str, typing.Any],
    image_url: str,
) -> sku_models.SkuCatalog:
    """신규 SKU와 대표 이미지를 하나의 트랜잭션으로 저장합니다.

    Args:
        session: 비동기 DB 세션입니다.
        sku_code: 신규 SKU 코드입니다 (중복 불가).
        product_name: 상품명입니다.
        brand: 브랜드입니다 (수동 입력 전용).
        price: 가격입니다 (수동 입력 전용).
        space: 사용 공간입니다.
        category: 대분류입니다.
        sub_category: 소분류입니다.
        attributes: 색상·소재 등 자유 속성입니다.
        image_url: 저장된 대표 이미지 경로입니다.

    Returns:
        생성된 SKU 레코드입니다.

    Raises:
        SkuCodeDuplicateError: 저장 시점에 SKU 코드가 이미 존재하는
            경우입니다.
    """
    sku = sku_models.SkuCatalog(
        sku_code=sku_code,
        product_name=product_name,
        brand=brand,
        price=price,
        space=space,
        category=category,
        sub_category=sub_category,
        attributes=attributes,
    )
    session.add(sku)
    try:
        await session.flush()
        session.add(
            sku_models.SkuImage(
                sku_id=sku.sku_id, image_url=image_url, image_type="MAIN"
            )
        )
        await session.commit()
    except sqlalchemy.exc.IntegrityError as error:
        await session.rollback()
        raise SkuCodeDuplicateError(
            f"SKU code already exists: {sku_code}"
        ) from error
    await session.refresh(sku)
    return sku


async def list_skus(
    session: sqlalchemy_async.AsyncSession, limit: int = 50
) -> collections.abc.Sequence[typing.Any]:
    """등록된 SKU를 최신순으로 대표 이미지와 함께 조회합니다.

    Args:
        session: 비동기 DB 세션입니다.
        limit: 최대 반환 건수입니다.

    Returns:
        ``(SkuCatalog, main_image_url)`` 튜플의 목록입니다. 대표
        이미지가 없으면 ``main_image_url``은 None입니다.
    """
    stmt = (
        sqlalchemy.select(sku_models.SkuCatalog, sku_models.SkuImage.image_url)
        .outerjoin(
            sku_models.SkuImage,
            sqlalchemy.and_(
                sku_models.SkuImage.sku_id == sku_models.SkuCatalog.sku_id,
                sku_models.SkuImage.image_type == "MAIN",
            ),
        )
        .order_by(sku_models.SkuCatalog.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return result.all()
