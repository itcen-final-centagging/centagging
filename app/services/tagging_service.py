"""Integrated object detection, retrieval, VLM validation, and HITL workflow."""

import datetime
import io
import json
import logging
import pathlib
import typing
import uuid

from google import genai
from google.genai import types
from PIL import Image

from app.core import config
from app.models import tagging
from app.services.catalog_repository import (
    CATALOG_ITEMS,
    CatalogItem,
    CatalogRepository,
)

LOGGER = logging.getLogger(__name__)

GenerateContentPart = (
    str
    | Image.Image
    | types.File
    | types.FileDict
    | types.Part
    | types.PartDict
)


class TaggingInputError(ValueError):
    """Raised when an uploaded image cannot be processed safely."""


class TaggingService:
    """Run the reusable PoC capabilities as one API-oriented workflow."""

    def __init__(self, settings: config.Settings) -> None:
        self._settings = settings
        self._repository = CatalogRepository(settings)
        self._in_memory_history: list[tagging.TaggingHistoryResponse] = []

    @property
    def is_configured(self) -> bool:
        """Return whether live Gemini calls can be used."""
        return bool(self._settings.gemini_api_key)

    def initialize(self) -> None:
        """Prepare the database-backed catalog if PostgreSQL is available."""
        self._repository.initialize()

    def analyze(
        self,
        image_bytes: bytes,
        image_name: str,
        target_description: str | None = None,
    ) -> tagging.AnalyzeTaggingResponse:
        """Run detection → metadata → retrieval → rubric validation for one image."""
        image = self._open_image(image_bytes)
        mode = "live" if self.is_configured else "mock"
        detections = self._detect_objects(image, target_description)

        objects: list[tagging.DetectedObjectResponse] = []
        for index, detection in enumerate(detections, start=1):
            cropped_image = self._crop_image(image, detection["bbox"])
            metadata = self._extract_metadata(cropped_image, detection["label"])
            embedding = self._embed_image(cropped_image)
            candidates = self._rank_candidates(
                cropped_image,
                metadata,
                embedding,
            )
            objects.append(
                tagging.DetectedObjectResponse(
                    id=f"object-{index:02d}",
                    name=self._display_name(detection["label"], metadata),
                    category=metadata.category,
                    description=self._object_description(metadata),
                    confidence=detection["confidence"],
                    bbox=tuple(detection["bbox"]),
                    metadata=metadata,
                    candidates=candidates,
                )
            )

        return tagging.AnalyzeTaggingResponse(
            analysis_id=str(uuid.uuid4()),
            mode=mode,
            objects=objects,
        )

    def search_catalog(self, query: str) -> list[tagging.SkuCandidateResponse]:
        """Search searchable SKU catalog entries for manual selection."""
        items = self._repository.search_catalog(query)
        return [self._catalog_response(item) for item in items]

    def get_catalog_image_path(self, sku: str) -> pathlib.Path | None:
        """Return a packaged SKU reference image without accepting arbitrary paths."""
        item = next((item for item in CATALOG_ITEMS if item.sku == sku), None)
        if item is None:
            return None
        image_path = self._reference_image_path(item.image_filename)
        return image_path if image_path.exists() else None

    def save_review(
        self,
        request: tagging.SaveReviewRequest,
    ) -> tagging.TaggingHistoryResponse:
        """Persist one operator-confirmed tag decision to the HITL queue."""
        selected_item = next(
            (
                item
                for item in CATALOG_ITEMS
                if item.sku == request.selected_sku
            ),
            None,
        )
        if selected_item is None:
            raise TaggingInputError(
                "The selected SKU does not exist in the catalog."
            )

        review_id = str(uuid.uuid4())
        tags = request.tags.model_dump()
        history_item = tagging.TaggingHistoryResponse(
            id=review_id,
            image_name=request.image_name,
            object_name=request.object_name,
            product_name=selected_item.name,
            saved_at=self._format_saved_at(),
            sku=request.selected_sku,
            tags=request.tags,
        )
        self._repository.save_review(
            {
                "id": review_id,
                "analysis_id": request.analysis_id,
                "object_id": request.object_id,
                "object_name": request.object_name,
                "image_name": request.image_name,
                "sku": request.selected_sku,
                "tags": tags,
            }
        )
        if not self._repository.is_available:
            self._in_memory_history.insert(0, history_item)
        return history_item

    def get_history(self) -> list[tagging.TaggingHistoryResponse]:
        """Return persisted HITL history, with a memory fallback for local mock mode."""
        database_history = self._repository.get_history()
        if not self._repository.is_available:
            return self._in_memory_history.copy()
        return [
            tagging.TaggingHistoryResponse(
                id=str(item["id"]),
                image_name=item["image_name"],
                object_name=item["object_name"],
                product_name=item["product_name"],
                saved_at=item["created_at"]
                .astimezone()
                .strftime("%Y. %m. %d. %H:%M"),
                sku=item["sku"],
                tags=tagging.ReviewTags.model_validate(item["tags"]),
            )
            for item in database_history
        ]

    def _detect_objects(
        self,
        image: Image.Image,
        target_description: str | None,
    ) -> list[dict[str, typing.Any]]:
        if not self.is_configured:
            return self._mock_detections(target_description)

        prompt = """
        Find every furniture object in this lifestyle image. Include chairs, desks,
        tables, sofas, lamps, cabinets, and storage furniture. Return only JSON:
        {
          "detections": [
            {
              "label": "chair",
              "confidence": 96,
              "bbox": [ymin, xmin, ymax, xmax]
            }
          ]
        }
        bbox uses 0-1000 normalized coordinates. Ignore decor, walls, and people.
        """
        if target_description:
            prompt += (
                f"\nPrioritize this target description: {target_description}"
            )
        try:
            contents: list[GenerateContentPart] = [image, prompt]
            response = self._client().models.generate_content(
                model=self._settings.gemini_vlm_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                ),
            )
            payload = self._response_payload(response.text)
            detections = [
                self._normalize_detection(item)
                for item in payload.get("detections", [])
            ]
            return [item for item in detections if item is not None]
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            LOGGER.warning(
                "VLM detection response was invalid; using PoC mock: %s", error
            )
            return self._mock_detections(target_description)
        except Exception as error:  # External Gemini SDK boundary.
            LOGGER.warning("VLM detection failed; using PoC mock: %s", error)
            return self._mock_detections(target_description)

    def _extract_metadata(
        self,
        cropped_image: Image.Image,
        detected_label: str,
    ) -> tagging.ExtractedMetadata:
        if not self.is_configured:
            return self._mock_metadata(detected_label)

        prompt = """
        Extract product metadata from this cropped furniture image. Return only JSON:
        {
          "category": "의자",
          "sub_category": "오피스체어",
          "key_features": ["메쉬", "하이백"],
          "attributes": {
            "color": "화이트",
            "material": "메쉬",
            "style": "모던",
            "structure": "5스타 캐스터"
          },
          "description": "short Korean product description"
        }
        Use Korean values. Be concrete only when the image supports the attribute.
        """
        try:
            contents: list[GenerateContentPart] = [
                cropped_image,
                prompt,
            ]
            response = self._client().models.generate_content(
                model=self._settings.gemini_vlm_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                ),
            )
            payload = self._response_payload(response.text)
            return tagging.ExtractedMetadata(
                category=self._normalize_category(
                    str(payload.get("category", ""))
                ),
                sub_category=str(payload.get("sub_category", "")),
                key_features=self._string_list(payload.get("key_features", [])),
                attributes=self._dictionary(payload.get("attributes", {})),
                description=str(payload.get("description", "")),
            )
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            LOGGER.warning(
                "Metadata response was invalid; using PoC mock: %s", error
            )
            return self._mock_metadata(detected_label)
        except Exception as error:  # External Gemini SDK boundary.
            LOGGER.warning(
                "Metadata extraction failed; using PoC mock: %s", error
            )
            return self._mock_metadata(detected_label)

    def _embed_image(self, image: Image.Image) -> list[float] | None:
        if not self.is_configured:
            return None
        try:
            image_bytes = self._to_jpeg_bytes(image)
            response = self._client().models.embed_content(
                model=self._settings.gemini_embedding_model,
                contents=types.Part.from_bytes(
                    data=image_bytes,
                    mime_type="image/jpeg",
                ),
                config=types.EmbedContentConfig(
                    output_dimensionality=self._settings.gemini_embedding_dimensions
                ),
            )
            embeddings = response.embeddings
            if not embeddings or not embeddings[0].values:
                raise ValueError("The embedding response was empty.")
            values = list(embeddings[0].values)
            if len(values) != self._settings.gemini_embedding_dimensions:
                raise ValueError("Unexpected embedding dimensions.")
            return values
        except Exception as error:  # External Gemini SDK boundary.
            LOGGER.warning(
                "Image embedding failed; using metadata fallback: %s", error
            )
            return None

    def _rank_candidates(
        self,
        cropped_image: Image.Image,
        metadata: tagging.ExtractedMetadata,
        embedding: list[float] | None,
    ) -> list[tagging.SkuCandidateResponse]:
        catalog_candidates = self._retrieve_candidates(
            embedding, metadata.category
        )
        rubric_results = self._evaluate_candidates(
            cropped_image, catalog_candidates
        )
        response_items: list[tagging.SkuCandidateResponse] = []

        for item, vector_score in catalog_candidates:
            metadata_score = self._metadata_score(metadata, item)
            rubric = rubric_results.get(item.sku, self._fallback_rubric(item))
            final_score = round(
                (vector_score * 55 + metadata_score * 15)
                + (rubric.total_score * 0.30)
            )
            response_items.append(
                tagging.SkuCandidateResponse(
                    **self._catalog_response_fields(item),
                    grade=self._score_grade(final_score),
                    score=max(0, min(100, final_score)),
                    vector_score=round(vector_score, 4),
                    metadata_score=round(metadata_score, 4),
                    rubric=rubric,
                )
            )
        return sorted(response_items, key=lambda item: item.score, reverse=True)

    def _retrieve_candidates(
        self,
        embedding: list[float] | None,
        category: str,
    ) -> list[tuple[CatalogItem, float]]:
        if embedding:
            self._ensure_catalog_embeddings()
            matches = self._repository.search_by_embedding(
                embedding,
                category,
                self._settings.catalog_top_k,
            )
            if matches:
                return matches

        filtered_items = [
            item for item in CATALOG_ITEMS if item.category == category
        ]
        fallback_items = filtered_items or list(CATALOG_ITEMS)
        fallback_scores = (0.96, 0.84, 0.71, 0.63, 0.51)
        return list(
            zip(
                fallback_items[: self._settings.catalog_top_k],
                fallback_scores,
                strict=False,
            )
        )

    def _ensure_catalog_embeddings(self) -> None:
        if not self._repository.is_available or not self.is_configured:
            return
        for item in self._repository.get_items_missing_embeddings():
            image_path = self._reference_image_path(item.image_filename)
            if not image_path.exists():
                LOGGER.warning(
                    "Missing catalog reference image: %s", image_path
                )
                continue
            with Image.open(image_path) as catalog_image:
                embedding = self._embed_image(catalog_image.convert("RGB"))
            if embedding:
                self._repository.save_embedding(item.sku, embedding)

    def _evaluate_candidates(
        self,
        cropped_image: Image.Image,
        candidates: list[tuple[CatalogItem, float]],
    ) -> dict[str, tagging.RubricEvaluation]:
        if not self.is_configured:
            return {
                item.sku: self._fallback_rubric(item) for item, _ in candidates
            }

        contents: list[GenerateContentPart] = [cropped_image]
        valid_candidates: list[CatalogItem] = []
        for item, _ in candidates:
            image_path = self._reference_image_path(item.image_filename)
            if not image_path.exists():
                continue
            contents.extend(
                [f"Candidate SKU: {item.sku}", Image.open(image_path)]
            )
            valid_candidates.append(item)
        if not valid_candidates:
            return {
                item.sku: self._fallback_rubric(item) for item, _ in candidates
            }

        prompt = """
        Compare Target Cropped Image against every Candidate SKU Image. Return only JSON:
        {
          "evaluations": [
            {
              "sku_id": "sku_chair",
              "status": "Matched",
              "total_score": 92,
              "breakdown": {
                "structure": 29,
                "color": 28,
                "detail": 18,
                "context": 17
              },
              "xai_reason": "Korean explanation"
            }
          ]
        }
        Use structure(30), color(30), detail(20), and context(20). A score below 70
        must be Rejected. Do not omit any provided candidate.
        """
        contents.append(prompt)
        try:
            response = self._client().models.generate_content(
                model=self._settings.gemini_vlm_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                ),
            )
            payload = self._response_payload(response.text)
            evaluations = {
                str(entry["sku_id"]): self._to_rubric(entry)
                for entry in payload.get("evaluations", [])
            }
            return {
                item.sku: evaluations.get(item.sku, self._fallback_rubric(item))
                for item, _ in candidates
            }
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            LOGGER.warning(
                "Rubric response was invalid; using PoC mock: %s", error
            )
            return {
                item.sku: self._fallback_rubric(item) for item, _ in candidates
            }
        except Exception as error:  # External Gemini SDK boundary.
            LOGGER.warning(
                "VLM rubric validation failed; using PoC mock: %s", error
            )
            return {
                item.sku: self._fallback_rubric(item) for item, _ in candidates
            }
        finally:
            for content in contents:
                if (
                    isinstance(content, Image.Image)
                    and content is not cropped_image
                ):
                    content.close()

    def _client(self) -> genai.Client:
        return genai.Client(api_key=self._settings.gemini_api_key)

    def _reference_image_path(self, image_filename: str) -> pathlib.Path:
        docker_path = pathlib.Path("/app/reference_assets") / image_filename
        if docker_path.exists():
            return docker_path
        project_root = pathlib.Path(__file__).resolve().parents[2]
        return (
            project_root
            / "kosa-poc-main"
            / "vlm-tagging"
            / "images"
            / image_filename
        )

    @staticmethod
    def _open_image(image_bytes: bytes) -> Image.Image:
        if not image_bytes:
            raise TaggingInputError("The uploaded image is empty.")
        try:
            image = Image.open(io.BytesIO(image_bytes))
            image.load()
        except (OSError, ValueError) as error:
            raise TaggingInputError(
                "The uploaded file is not a valid image."
            ) from error
        if image.width < 512 or image.height < 512:
            raise TaggingInputError(
                "The image must be at least 512 × 512 pixels."
            )
        return image.convert("RGB")

    @staticmethod
    def _crop_image(
        image: Image.Image,
        bbox: list[float],
    ) -> Image.Image:
        width, height = image.size
        ymin, xmin, ymax, xmax = bbox
        left = max(0, min(round(xmin * width / 1000), width - 1))
        top = max(0, min(round(ymin * height / 1000), height - 1))
        right = max(left + 1, min(round(xmax * width / 1000), width))
        bottom = max(top + 1, min(round(ymax * height / 1000), height))
        return image.crop((left, top, right, bottom))

    @staticmethod
    def _to_jpeg_bytes(image: Image.Image) -> bytes:
        output = io.BytesIO()
        image.convert("RGB").save(output, format="JPEG", quality=92)
        return output.getvalue()

    def _normalize_detection(
        self,
        item: typing.Any,
    ) -> dict[str, typing.Any] | None:
        if not isinstance(item, dict):
            return None
        raw_bbox = item.get("bbox")
        if not isinstance(raw_bbox, list) or len(raw_bbox) != 4:
            return None
        try:
            bbox = [max(0.0, min(1000.0, float(value))) for value in raw_bbox]
            ymin, xmin, ymax, xmax = bbox
        except (TypeError, ValueError):
            return None
        if ymin >= ymax or xmin >= xmax:
            return None
        return {
            "label": str(item.get("label", "furniture")),
            "confidence": max(0, min(100, int(item.get("confidence", 80)))),
            "bbox": bbox,
        }

    @staticmethod
    def _mock_detections(
        target_description: str | None,
    ) -> list[dict[str, typing.Any]]:
        if target_description and any(
            word in target_description for word in ("없", "실패", "찾지")
        ):
            return []
        return [
            {
                "label": "chair",
                "confidence": 96,
                "bbox": [345.0, 230.0, 995.0, 570.0],
            },
            {
                "label": "desk",
                "confidence": 93,
                "bbox": [420.0, 210.0, 970.0, 856.0],
            },
            {
                "label": "lamp",
                "confidence": 88,
                "bbox": [190.0, 650.0, 475.0, 846.0],
            },
        ]

    def _mock_metadata(self, detected_label: str) -> tagging.ExtractedMetadata:
        values: dict[str, tagging.ExtractedMetadata] = {
            "chair": tagging.ExtractedMetadata(
                category="의자",
                sub_category="오피스체어",
                key_features=[
                    "메쉬",
                    "화이트 프레임",
                    "하이백",
                    "5스타 캐스터",
                ],
                attributes={
                    "color": "화이트",
                    "material": "메쉬 · 패브릭",
                    "style": "모던",
                    "structure": "5스타 캐스터",
                },
                description="화이트 메쉬 하이백 오피스체어",
            ),
            "desk": tagging.ExtractedMetadata(
                category="테이블",
                sub_category="오피스 책상",
                key_features=["원목 상판", "화이트 프레임", "직사각형"],
                attributes={
                    "color": "오크",
                    "material": "원목 · 스틸",
                    "style": "모던",
                    "structure": "4다리",
                },
                description="원목 상판의 직사각형 오피스 책상",
            ),
            "lamp": tagging.ExtractedMetadata(
                category="조명",
                sub_category="데스크 스탠드",
                key_features=["블랙", "원형 갓", "스탠드"],
                attributes={
                    "color": "블랙",
                    "material": "스틸",
                    "style": "미니멀",
                    "structure": "원형 베이스",
                },
                description="블랙 스틸 데스크 스탠드",
            ),
        }
        return values.get(
            detected_label.lower(),
            tagging.ExtractedMetadata(
                category="기타", description="탐지된 가구"
            ),
        )

    def _fallback_rubric(self, item: CatalogItem) -> tagging.RubricEvaluation:
        scores = {
            "sku_chair": (29, 28, 18, 17),
            "sku_chair_black": (28, 8, 18, 16),
            "sku_desk": (29, 29, 18, 19),
            "sku_lamp": (28, 29, 18, 18),
            "sku_cabinet": (14, 15, 12, 10),
        }.get(item.sku, (18, 18, 12, 12))
        total_score = sum(scores)
        return tagging.RubricEvaluation(
            status="Matched" if total_score >= 70 else "Rejected",
            total_score=total_score,
            breakdown=tagging.RubricScore(
                structure=scores[0],
                color=scores[1],
                detail=scores[2],
                context=scores[3],
            ),
            xai_reason=(
                f"{item.name}의 형태·색상·소재 특성을 객체 크롭과 비교한 "
                "PoC 루브릭 결과입니다."
            ),
        )

    @staticmethod
    def _to_rubric(entry: dict[str, typing.Any]) -> tagging.RubricEvaluation:
        breakdown = entry.get("breakdown", {})
        if not isinstance(breakdown, dict):
            breakdown = {}
        return tagging.RubricEvaluation(
            status=str(entry.get("status", "Rejected")),
            total_score=max(0, min(100, int(entry.get("total_score", 0)))),
            breakdown=tagging.RubricScore(
                structure=max(0, min(30, int(breakdown.get("structure", 0)))),
                color=max(0, min(30, int(breakdown.get("color", 0)))),
                detail=max(0, min(20, int(breakdown.get("detail", 0)))),
                context=max(0, min(20, int(breakdown.get("context", 0)))),
            ),
            xai_reason=str(entry.get("xai_reason", "루브릭 설명이 없습니다.")),
        )

    @staticmethod
    def _metadata_score(
        metadata: tagging.ExtractedMetadata,
        item: CatalogItem,
    ) -> float:
        category_score = 0.6 if metadata.category == item.category else 0.0
        extracted_tokens = set(metadata.key_features)
        extracted_tokens.update(
            str(value) for value in metadata.attributes.values()
        )
        catalog_tokens = set(item.key_features)
        catalog_tokens.update(item.attributes.values())
        overlap = len(extracted_tokens & catalog_tokens)
        feature_score = min(0.4, overlap * 0.1)
        return category_score + feature_score

    @staticmethod
    def _catalog_response_fields(item: CatalogItem) -> dict[str, str]:
        return {
            "sku": item.sku,
            "name": item.name,
            "category": item.category,
            "kind": item.kind,
            "image_url": f"/api/v1/taggings/catalog/{item.sku}/image",
            "color": item.color,
            "material": item.material,
            "size": item.size,
        }

    def _catalog_response(
        self, item: CatalogItem
    ) -> tagging.SkuCandidateResponse:
        rubric = self._fallback_rubric(item)
        return tagging.SkuCandidateResponse(
            **self._catalog_response_fields(item),
            grade="검수 필요",
            score=0,
            vector_score=0,
            metadata_score=0,
            rubric=rubric,
        )

    @staticmethod
    def _normalize_category(value: str) -> str:
        lookup = {
            "chair": "의자",
            "desk": "테이블",
            "table": "테이블",
            "lamp": "조명",
            "light": "조명",
            "cabinet": "수납",
            "storage": "수납",
            "sofa": "소파",
        }
        return lookup.get(value.strip().lower(), value.strip() or "기타")

    @staticmethod
    def _display_name(
        detected_label: str,
        metadata: tagging.ExtractedMetadata,
    ) -> str:
        if metadata.description:
            return metadata.description
        return f"{TaggingService._normalize_category(detected_label)} 객체"

    @staticmethod
    def _object_description(metadata: tagging.ExtractedMetadata) -> str:
        values = [
            str(metadata.attributes.get(key, ""))
            for key in ("color", "material", "style")
        ]
        return (
            " · ".join(value for value in values if value)
            or metadata.sub_category
        )

    @staticmethod
    def _string_list(value: typing.Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if str(item).strip()]

    @staticmethod
    def _dictionary(value: typing.Any) -> dict[str, typing.Any]:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _response_payload(response_text: str | None) -> dict[str, typing.Any]:
        if not response_text:
            raise ValueError("The Gemini response was empty.")
        payload = json.loads(response_text)
        if not isinstance(payload, dict):
            raise ValueError("The Gemini response was not a JSON object.")
        return payload

    @staticmethod
    def _score_grade(score: int) -> str:
        if score >= 85:
            return "높음"
        if score >= 70:
            return "중간"
        return "낮음"

    @staticmethod
    def _format_saved_at() -> str:
        return datetime.datetime.now().strftime("%Y. %m. %d. %H:%M")
