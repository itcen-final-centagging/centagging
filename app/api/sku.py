# pylint: disable=duplicate-code
# create_sku()의 키워드 인자 목록이 app.services.sku_service.create_sku
# 시그니처와 자연스럽게 겹쳐 발생하는 오탐입니다.
"""신규 SKU 등록 API입니다. / New SKU registration API."""

import datetime
import json
import typing

import fastapi
import pydantic
from sqlalchemy.ext import asyncio as sqlalchemy_async

from app.core import config, database
from app.services import sku_service

router = fastapi.APIRouter(prefix="/api/centagging/sku", tags=["sku"])

_ALLOWED_MIME_TYPES = {"image/jpeg", "image/png"}
_MAX_IMAGE_SIZE = 10 * 1024 * 1024


class MetadataExtractResponse(pydantic.BaseModel):
    """AI가 추출한 메타데이터 응답입니다."""

    category: typing.Optional[str] = None
    sub_category: typing.Optional[str] = None
    space: typing.Optional[str] = None
    attributes: dict[str, typing.Any] = pydantic.Field(default_factory=dict)


class SkuSummary(pydantic.BaseModel):
    """유사/중복 조회에서 노출하는 SKU 요약 정보입니다."""

    sku_id: int
    sku_code: str
    product_name: str


class NameCheckResponse(pydantic.BaseModel):
    """상품명 정확 일치 조회 응답입니다."""

    exists: bool
    matched: list[SkuSummary]


class CodeCheckResponse(pydantic.BaseModel):
    """SKU 코드 정확 일치 조회 응답입니다."""

    sku_code: str
    exists: bool


class SkuCreateResponse(pydantic.BaseModel):
    """신규 SKU 저장 응답입니다."""

    sku_id: int
    sku_code: str
    product_name: str
    main_image_url: str


class SkuCatalogItem(pydantic.BaseModel):
    """카탈로그 목록의 SKU 한 건입니다."""

    sku_id: int
    sku_code: str
    product_name: str
    brand: typing.Optional[str] = None
    price: typing.Optional[int] = None
    space: typing.Optional[str] = None
    category: typing.Optional[str] = None
    sub_category: typing.Optional[str] = None
    attributes: dict[str, typing.Any] = pydantic.Field(default_factory=dict)
    main_image_url: typing.Optional[str] = None
    created_at: datetime.datetime


class SkuCatalogListResponse(pydantic.BaseModel):
    """전체 카탈로그 목록 응답입니다."""

    items: list[SkuCatalogItem]


def _validate_image(content: bytes, content_type: typing.Optional[str]) -> None:
    """업로드 이미지의 형식과 용량을 검증합니다.

    Args:
        content: 업로드된 이미지의 원본 바이트입니다.
        content_type: 업로드 요청의 MIME 타입입니다.

    Raises:
        fastapi.HTTPException: 형식이 다르거나 10MB를 초과한 경우입니다.
    """
    if content_type not in _ALLOWED_MIME_TYPES:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="JPG, PNG 파일만 업로드 가능합니다.",
        )
    if len(content) > _MAX_IMAGE_SIZE:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="파일 용량은 최대 10MB까지 가능합니다.",
        )


@router.post("/extract", response_model=MetadataExtractResponse)
async def extract_metadata(
    image: fastapi.UploadFile = fastapi.File(...),
) -> MetadataExtractResponse:
    """업로드 이미지를 분석해 SKU 메타데이터를 추출합니다.

    DB에 아무것도 저장하지 않는 상태 없는(stateless) 호출입니다.

    Args:
        image: 분석 대상 이미지입니다.

    Returns:
        추출된 category, sub_category, space, attributes입니다.

    Raises:
        fastapi.HTTPException: 이미지가 유효하지 않거나(422) AI 설정이
            없거나(503) 호출이 실패한 경우(502)입니다.
    """
    content = await image.read()
    _validate_image(content, image.content_type)

    settings = config.get_settings()
    try:
        result = sku_service.extract_metadata(
            settings, content, image.content_type or "image/jpeg"
        )
    except sku_service.SkuConfigurationError as error:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gemini API key is not configured.",
        ) from error
    except sku_service.SkuExtractionError as error:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_502_BAD_GATEWAY,
            detail="메타데이터 추출에 실패했습니다.",
        ) from error

    return MetadataExtractResponse(**result)


@router.get("/catalog/check-name", response_model=NameCheckResponse)
async def check_product_name(
    product_name: str,
    session: sqlalchemy_async.AsyncSession = fastapi.Depends(
        database.get_database_session
    ),
) -> NameCheckResponse:
    """상품명과 정확히 일치하는 기존 SKU가 있는지 확인합니다.

    결과는 안내용이며 저장을 막지 않습니다.

    Args:
        product_name: 확인할 상품명입니다.
        session: 비동기 DB 세션입니다.

    Returns:
        일치 여부와 일치한 SKU 목록입니다.
    """
    matches = await sku_service.find_skus_by_product_name(session, product_name)
    return NameCheckResponse(
        exists=bool(matches),
        matched=[
            SkuSummary(
                sku_id=match.sku_id,
                sku_code=match.sku_code,
                product_name=match.product_name,
            )
            for match in matches
        ],
    )


