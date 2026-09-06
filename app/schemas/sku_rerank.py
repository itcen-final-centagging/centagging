"""Gemini SKU 재정렬 내부 응답 스키마입니다."""

from pydantic import BaseModel, Field


class SkuRerankResult(BaseModel):
    """Gemini 구조화 응답의 재정렬된 sku_code 목록입니다."""

    ranked_sku_codes: list[str] = Field(default_factory=list)
