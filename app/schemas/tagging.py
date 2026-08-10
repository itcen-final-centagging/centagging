"""장면 이미지 태깅(유사 SKU 추천) API의 요청·응답 스키마입니다."""

import typing

from pydantic import BaseModel


class MatchedSkuImage(BaseModel):
    """매칭 근거가 된 SKU 이미지입니다."""

    sku_image_id: int
    image_type: typing.Literal["MAIN", "ANGLE"]
    image_url: str


class XaiResult(BaseModel):
    """XAI 판정 요약입니다."""

    summary: str


class SkuCandidate(BaseModel):
    """탐지된 객체 1건에 대한 SKU 후보입니다."""

    sku_code: str
    product_name: str
    category: str
    sub_category: str
    attrs: dict[str, str]
    similarity_score: int
    matched_sku_image: MatchedSkuImage
    xai_result: XaiResult


class DetectedObject(BaseModel):
    """탐지된 가구 객체 1건과 해당 SKU 후보 목록입니다."""

    object_index: int
    bbox_coord: dict[str, float]
    sku_candidates: list[SkuCandidate]


class DetectionResult(BaseModel):
    """객체 탐지 결과 본문입니다."""

    processing_status: str
    objects: list[DetectedObject]


class DetectionResponse(BaseModel):
    """객체 탐지 API 응답입니다."""

    status: typing.Literal["success", "error"]
    data: DetectionResult
