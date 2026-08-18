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

import pydantic
import sqlalchemy
from google.genai import types
from sqlalchemy.ext import asyncio as sqlalchemy_async

from app.core import config, genai_client
from app.models import sku as sku_models
from app.services import sku_attributes

_UPLOAD_SUBDIR = "sku"


class SkuConfigurationError(RuntimeError):
    """Google Gen AI 인증 설정이 누락된 경우 발생합니다."""


class SkuExtractionError(RuntimeError):
    """AI 메타데이터 추출이 실패한 경우 발생합니다."""


class SkuCodeDuplicateError(RuntimeError):
    """저장 시점에 SKU 코드가 이미 존재하는 경우 발생합니다."""


class ExtractedMetadata(typing.TypedDict):
    """AI가 추출한 SKU 메타데이터입니다."""

    category: typing.Optional[str]
    sub_category: typing.Optional[str]
    space: typing.Optional[str]
    attributes: dict[str, typing.Any]


class _CategoryMetadata(pydantic.BaseModel):
    """1차 호출(category/sub_category/space) 응답 스키마입니다."""

    category: typing.Optional[str] = None
    sub_category: typing.Optional[str] = None
    space: typing.Optional[str] = None


def _build_category_prompt() -> str:
    """1차 호출(category/sub_category/space 추출)용 프롬프트를 만듭니다.

    Returns:
        카테고리·공간 후보 목록을 담은 프롬프트 문자열입니다.
    """
    categories = json.dumps(
        sku_attributes.CATEGORY_TAXONOMY, ensure_ascii=False
    )
    spaces = ", ".join(sku_attributes.SPACE_OPTIONS)
    template = """당신은 가구 상품 이미지를 분석하는 카탈로그 태거입니다.
이미지 속 가구 1개를 보고 category, sub_category, space를 정하세요.
category는 다음 목록의 키 중 하나, sub_category는 그 값 목록 중 하나를 고르세요: {categories}
space는 다음 중 하나를 고르세요: {spaces}
확신할 수 없는 값은 비워두세요."""
    return template.format(categories=categories, spaces=spaces)


def _build_attributes_prompt(
    category: str, sub_category: typing.Optional[str]
) -> str:
    """2차 호출(category별 attributes 추출)용 프롬프트를 만듭니다.

    Args:
        category: 1차 호출에서 정해진 대분류입니다.
        sub_category: 1차 호출에서 정해진 소분류입니다 (있는 경우).

    Returns:
        해당 category 스키마에 맞는 값을 채우도록 안내하는 프롬프트
        문자열입니다.
    """
    colors = ", ".join(sku_attributes.COLOR_OPTIONS)
    category_template = "category={0}"
    context = category_template.format(category)
    if sub_category:
        sub_category_template = ", sub_category={0}"
        context += sub_category_template.format(sub_category)
    template = """
        당신은 가구 상품 이미지를 분석하는 카탈로그 태거입니다.
        이미지 속 가구는 {context}입니다.
        주어진 스키마의 각 필드 값을 이미지를 보고 채우세요.
        color는 다음 중 하나를 고르세요: {colors}
        선택(optional) 필드는 확신할 수 없으면 비워두세요.
    """
    return template.format(context=context, colors=colors)


