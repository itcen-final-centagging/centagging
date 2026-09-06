"""SKU 카탈로그의 텍스트 임베딩 기반 유사도 검색 기능을 제공합니다."""

import collections.abc
import dataclasses
import logging
import typing

import pgvector.sqlalchemy as pgvector_sa  # type: ignore[import-untyped]
import sqlalchemy
from sqlalchemy import orm
from sqlalchemy.ext import asyncio as sqlalchemy_async

from app.models.sku import SkuCatalog, SkuImage
from app.schemas import sku_search as sku_search_schema
from app.services import sku_text_embedding
from app.services.gemini_service import GeminiConfigurationError, GeminiService
from app.services.sku_image_storage import SkuImageStorage

EMBEDDING_DIMENSIONS = 3072
DEFAULT_RESULT_LIMIT = 5
# LLM 재정렬 대상 후보 풀 크기입니다. attribute_reranking/llm_semantic_
# reranking 실험(search_eval_v2)에서 검증한 Top-30 후보 풀과 동일한
# 크기를 그대로 사용합니다 — 코사인 유사도만으로는 놓치는 케이스를
# 재정렬 단계에서 건져올 여지를 주기 위함입니다.
CANDIDATE_POOL_SIZE = 30
# 화면에 보여줄 스타일 태그의 최소 개수입니다. 실제 연출 이미지 태그가
# 이 개수에 못 미칠 때만 scripts.seed.seed_demo_vlm_moods로 채운 데모
# 태그를 뒤에 채워 넣습니다(app.services.sku_text_embedding.
# prioritize_display_moods 참고).
MIN_DISPLAY_STYLE_TAG_COUNT = 5
_HALFVEC = pgvector_sa.HALFVEC(EMBEDDING_DIMENSIONS)

_LOGGER = logging.getLogger(__name__)

# 검색 결과에 공간 분위기·스타일 태그를 얹기 위한 배치 조회입니다.
# app.services.approval_service._reindex_sku_text_embedding과 같은
# 대상(승인된 tagging_result.vlm_mood)을 다시 모으되, sku_catalog에는
# 별도 컬럼을 두지 않고 매 검색마다 다시 읽습니다.
#
# is_seed는 scripts.seed.seed_demo_vlm_moods가 만든 가짜 연출 이미지를
# 가려내기 위한 표시입니다. 그 스크립트는 scene_image.image_url을 항상
# '/uploads/seed/vlm-mood-seed-{sku_id}.jpg' 형태로 만들므로(실제 업로드
# 이미지는 이 경로를 쓰지 않습니다), 별도 DB 컬럼 없이 이 경로 패턴만
# 보고 실제 연출 이미지와 데모 시드를 구분합니다.
_SELECT_ACTIVE_VLM_MOODS_BY_SKU_IDS = sqlalchemy.text("""
    SELECT tr.sku_id, tr.vlm_mood,
           (si.image_url LIKE '/uploads/seed/%') AS is_seed
      FROM tagging_result tr
      JOIN approval a ON a.tagging_result_id = tr.result_id
      JOIN scene_image si ON si.scene_image_id = tr.scene_image_id
     WHERE tr.sku_id IN :sku_ids
       AND a.status = 'ACTIVE'
       AND tr.vlm_mood IS NOT NULL
    """).bindparams(sqlalchemy.bindparam("sku_ids", expanding=True))


class SkuSearchQueryError(RuntimeError):
    """검색어 임베딩 또는 조회 중 발생한 오류입니다."""


def _to_public_url(
    sku_image_storage: SkuImageStorage, stored_path: str | None
) -> str | None:
    """DB 저장 경로가 있으면 공개 URL로 바꾸고, 없으면 None을 반환합니다."""
    if not stored_path:
        return None
    return sku_image_storage.public_url(stored_path)


