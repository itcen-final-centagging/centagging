"""신규 SKU 등록 API입니다. / New SKU registration API."""

import json
import typing

import fastapi
from sqlalchemy.ext import asyncio as sqlalchemy_async

from app import dependencies
from app.core import config, database
from app.core.error_codes import ErrorCode
from app.schemas import common as common_schema
from app.schemas import sku as sku_schema
from app.services import sku_service
from app.services.gemini_service import (
    GeminiConfigurationError,
    GeminiEmbeddingError,
    GeminiService,
)
from app.services.sku_image_storage import SkuImageStorage

router = fastapi.APIRouter(prefix="/sku", tags=["sku"])

_MAX_BATCH_IMAGE_COUNT = 20


def _validate_image(content: bytes, content_type: typing.Optional[str]) -> None:
    """업로드 이미지를 검증하고 실패 시 HTTP 오류로 변환합니다.

    Args:
        content: 업로드된 이미지의 원본 바이트입니다.
        content_type: 업로드 요청의 MIME 타입입니다.

    Raises:
        fastapi.HTTPException: 형식이 다르거나 10MB를 초과한 경우입니다(422).
    """
    try:
        sku_service.validate_image_upload(content, content_type)
    except sku_service.SkuImageValidationError as error:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error


# NOTE: 기존 SKU 라우터 확장부에 공통 관리자 권한·응답 규약을 적용합니다.
@router.post(
    "/{sku_code}/images",
    response_model=common_schema.SuccessResponse[
        sku_schema.SkuImageBatchCreateResponse
    ],
    status_code=fastapi.status.HTTP_201_CREATED,
)
async def add_images_to_existing_sku(
    sku_code: str,
    images: list[fastapi.UploadFile] = fastapi.File(...),
    image_type: sku_schema.SkuImageType = fastapi.Form("STYLING"),
    _: dependencies.AdminUser = fastapi.Depends(
        dependencies.require_super_admin
    ),
    session: sqlalchemy_async.AsyncSession = fastapi.Depends(
        database.get_database_session
    ),
) -> common_schema.SuccessResponse[sku_schema.SkuImageBatchCreateResponse]:
    """기존 SKU에 제품 이미지를 한 번에 추가합니다.

    관리자 일괄 등록 화면은 여러 파일을 업로드하되 하나의 큐 항목은
    동일한 이미지 유형으로 저장합니다. 예를 들어 여러 연출 이미지를
    ``STYLING``으로, 여러 상세 컷을 ``DETAIL``로 묶어 추가합니다.

    Args:
        sku_code: 이미지를 연결할 기존 SKU 코드입니다.
        images: JPG 또는 PNG 파일 1~20개입니다.
        image_type: 모든 파일에 적용할 이미지 유형입니다.
        session: 요청 범위 DB 세션입니다.

    Returns:
        새로 만든 ``sku_image`` 목록입니다.

    Raises:
        fastapi.HTTPException: SKU가 없거나, 파일 수·형식·용량이
            허용 범위를 벗어난 경우입니다.
    """
    if not images:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="이미지를 한 장 이상 업로드해야 합니다.",
        )
    if len(images) > _MAX_BATCH_IMAGE_COUNT:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"이미지는 한 번에 최대 {_MAX_BATCH_IMAGE_COUNT}장까지 가능합니다.",
        )

    sku = await sku_service.find_sku_by_code(session, sku_code)
    if sku is None:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_404_NOT_FOUND,
            detail="기존 SKU를 찾을 수 없습니다.",
        )

    image_urls = []
    for image in images:
        content = await image.read()
        _validate_image(content, image.content_type)
        image_urls.append(
            sku_service.save_uploaded_image(
                config.get_settings(),
                sku.sku_code,
                image.filename or "image.jpg",
                content,
            )
        )

    created_images = await sku_service.add_sku_images(
        session,
        sku_id=sku.sku_id,
        image_urls=image_urls,
        image_type=image_type,
    )
    return common_schema.success_response(
        sku_schema.SkuImageBatchCreateResponse(
            sku_id=sku.sku_id,
            sku_code=sku.sku_code,
            images=[
                sku_schema.SkuImageUploadItem(
                    sku_image_id=image.sku_image_id,
                    image_url=image.image_url,
                    image_type=typing.cast(
                        sku_schema.SkuImageType, image.image_type
                    ),
                )
                for image in created_images
            ],
        )
    )


@router.post("/extract", response_model=sku_schema.MetadataExtractResponse)
async def extract_metadata(
    image: fastapi.UploadFile = fastapi.File(...),
) -> sku_schema.MetadataExtractResponse:
    """업로드 이미지를 분석해 SKU 메타데이터를 추출합니다.

    DB에 아무것도 저장하지 않는 상태 없는(stateless) 호출입니다.

    Args:
        image: 분석 대상 이미지입니다.

    Returns:
        추출된 category, sub_category, attributes입니다.

    Raises:
        fastapi.HTTPException: 이미지가 유효하지 않거나(422) AI 설정이
            없거나(503) 호출이 실패한 경우(502)입니다.
    """
    content = await image.read()
    _validate_image(content, image.content_type)

    settings = config.get_settings()
    try:
        result = sku_service.extract_metadata(settings, content)
    except sku_service.SkuConfigurationError as error:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Gen AI authentication is not configured.",
        ) from error
    except sku_service.SkuExtractionError as error:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_502_BAD_GATEWAY,
            detail="메타데이터 추출에 실패했습니다.",
        ) from error

    return sku_schema.MetadataExtractResponse(**result)


