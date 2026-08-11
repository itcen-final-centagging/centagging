"""crop 이미지의 가구 속성 추출 스키마입니다."""

from pydantic import BaseModel, Field

class FurnitureAttributeResult(BaseModel):
    """crop 이미지에서 추출한 가구 속성입니다."""

    category: str
    sub_category: str | None = None
    attributes: dict[str, str] = Field(default_factory=dict)