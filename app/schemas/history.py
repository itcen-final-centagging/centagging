"""태깅 이력 조회 응답 스키마입니다."""

import datetime
import typing

import pydantic

from app.schemas import tagging as tagging_schema


class HistoryBoundingBox(pydantic.BaseModel):
    """태깅 이력에 표시할 객체 좌표입니다."""

    xmin: int | float
    ymin: int | float
    xmax: int | float
    ymax: int | float


class HistorySceneImage(pydantic.BaseModel):
    """태깅 이력에 표시할 연출 이미지 정보입니다."""

    image_url: str
    origin_name: str
    bbox: HistoryBoundingBox


class TaggingHistoryListItem(pydantic.BaseModel):
    """태깅 이력 목록의 결과 한 건입니다."""

    result_id: int
    sku_code: str
    product_name: str
    object_name: str | None
    similarity_score: int | None
    created_by: str
    created_at: datetime.datetime
    style_tags: list[str] = pydantic.Field(default_factory=list)
    scene_image: HistorySceneImage


class TaggingHistoryListData(pydantic.BaseModel):
    """태깅 이력 목록 공통 성공 응답의 데이터 본문입니다."""

    items: list[TaggingHistoryListItem]


class HistoryDetailSceneImage(pydantic.BaseModel):
    """태깅 이력 상세의 연출 이미지 정보입니다."""

    image_url: str
    origin_name: str


class HistoryDetectedObject(pydantic.BaseModel):
    """태깅 이력 상세의 탐지 객체 정보입니다."""

    category: str | None
    sub_category: str | None
    attrs: dict[str, typing.Any] = pydantic.Field(default_factory=dict)
    bbox: HistoryBoundingBox
    vlm_mood: tagging_schema.VlmMood | None


class HistoryMatchedSku(pydantic.BaseModel):
    """태깅 이력 상세에서 확정된 SKU 정보입니다."""

    sku_code: str
    product_name: str
    brand: str | None
    price: int | None
    image_url: str | None
    category: str | None
    sub_category: str | None
    attrs: dict[str, typing.Any] = pydantic.Field(default_factory=dict)


class HistoryXaiResult(pydantic.BaseModel):
    """태깅 이력 상세의 XAI 판정 결과입니다."""

    summary: str
    criteria: list[tagging_schema.XaiCriterion] = pydantic.Field(
        default_factory=list
    )


class TaggingHistoryDetail(pydantic.BaseModel):
    """태깅 이력 상세 결과입니다."""

    result_id: int
    created_by: str
    created_at: datetime.datetime
    similarity_score: int | None
    scene_image: HistoryDetailSceneImage
    detected_object: HistoryDetectedObject
    matched_sku: HistoryMatchedSku
    xai_result: HistoryXaiResult | None