async def _fetch_active_moods_by_sku_ids(
    session: sqlalchemy_async.AsyncSession,
    sku_ids: collections.abc.Iterable[int],
) -> dict[int, tuple[list[str], list[str]]]:
    """SKU별 승인된 공간 분위기 요약·스타일 태그를 배치로 모읍니다.

    승인 최종 트리거(app.services.approval_service의
    _reindex_sku_text_embedding)와 같은 대상을 다시 모으되, 화면 표시용
    으로는 실제 연출 이미지에서 얻은 값을 우선하고 데모 시드
    (scripts.seed.seed_demo_vlm_moods)로 채운 값은 실제 태그가
    MIN_DISPLAY_STYLE_TAG_COUNT에 못 미칠 때만 채워 넣습니다
    (app.services.sku_text_embedding.prioritize_display_moods 참고). 이
    조회가 실패해도 검색 자체를 막으면 안 되므로 예외를 삼키고 빈
    결과로 대체합니다.

    Args:
        session: 비동기 SQLAlchemy 세션입니다.
        sku_ids: 조회할 sku_id 목록입니다.

    Returns:
        sku_id -> (공간 분위기 요약 목록, 스타일 태그 목록)입니다. 승인된
        태깅 결과가 없는 SKU는 키 자체가 없습니다.
    """
    unique_sku_ids = sorted({int(sku_id) for sku_id in sku_ids})
    if not unique_sku_ids:
        return {}

    try:
        result = await session.execute(
            _SELECT_ACTIVE_VLM_MOODS_BY_SKU_IDS,
            {"sku_ids": unique_sku_ids},
        )
        real_moods_by_sku_id: dict[int, list[typing.Any]] = {}
        seed_moods_by_sku_id: dict[int, list[typing.Any]] = {}
        for sku_id, vlm_mood, is_seed in result.all():
            bucket = (
                seed_moods_by_sku_id if is_seed else real_moods_by_sku_id
            )
            bucket.setdefault(int(sku_id), []).append(vlm_mood)
    except Exception:  # noqa: BLE001 - 조회 실패가 검색을 막으면 안 됨
        _LOGGER.warning(
            "공간 분위기·스타일 태그 조회 실패 - 빈 값으로 대체합니다.",
            exc_info=True,
        )
        return {}

    all_sku_ids = set(real_moods_by_sku_id) | set(seed_moods_by_sku_id)
    moods_by_sku_id: dict[int, tuple[list[str], list[str]]] = {
        sku_id: sku_text_embedding.prioritize_display_moods(
            real_moods_by_sku_id.get(sku_id, []),
            seed_moods_by_sku_id.get(sku_id, []),
            min_tag_count=MIN_DISPLAY_STYLE_TAG_COUNT,
        )
        for sku_id in all_sku_ids
    }
    return moods_by_sku_id


def _to_rerank_candidate(
    row: collections.abc.Mapping[str, typing.Any],
) -> dict[str, typing.Any]:
    """재정렬 프롬프트에 넘길 catalog 필드만 뽑아냅니다.

    정답 SKU나 평가용 라벨은 애초에 이 함수의 입력(row)에 존재하지
    않습니다 — search_skus의 SELECT 절이 catalog 필드만 조회하기
    때문입니다.

    Args:
        row: SQL 조회 결과 한 행입니다.

    Returns:
        sku_code와 catalog 필드만 담은 딕셔너리입니다.
    """
    return {
        "sku_code": row["sku_code"],
        "product_name": row["product_name"],
        "category": row["category"],
        "sub_category": row["sub_category"],
        "attributes": row.get("attributes") or {},
        "brand": row["brand"],
        "price": row["price"],
    }


def _reorder_by_ranked_codes(
    items: list[sku_search_schema.SkuSearchItem],
    ranked_codes: list[str],
) -> list[sku_search_schema.SkuSearchItem]:
    """LLM이 반환한 sku_code 순서대로 items를 재배열합니다.

    LLM이 일부만 반환했거나 목록에 없는 코드를 냈다면, 남은 자리는
    원래(코사인 유사도) 순서로 채웁니다 — 재정렬이 부분적으로만
    성공해도 후보를 잃지 않도록 하기 위함입니다.

    Args:
        items: 코사인 유사도 순서의 원본 결과 목록입니다.
        ranked_codes: Gemini가 반환한 재정렬된 sku_code 목록입니다.

    Returns:
        재정렬된 SkuSearchItem 목록이며, 길이는 items와 같습니다.
    """
    by_code = {item.sku_code: item for item in items}
    ordered: list[sku_search_schema.SkuSearchItem] = []
    seen: set[str] = set()

    for code in ranked_codes:
        item = by_code.get(code)
        if item is not None and code not in seen:
            ordered.append(item)
            seen.add(code)

    for item in items:
        if item.sku_code not in seen:
            ordered.append(item)
            seen.add(item.sku_code)

    return ordered