@router.get(
    "/catalog/filters",
    response_model=common_schema.SuccessResponse[
        sku_schema.SkuCatalogFilterOptions
    ],
)
async def get_sku_catalog_filters() -> (
    common_schema.SuccessResponse[sku_schema.SkuCatalogFilterOptions]
):
    """카탈로그 목록 화면의 필터 드롭다운 선택지를 반환합니다.

    DB 상태와 무관하게 catalog_spec 정의를 그대로 돌려주므로 세션이
    필요 없다.

    Returns:
        대분류, 대분류별 소분류, 색상, 스타일, 패턴 선택지입니다.
    """
    options = sku_service.get_catalog_filter_options()
    return common_schema.success_response(
        sku_schema.SkuCatalogFilterOptions(
            categories=options["categories"],
            sub_categories_by_category=options["sub_categories_by_category"],
            colors=options["colors"],
            styles=options["styles"],
            pattern=options["pattern"],
        )
    )


@router.get(
    "/catalog",
    response_model=common_schema.SuccessResponse[
        sku_schema.SkuCatalogListResponse
    ],
)
async def list_sku_catalog(
    filters: sku_schema.SkuCatalogFilters = fastapi.Depends(),
    session: sqlalchemy_async.AsyncSession = fastapi.Depends(
        database.get_database_session
    ),
    gemini_service: GeminiService = fastapi.Depends(
        dependencies.get_gemini_service
    ),
) -> common_schema.SuccessResponse[sku_schema.SkuCatalogListResponse]:
    """등록된 전체 SKU 목록을 최신순으로 조회합니다.

    신규 SKU 등록이 실제로 저장됐는지 확인하는 용도이자, 관리자
    카탈로그 화면의 목록·필터 조회에도 쓰인다. 검색어(q)가 있으면
    app.services.sku_search_service의 SKU 검색과 같은 방식으로 텍스트
    임베딩 코사인 유사도 순으로 정렬한다.

    Args:
        filters: 대분류/소분류/색상/스타일/검색어 쿼리 파라미터입니다.
            sub_category는 category 없이는 지정할 수 없습니다(먼저
            대분류를 선택해야 합니다).
        session: 비동기 DB 세션입니다.
        gemini_service: 검색어 텍스트 임베딩에 쓰는 서비스입니다.

    Returns:
        대표 이미지 경로를 포함한 SKU 목록입니다.

    Raises:
        fastapi.HTTPException: 필터 값이나 조합이 유효하지 않으면 422,
            검색어가 있는데 Gemini 인증이 설정되지 않았으면 503,
            검색어 임베딩이 실패하면 502를 반환합니다.
    """
    try:
        rows = await sku_service.list_skus(
            session, filters=filters, gemini_service=gemini_service
        )
    except sku_service.SkuFilterValidationError as error:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error
    except GeminiConfigurationError as error:
        raise fastapi.HTTPException(
            status_code=503,
            detail={
                "code": ErrorCode.SERVICE_UNAVAILABLE.value,
                "message": "검색 기능이 아직 설정되지 않았습니다.",
            },
        ) from error
    except GeminiEmbeddingError as error:
        raise fastapi.HTTPException(
            status_code=502,
            detail={
                "code": ErrorCode.UPSTREAM_ERROR.value,
                "message": "검색어 처리 중 오류가 발생했습니다.",
            },
        ) from error

    storage = SkuImageStorage(config.get_settings().sku_image_root)
    return common_schema.success_response(
        sku_schema.SkuCatalogListResponse(
            items=[
                sku_schema.SkuCatalogItem(
                    sku_id=sku.sku_id,
                    sku_code=sku.sku_code,
                    product_name=sku.product_name,
                    brand=sku.brand,
                    price=sku.price,
                    category=sku.category,
                    sub_category=sku.sub_category,
                    attributes=sku.attributes,
                    main_image_url=(
                        storage.public_url(image_url) if image_url else None
                    ),
                    created_at=sku.created_at,
                )
                for sku, image_url in rows
            ]
        )
    )


@router.post(
    "",
    response_model=sku_schema.SkuCreateResponse,
    status_code=fastapi.status.HTTP_201_CREATED,
)
async def create_sku(
    # pylint: disable=too-many-arguments,too-many-positional-arguments
    sku_code: str = fastapi.Form(...),
    product_name: str = fastapi.Form(...),
    brand: typing.Optional[str] = fastapi.Form(None),
    price: typing.Optional[int] = fastapi.Form(None),
    category: typing.Optional[str] = fastapi.Form(None),
    sub_category: typing.Optional[str] = fastapi.Form(None),
    attributes: typing.Optional[str] = fastapi.Form(None),
    image: fastapi.UploadFile = fastapi.File(...),
    session: sqlalchemy_async.AsyncSession = fastapi.Depends(
        database.get_database_session
    ),
) -> sku_schema.SkuCreateResponse:
    """신규 SKU와 대표 이미지를 저장합니다.

    SKU 코드가 이미 존재하면 저장을 차단합니다.

    Args:
        sku_code: 신규 SKU 코드입니다.
        product_name: 상품명입니다.
        brand: 브랜드입니다 (선택, 수동 입력 전용).
        price: 가격입니다 (선택, 수동 입력 전용).
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
        config.get_settings(), sku_code, image.filename or "image.jpg", content
    )

    try:
        sku = await sku_service.create_sku(
            session,
            sku_code=sku_code,
            product_name=product_name,
            brand=brand,
            price=price,
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

    return sku_schema.SkuCreateResponse(
        sku_id=sku.sku_id,
        sku_code=sku.sku_code,
        product_name=sku.product_name,
        main_image_url=image_url,
    )