@router.get("/catalog/check-code", response_model=CodeCheckResponse)
async def check_sku_code(
    sku_code: str,
    session: sqlalchemy_async.AsyncSession = fastapi.Depends(
        database.get_database_session
    ),
) -> CodeCheckResponse:
    """SKU 코드와 정확히 일치하는 기존 SKU가 있는지 확인합니다.

    Args:
        sku_code: 확인할 SKU 코드입니다.
        session: 비동기 DB 세션입니다.

    Returns:
        SKU 코드와 존재 여부입니다.
    """
    existing = await sku_service.find_sku_by_code(session, sku_code)
    return CodeCheckResponse(sku_code=sku_code, exists=existing is not None)


@router.get("/catalog", response_model=SkuCatalogListResponse)
async def list_sku_catalog(
    limit: int = 50,
    session: sqlalchemy_async.AsyncSession = fastapi.Depends(
        database.get_database_session
    ),
) -> SkuCatalogListResponse:
    """등록된 전체 SKU 목록을 최신순으로 조회합니다.

    신규 SKU 등록이 실제로 저장됐는지 확인하는 용도입니다.

    Args:
        limit: 최대 반환 건수입니다 (기본 50).
        session: 비동기 DB 세션입니다.

    Returns:
        대표 이미지 경로를 포함한 SKU 목록입니다.
    """
    rows = await sku_service.list_skus(session, limit=limit)
    return SkuCatalogListResponse(
        items=[
            SkuCatalogItem(
                sku_id=sku.sku_id,
                sku_code=sku.sku_code,
                product_name=sku.product_name,
                brand=sku.brand,
                price=sku.price,
                space=sku.space,
                category=sku.category,
                sub_category=sku.sub_category,
                attributes=sku.attributes,
                main_image_url=image_url,
                created_at=sku.created_at,
            )
            for sku, image_url in rows
        ]
    )


@router.post(
    "",
    response_model=SkuCreateResponse,
    status_code=fastapi.status.HTTP_201_CREATED,
)
async def create_sku(
    # pylint: disable=too-many-arguments,too-many-positional-arguments
    sku_code: str = fastapi.Form(...),
    product_name: str = fastapi.Form(...),
    brand: typing.Optional[str] = fastapi.Form(None),
    price: typing.Optional[int] = fastapi.Form(None),
    space: typing.Optional[str] = fastapi.Form(None),
    category: typing.Optional[str] = fastapi.Form(None),
    sub_category: typing.Optional[str] = fastapi.Form(None),
    attributes: typing.Optional[str] = fastapi.Form(None),
    image: fastapi.UploadFile = fastapi.File(...),
    session: sqlalchemy_async.AsyncSession = fastapi.Depends(
        database.get_database_session
    ),
) -> SkuCreateResponse:
    """신규 SKU와 대표 이미지를 저장합니다.

    SKU 코드가 이미 존재하면 저장을 차단합니다.

    Args:
        sku_code: 신규 SKU 코드입니다.
        product_name: 상품명입니다.
        brand: 브랜드입니다 (선택, 수동 입력 전용).
        price: 가격입니다 (선택, 수동 입력 전용).
        space: 사용 공간입니다 (선택).
        category: 대분류입니다 (선택).
        sub_category: 소분류입니다 (선택).
        attributes: 색상·소재 등을 담은 JSON 문자열입니다 (선택).
        image: 대표 이미지입니다.
        session: 비동기 DB 세션입니다.

    Returns:
        생성된 SKU의 식별자와 대표 이미지 경로입니다.

    Raises:
        fastapi.HTTPException: 이미지가 유효하지 않은 경우(422), SKU
            코드가 중복인 경우(409), attributes가 JSON이 아닌
            경우(400)입니다.
    """
    content = await image.read()
    _validate_image(content, image.content_type)

    if await sku_service.find_sku_by_code(session, sku_code) is not None:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_409_CONFLICT,
            detail="이미 등록된 SKU 코드입니다.",
        )

    try:
        parsed_attributes = json.loads(attributes) if attributes else {}
    except json.JSONDecodeError as error:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_400_BAD_REQUEST,
            detail="attributes는 올바른 JSON 형식이어야 합니다.",
        ) from error

    image_url = sku_service.save_uploaded_image(
        sku_code, image.filename or "image.jpg", content
    )

    try:
        sku = await sku_service.create_sku(
            session,
            sku_code=sku_code,
            product_name=product_name,
            brand=brand,
            price=price,
            space=space,
            category=category,
            sub_category=sub_category,
            attributes=parsed_attributes,
            image_url=image_url,
        )
    except sku_service.SkuCodeDuplicateError as error:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_409_CONFLICT,
            detail="이미 등록된 SKU 코드입니다.",
        ) from error

    return SkuCreateResponse(
        sku_id=sku.sku_id,
        sku_code=sku.sku_code,
        product_name=sku.product_name,
        main_image_url=image_url,
    )