def _rerank_items(
    gemini_service: GeminiService,
    query: str,
    items: list[sku_search_schema.SkuSearchItem],
    rows: collections.abc.Sequence[collections.abc.Mapping[str, typing.Any]],
    limit: int,
) -> list[sku_search_schema.SkuSearchItem]:
    """LLM으로 후보 풀을 재정렬합니다. 실패하면 원래 순서로 폴백합니다.

    재정렬은 검색 품질을 높이는 부가 단계이므로, 재정렬 자체가
    실패(인증 미설정, API 오류, 응답 파싱 실패 등)해도 검색 결과 자체를
    막아서는 안 됩니다. 실패 시 코사인 유사도 순서를 그대로 사용합니다.

    Args:
        gemini_service: 재정렬 호출에 사용하는 서비스입니다.
        query: 검색 프롬프트입니다.
        items: 코사인 유사도 순서의 후보 SkuSearchItem 목록입니다
            (최대 CANDIDATE_POOL_SIZE개).
        rows: items와 같은 순서의 원본 SQL 조회 결과입니다. 재정렬
            프롬프트에 필요한 attributes 등 catalog 필드를 담고
            있습니다.
        limit: 최종적으로 반환할 결과 개수입니다.

    Returns:
        재정렬 후 limit개로 자른 SkuSearchItem 목록입니다.
    """
    try:
        candidates = [_to_rerank_candidate(row) for row in rows]
        ranked_codes = gemini_service.rerank_sku_candidates(
            query, candidates, top_k=limit
        )
        reordered = _reorder_by_ranked_codes(items, ranked_codes)
    except Exception:  # noqa: BLE001 - 재정렬 실패가 검색을 막으면 안 됨
        _LOGGER.warning(
            "SKU 재정렬 실패 - 코사인 유사도 순서로 대체합니다.",
            exc_info=True,
        )
        reordered = items

    return reordered[:limit]


async def search_skus(
    session: sqlalchemy_async.AsyncSession,
    gemini_service: GeminiService,
    sku_image_storage: SkuImageStorage,
    query: str,
    limit: int = DEFAULT_RESULT_LIMIT,
) -> sku_search_schema.SkuSearchData:
    """검색어와 의미적으로 유사한 SKU를 조회합니다.

    1차로 코사인 유사도 상위 CANDIDATE_POOL_SIZE개를 후보 풀로 뽑고,
    Gemini로 검색어 조건에 맞게 재정렬한 뒤 상위 limit개를 반환합니다.
    재정렬이 실패하면 코사인 유사도 순서를 그대로 사용합니다. 각 결과에는
    승인(ACTIVE)된 tagging_result.vlm_mood를 다시 모은 공간 분위기·스타일
    태그도 함께 담기며, 이 조회가 실패해도 검색 결과 자체는 반환합니다.

    Args:
        session: 비동기 SQLAlchemy 세션입니다.
        gemini_service: 검색어 임베딩과 후보 재정렬에 사용하는
            서비스입니다.
        sku_image_storage: 대표 이미지 경로를 공개 URL로 바꾸는 저장소입니다.
        query: 검색 프롬프트입니다.
        limit: 반환할 최대 SKU 개수입니다 (기본 5건).

    Returns:
        검색어 관련도 순으로 정렬된 SKU 검색 결과입니다.

    Raises:
        GeminiConfigurationError: Gemini 설정 오류
        SkuSearchQueryError: 검색어 임베딩에 실패했거나 응답 차원이
            올바르지 않은 경우입니다.
    """
    try:
        embedding = gemini_service.embed_text(query)
    except GeminiConfigurationError:
        raise
    except Exception as error:
        raise SkuSearchQueryError("검색어 임베딩에 실패했습니다.") from error

    if len(embedding) != EMBEDDING_DIMENSIONS:
        raise SkuSearchQueryError(
            f"임베딩 벡터 차원은 {EMBEDDING_DIMENSIONS} 차원이어야 "
            f"합니다. 현재 {len(embedding)} 차원입니다."
        )

    query_vector = sqlalchemy.cast(list(embedding), _HALFVEC)
    distance = (
        sqlalchemy.cast(SkuCatalog.text_embedding, _HALFVEC)
        .cosine_distance(query_vector)
        .label("distance")
    )

    pool_size = max(limit, CANDIDATE_POOL_SIZE)
    main_image = orm.aliased(SkuImage, name="main_image")
    stmt = (
        sqlalchemy.select(
            SkuCatalog.sku_id,
            SkuCatalog.sku_code,
            SkuCatalog.product_name,
            SkuCatalog.category,
            SkuCatalog.sub_category,
            SkuCatalog.brand,
            SkuCatalog.price,
            SkuCatalog.attributes,
            main_image.image_url,
            (1 - distance).label("similarity"),
        )
        .where(SkuCatalog.text_embedding.is_not(None))
        .outerjoin(
            main_image,
            sqlalchemy.and_(
                main_image.sku_id == SkuCatalog.sku_id,
                main_image.image_type == "MAIN",
            ),
        )
        .order_by(distance)
        .limit(pool_size)
    )

    rows = (await session.execute(stmt)).mappings().all()

    moods_by_sku_id = await _fetch_active_moods_by_sku_ids(
        session, (row["sku_id"] for row in rows)
    )

    items = [
        sku_search_schema.SkuSearchItem(
            sku_code=row["sku_code"],
            product_name=row["product_name"],
            category=row["category"],
            sub_category=row["sub_category"],
            image_url=_to_public_url(sku_image_storage, row["image_url"]),
            brand=row["brand"],
            price=row["price"],
            similarity_score=round(
                max(0.0, min(100.0, row["similarity"] * 100)), 1
            ),
            space_moods=moods_by_sku_id.get(row["sku_id"], ([], []))[0],
            style_tags=moods_by_sku_id.get(row["sku_id"], ([], []))[1],
        )
        for row in rows
    ]

    ranked_items = _rerank_items(gemini_service, query, items, rows, limit)

    return sku_search_schema.SkuSearchData(skus=ranked_items)


