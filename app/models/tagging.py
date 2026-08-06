"""Pydantic models for the furniture tagging workflow."""

import typing

import pydantic


class ExtractedMetadata(pydantic.BaseModel):
    """Metadata extracted from one detected furniture crop."""

    category: str
    sub_category: str = ""
    key_features: list[str] = pydantic.Field(default_factory=list)
    attributes: dict[str, typing.Any] = pydantic.Field(default_factory=dict)
    description: str = ""


class RubricScore(pydantic.BaseModel):
    """Per-candidate VLM rubric evaluation."""

    structure: int = 0
    color: int = 0
    detail: int = 0
    context: int = 0


class RubricEvaluation(pydantic.BaseModel):
    """A VLM judgment and its explainable matching rationale."""

    status: str
    total_score: int
    breakdown: RubricScore
    xai_reason: str


class SkuCandidateResponse(pydantic.BaseModel):
    """One ranked SKU candidate returned for a detected object."""

    sku: str
    name: str
    category: str
    kind: str
    image_url: str
    color: str
    material: str
    size: str
    grade: str
    score: int
    vector_score: float
    metadata_score: float
    rubric: RubricEvaluation


class DetectedObjectResponse(pydantic.BaseModel):
    """Detection, extracted metadata, and candidate list for one object."""

    id: str
    name: str
    category: str
    description: str
    confidence: int
    bbox: tuple[float, float, float, float]
    metadata: ExtractedMetadata
    candidates: list[SkuCandidateResponse]


class AnalyzeTaggingResponse(pydantic.BaseModel):
    """The complete synchronous output of one tagging analysis."""

    analysis_id: str
    mode: str
    objects: list[DetectedObjectResponse]


class ReviewTags(pydantic.BaseModel):
    """Operator-confirmed tagging metadata that is saved to the HITL queue."""

    category: str
    color: str
    material: str
    mood: str
    style_tags: list[str] = pydantic.Field(
        default_factory=list,
        validation_alias=pydantic.AliasChoices("style_tags", "styleTags"),
    )


class SaveReviewRequest(pydantic.BaseModel):
    """Request body for saving a human-reviewed SKU decision."""

    analysis_id: str
    object_id: str
    object_name: str
    image_name: str
    selected_sku: str
    tags: ReviewTags


class TaggingHistoryResponse(pydantic.BaseModel):
    """One item in the persisted HITL review history."""

    id: str
    image_name: str
    object_name: str
    product_name: str
    saved_at: str
    sku: str
    tags: ReviewTags
