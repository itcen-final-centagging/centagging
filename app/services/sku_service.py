"""신규 SKU 등록에 필요한 AI 추출·DB·스토리지 로직입니다."""

import collections.abc
import pathlib
import typing
import uuid

import sqlalchemy
from sqlalchemy import orm
from sqlalchemy.ext import asyncio as sqlalchemy_async

from app.core import catalog_spec, config, genai_client
from app.models import sku as sku_models
from app.schemas import sku as sku_schema
from app.schemas.gemini_detection import GeminiRawDetection
from app.services import image_processing_service
from app.services.gemini_service import GeminiService

_UPLOAD_SUBDIR = "sku"
_ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png"}
_MAX_IMAGE_SIZE = 10 * 1024 * 1024


class SkuConfigurationError(RuntimeError):
    """Google Gen AI 인증 설정이 누락된 경우 발생합니다."""


class SkuExtractionError(RuntimeError):
    """AI 메타데이터 추출이 실패한 경우 발생합니다."""


class SkuCodeDuplicateError(RuntimeError):
    """저장 시점에 SKU 코드가 이미 존재하는 경우 발생합니다."""


class SkuImageValidationError(ValueError):
    """업로드 이미지가 형식·용량 조건을 충족하지 못한 경우 발생합니다."""


class SkuFilterValidationError(ValueError):
    """카탈로그 목록 필터 값이나 조합이 유효하지 않은 경우 발생합니다."""


def validate_image_upload(
    content: bytes, content_type: typing.Optional[str]
) -> None:
    """업로드 이미지의 형식과 용량을 검증합니다.

    Args:
        content: 업로드된 이미지의 원본 바이트입니다.
        content_type: 업로드 요청의 MIME 타입입니다.

    Raises:
        SkuImageValidationError: 형식이 다르거나 10MB를 초과한 경우입니다.
    """
    if content_type not in _ALLOWED_IMAGE_MIME_TYPES:
        raise SkuImageValidationError("JPG, PNG 파일만 업로드 가능합니다.")
    if len(content) > _MAX_IMAGE_SIZE:
        raise SkuImageValidationError("파일 용량은 최대 10MB까지 가능합니다.")


class ExtractedMetadata(typing.TypedDict):
    """AI가 추출한 SKU 메타데이터입니다."""

    category: typing.Optional[str]
    sub_category: typing.Optional[str]
    attributes: dict[str, typing.Any]


def _select_primary_category(
    detections: list[GeminiRawDetection],
) -> typing.Optional[str]:
    """탐지된 가구 중 신뢰도가 가장 높은 category를 대표값으로 고릅니다.

    SKU 등록 이미지는 상품 1개만 담긴 것을 전제하므로, 여러 개가
    탐지되더라도 가장 확신도가 높은 detection만 대표로 씁니다.

    Args:
        detections: :meth:`GeminiService.detect_furniture`가 반환한
            탐지 목록입니다.

    Returns:
        대표 category이며, 탐지된 가구가 없으면 None입니다.
    """
    if not detections:
        return None
    best = max(detections, key=lambda detection: detection.confidence or 0.0)
    return best.category