async def get_sku_detail(
    session: sqlalchemy_async.AsyncSession,
    sku_image_storage: SkuImageStorage,
    sku_code: str,
) -> sku_search_schema.SkuDetailData | None:
    """SKU 코드로 카테고리별 속성을 포함한 상세 정보를 조회합니다.

    Args:
        session: 비동기 SQLAlchemy 세션입니다.
        sku_image_storage: 대표 이미지 경로를 공개 URL로 바꾸는 저장소입니다.
        sku_code: 조회할 SKU 코드입니다.

    Returns:
        SKU 상세 정보이며, 존재하지 않으면 None입니다. 승인(ACTIVE)된
        tagging_result.vlm_mood를 다시 모은 공간 분위기·스타일 태그도
        함께 담깁니다.
    """
    main_image = orm.aliased(SkuImage, name="main_image")
    stmt = (
        sqlalchemy.select(
            SkuCatalog.sku_id,
            SkuCatalog.sku_code,
            SkuCatalog.product_name,
            SkuCatalog.brand,
            SkuCatalog.price,
            SkuCatalog.category,
            SkuCatalog.sub_category,
            SkuCatalog.attributes,
            main_image.image_url,
            main_image.sku_image_id,
        )
        .outerjoin(
            main_image,
            sqlalchemy.and_(
                main_image.sku_id == SkuCatalog.sku_id,
                main_image.image_type == "MAIN",
            ),
        )
        .where(SkuCatalog.sku_code == sku_code)
    )
    row = (await session.execute(stmt)).mappings().first()
    if row is None:
        return None

    moods_by_sku_id = await _fetch_active_moods_by_sku_ids(
        session, [row["sku_id"]]
    )
    space_moods, style_tags = moods_by_sku_id.get(row["sku_id"], ([], []))

    return sku_search_schema.SkuDetailData(
        sku_id=row["sku_id"],
        sku_code=row["sku_code"],
        product_name=row["product_name"],
        brand=row["brand"],
        price=row["price"],
        category=row["category"],
        sub_category=row["sub_category"],
        attrs=row["attributes"] or {},
        image_url=_to_public_url(sku_image_storage, row["image_url"]),
        sku_image_id=row["sku_image_id"],
        space_moods=space_moods,
        style_tags=style_tags,
    )


@dataclasses.dataclass(frozen=True)
class SkuImageForScoring:
    """VLM 채점에 쓸 SKU 대표 이미지의 원본 저장 경로입니다.

    ``get_sku_detail``과 달리 image_url을 공개 URL로 바꾸지 않고 DB에
    저장된 경로 그대로 담습니다. ``read_sku_image_bytes``가 이 원본
    경로를 기준으로 파일을 읽기 때문입니다.
    """

    sku_id: int
    sku_image_id: int
    image_url: str


async def get_sku_image_for_scoring(
    session: sqlalchemy_async.AsyncSession,
    sku_code: str,
) -> SkuImageForScoring | None:
    """VLM 채점에 필요한 SKU 대표(MAIN) 이미지의 저장 경로를 조회합니다.

    전체 카탈로그 검색으로 선택한 SKU도 AI 추천 후보와 동일한 XAI
    채점(``XaiScoringService``)을 거칠 수 있도록, 그 입력으로 쓸 원본
    이미지 경로만 가볍게 조회합니다.

    Args:
        session: 비동기 SQLAlchemy 세션입니다.
        sku_code: 조회할 SKU 코드입니다.

    Returns:
        MAIN 이미지 정보이며, SKU나 대표 이미지가 없으면 None입니다.
    """
    main_image = orm.aliased(SkuImage, name="main_image")
    stmt = (
        sqlalchemy.select(
            SkuCatalog.sku_id,
            main_image.sku_image_id,
            main_image.image_url,
        )
        .join(
            main_image,
            sqlalchemy.and_(
                main_image.sku_id == SkuCatalog.sku_id,
                main_image.image_type == "MAIN",
            ),
        )
        .where(SkuCatalog.sku_code == sku_code)
    )
    row = (await session.execute(stmt)).mappings().first()
    if row is None:
        return None

    return SkuImageForScoring(
        sku_id=row["sku_id"],
        sku_image_id=row["sku_image_id"],
        image_url=row["image_url"],
    )