def extract_metadata(
    settings: config.Settings, image_bytes: bytes, mime_type: str
) -> ExtractedMetadata:
    """이미지에서 카테고리·하위카테고리·공간·속성을 추출합니다.

    category/sub_category/space를 먼저 정한 뒤(1차 호출), 그 category에
    해당하는 :mod:`app.services.sku_attributes` 스키마를
    ``response_schema``로 강제해 attributes를 채웁니다(2차 호출).
    카테고리에 맞는 attributes 스키마가 없으면(예: 답안 데이터가 없는
    카테고리) 2차 호출 없이 attributes를 빈 dict로 둡니다.

    Args:
        settings: Google Gen AI 인증과 모델명이 담긴 설정입니다.
        image_bytes: 분석할 이미지의 원본 바이트입니다.
        mime_type: 이미지의 MIME 타입입니다.

    Returns:
        추출된 category, sub_category, space, attributes입니다.

    Raises:
        SkuConfigurationError: Google Gen AI 인증 설정이 없는 경우입니다.
        SkuExtractionError: Gemini 호출 또는 응답 파싱에 실패한
            경우입니다.
    """
    if not genai_client.is_configured(settings):
        raise SkuConfigurationError(
            "Google Gen AI authentication is not configured."
        )

    try:
        client = genai_client.create_client(settings)
        image_part = types.Part.from_bytes(
            data=image_bytes, mime_type=mime_type
        )

        category_response = client.models.generate_content(
            model=settings.gemini_vlm_model,
            # google-genai의 Content 유니온 타입 스텁이 리스트 불변성과
            # 맞지 않아 명시적으로 캐스팅합니다 (외부 SDK 경계).
            contents=typing.cast(
                typing.Any, [image_part, _build_category_prompt()]
            ),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_CategoryMetadata,
            ),
        )
        if not category_response.text:
            raise RuntimeError("Gemini returned an empty response.")
        category_data = _CategoryMetadata.model_validate_json(
            category_response.text
        )

        attributes: dict[str, typing.Any] = {}
        category = category_data.category
        attribute_model = (
            sku_attributes.CATEGORY_ATTRIBUTE_MODELS.get(category)
            if category
            else None
        )
        if category and attribute_model is not None:
            attributes_response = client.models.generate_content(
                model=settings.gemini_vlm_model,
                contents=typing.cast(
                    typing.Any,
                    [
                        image_part,
                        _build_attributes_prompt(
                            category, category_data.sub_category
                        ),
                    ],
                ),
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=attribute_model,
                ),
            )
            if attributes_response.text:
                attributes = attribute_model.model_validate_json(
                    attributes_response.text
                ).model_dump(exclude_none=True)
    except (
        Exception
    ) as error:  # External SDK boundary; re-raise a domain error.
        raise SkuExtractionError(
            "Gemini metadata extraction failed."
        ) from error

    return {
        "category": category_data.category,
        "sub_category": category_data.sub_category,
        "space": category_data.space,
        "attributes": attributes,
    }


def save_uploaded_image(
    settings: config.Settings, sku_code: str, filename: str, content: bytes
) -> str:
    """업로드된 이미지를 로컬 스토리지에 저장하고 공개 경로를 반환합니다.

    Args:
        settings: 이미지 저장 루트(``image_storage_root``)가 담긴
            애플리케이션 설정입니다.
        sku_code: 이미지가 속한 SKU 코드입니다 (저장 경로 구분용).
        filename: 업로드된 원본 파일명입니다 (확장자 판별용).
        content: 이미지의 원본 바이트입니다.

    Returns:
        ``/uploads``로 정적 서빙되는 상대 경로입니다.
    """
    extension = pathlib.Path(filename).suffix.lower() or ".jpg"
    target_dir = (
        pathlib.Path(settings.image_storage_root) / _UPLOAD_SUBDIR / sku_code
    )
    target_dir.mkdir(parents=True, exist_ok=True)
    target_name = f"{uuid.uuid4().hex}{extension}"
    (target_dir / target_name).write_bytes(content)
    return f"/uploads/{_UPLOAD_SUBDIR}/{sku_code}/{target_name}"


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


async def add_sku_images(
    session: sqlalchemy_async.AsyncSession,
    *,
    sku_id: int,
    image_urls: list[str],
    image_type: str,
) -> list[sku_models.SkuImage]:
    """기존 SKU에 같은 유형의 이미지를 여러 장 추가합니다.

    일괄 업로드 화면은 파일을 여러 장 올려도 유형 선택은 한 번에
    적용하므로, 이 함수도 하나의 ``image_type``으로 이미지 목록을
    저장합니다. 파일별로 다른 유형이 필요하면 호출을 나누면 됩니다.

    Args:
        session: 요청 범위의 비동기 DB 세션입니다.
        sku_id: 이미지를 추가할 기존 SKU 식별자입니다.
        image_urls: 스토리지에 저장된 공개 이미지 경로 목록입니다.
        image_type: MAIN | ANGLE | DETAIL | STYLING 중 하나입니다.

    Returns:
        새로 생성된 SKU 이미지 행 목록입니다.
    """
    images = [
        sku_models.SkuImage(
            sku_id=sku_id,
            image_url=image_url,
            image_type=image_type,
        )
        for image_url in image_urls
    ]
    session.add_all(images)
    try:
        await session.flush()
        await session.commit()
    except sqlalchemy.exc.SQLAlchemyError:
        await session.rollback()
        raise
    return images


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