def extract_metadata(
    settings: config.Settings, image_bytes: bytes
) -> ExtractedMetadata:
    """이미지에서 카테고리·하위카테고리·속성을 추출합니다.

    :meth:`GeminiService.detect_furniture`로 대표 category를 먼저 정한
    뒤(1차 호출), 그 category로 :meth:`GeminiService.extract_furniture_attributes`
    를 호출해 :mod:`app.core.catalog_spec` 허용값에 맞는 sub_category와
    attributes를 채웁니다(2차 호출). 가구가 하나도 탐지되지 않으면 2차
    호출 없이 category 이후 값을 모두 비워 둡니다.

    Args:
        settings: Google Gen AI 인증과 모델명이 담긴 설정입니다.
        image_bytes: 분석할 이미지의 원본 바이트입니다.

    Returns:
        추출된 category, sub_category, attributes입니다.

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
        image = image_processing_service.decode_image(image_bytes)
        gemini_service = GeminiService(settings)

        detection_result = gemini_service.detect_furniture(image)
        category = _select_primary_category(detection_result.detections)

        sub_category: typing.Optional[str] = None
        attributes: dict[str, typing.Any] = {}
        if category is not None:
            attribute_result = gemini_service.extract_furniture_attributes(
                image, category
            )
            sub_category = attribute_result.sub_category
            attributes = attribute_result.attributes
    except (
        Exception
    ) as error:  # External SDK boundary; re-raise a domain error.
        raise SkuExtractionError(
            "Gemini metadata extraction failed."
        ) from error

    return {
        "category": category,
        "sub_category": sub_category,
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


_COLOR_OPTIONS: list[str] = list(catalog_spec.COMMON_ATTRIBUTE["color"] or [])
_STYLE_OPTIONS: list[str] = list(catalog_spec.COMMON_ATTRIBUTE["style"] or [])
_PATTERN_OPTIONS: list[str] = list(
    catalog_spec.COMMON_ATTRIBUTE["pattern"] or []
)

_MIN_SEARCH_QUERY_LENGTH = 2


def _validate_catalog_filters(filters: sku_schema.SkuCatalogFilters) -> None:
    """카탈로그 목록 필터 값이 catalog_spec 기준에 맞는지 검증합니다.

    Args:
        filters: 검증할 대분류/소분류/색상/스타일 필터입니다.
            sub_category는 category 없이는 지정할 수 없습니다
            (드롭다운에서 대분류를 먼저 골라야 하는 것과 같은 규칙을
            서버에서도 강제합니다).

    Raises:
        SkuFilterValidationError: 필터 값이나 조합이 유효하지 않은
            경우입니다.
    """
    if (
        filters.category is not None
        and filters.category not in catalog_spec.CATEGORIES
    ):
        raise SkuFilterValidationError(
            f"정의되지 않은 대분류입니다: {filters.category}"
        )

    if filters.sub_category is not None:
        if filters.category is None:
            raise SkuFilterValidationError(
                "소분류를 선택하려면 대분류를 먼저 선택해야 합니다."
            )
        if (
            filters.sub_category
            not in catalog_spec.PRODUCT_CATEGORY[filters.category]
        ):
            raise SkuFilterValidationError(
                f"'{filters.category}'에 없는 소분류입니다: "
                f"{filters.sub_category}"
            )

    if filters.color is not None and filters.color not in _COLOR_OPTIONS:
        raise SkuFilterValidationError(
            f"정의되지 않은 색상입니다: {filters.color}"
        )

    if filters.style is not None and filters.style not in _STYLE_OPTIONS:
        raise SkuFilterValidationError(
            f"정의되지 않은 스타일입니다: {filters.style}"
        )

    if filters.pattern is not None and filters.pattern not in _PATTERN_OPTIONS:
        raise SkuFilterValidationError(
            f"정의되지 않은 패턴입니다: {filters.pattern}"
        )

    if (
        filters.q is not None
        and filters.q.strip()
        and len(filters.q.strip()) < _MIN_SEARCH_QUERY_LENGTH
    ):
        raise SkuFilterValidationError(
            f"검색어는 {_MIN_SEARCH_QUERY_LENGTH}자 이상 입력해주세요."
        )


async def list_skus(
    session: sqlalchemy_async.AsyncSession,
    filters: typing.Optional[sku_schema.SkuCatalogFilters] = None,
) -> collections.abc.Sequence[typing.Any]:
    """등록된 SKU를 최신순으로 대표 이미지와 함께 조회합니다.

    Args:
        session: 비동기 DB 세션입니다.
        filters: 대분류/소분류/색상/스타일/검색어 필터입니다. 지정하지
            않으면 전체 목록을 반환합니다.

    Returns:
        ``(SkuCatalog, main_image_url)`` 튜플의 목록입니다. 대표
        이미지가 없으면 ``main_image_url``은 None입니다. SKU 한 건이
        ``MAIN`` 이미지를 여러 장 갖고 있어도 SKU당 정확히 한 행만
        반환합니다.

    Raises:
        SkuFilterValidationError: 필터 값이나 조합이 유효하지 않은
            경우입니다.
    """
    filters = filters or sku_schema.SkuCatalogFilters()
    _validate_catalog_filters(filters)

    deduped = (
        sqlalchemy.select(sku_models.SkuCatalog, sku_models.SkuImage.image_url)
        .distinct(sku_models.SkuCatalog.sku_id)
        .outerjoin(
            sku_models.SkuImage,
            sqlalchemy.and_(
                sku_models.SkuImage.sku_id == sku_models.SkuCatalog.sku_id,
                sku_models.SkuImage.image_type == "MAIN",
            ),
        )
    )
    if filters.category is not None:
        deduped = deduped.where(
            sku_models.SkuCatalog.category == filters.category
        )
    if filters.sub_category is not None:
        deduped = deduped.where(
            sku_models.SkuCatalog.sub_category == filters.sub_category
        )
    if filters.color is not None:
        deduped = deduped.where(
            sku_models.SkuCatalog.attributes["color"].astext == filters.color
        )
    if filters.style is not None:
        deduped = deduped.where(
            sku_models.SkuCatalog.attributes["style"].astext == filters.style
        )
    if filters.pattern is not None:
        deduped = deduped.where(
            sku_models.SkuCatalog.attributes["pattern"].astext
            == filters.pattern
        )
    if filters.q is not None and filters.q.strip():
        keyword = filters.q.strip()
        deduped = deduped.where(
            sqlalchemy.or_(
                sku_models.SkuCatalog.sku_code == keyword,
                sqlalchemy.func.lower(sku_models.SkuCatalog.product_name).like(
                    f"%{keyword.lower()}%"
                ),
            )
        )
    deduped = deduped.order_by(
        sku_models.SkuCatalog.sku_id,
        sku_models.SkuImage.sku_image_id,
    )

    subquery = deduped.subquery()
    sku_alias = orm.aliased(sku_models.SkuCatalog, subquery)
    stmt = sqlalchemy.select(sku_alias, subquery.c.image_url).order_by(
        subquery.c.created_at.desc()
    )
    result = await session.execute(stmt)
    return result.all()


class CatalogFilterOptions(typing.TypedDict):
    """카탈로그 목록 필터 드롭다운에 쓰이는 선택지입니다."""

    categories: list[str]
    sub_categories_by_category: dict[str, list[str]]
    colors: list[str]
    styles: list[str]
    pattern: list[str]


def get_catalog_filter_options() -> CatalogFilterOptions:
    """카탈로그 목록 필터 드롭다운의 선택지를 반환합니다.

    DB 접근 없이 ``catalog_spec`` 정의를 그대로 반환하는 순수 조회다.
    소분류는 대분류별로 묶어서 반환하므로, 프런트는 대분류 선택 후
    그 값으로 소분류 드롭다운 내용만 바꿔 끼우면 된다.

    Returns:
        대분류 목록, 대분류별 소분류 목록, 색상·스타일·패턴 허용값입니다.
    """
    return {
        "categories": catalog_spec.CATEGORIES,
        "sub_categories_by_category": catalog_spec.PRODUCT_CATEGORY,
        "colors": _COLOR_OPTIONS,
        "styles": _STYLE_OPTIONS,
        "pattern": _PATTERN_OPTIONS,
    }
