"""태깅 이력 조회 응답 스키마입니다."""

import datetime
import typing

import pydantic


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


class TaggingHistoryListResponse(pydantic.BaseModel):
    """태깅 이력 목록 API 응답입니다."""

    status: typing.Literal["success"]
    data: dict[
        typing.Literal["items"],
        list[TaggingHistoryListItem],
    ] = pydantic.Field(min_length=1, max_length=1)


class TaggingHistoryDetail(pydantic.BaseModel):
    """태깅 이력 상세 결과입니다."""

    result_id: int
    created_by: str
    created_at: datetime.datetime
    similarity_score: int | None
    scene_image: dict[str, str]
    detected_object: dict[str, typing.Any]
    matched_sku: dict[str, typing.Any]
    xai_result: dict[str, typing.Any] | None


class TaggingHistoryDetailResponse(pydantic.BaseModel):
    """태깅 이력 상세 API 응답입니다."""

    status: typing.Literal["success"]
    data: TaggingHistoryDetail
