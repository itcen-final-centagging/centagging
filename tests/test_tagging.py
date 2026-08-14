"""유사 SKU 추천 응답 테스트입니다."""

import typing
import unittest

from PIL import Image

from app.core import config
from app.schemas import tagging
from app.services import gemini_service, similar_sku_service
from app.services.image_processing_service import CroppedObject


class _FakeResult:
    """유사 SKU 조회 결과를 반환합니다."""

    def mappings(self) -> "_FakeResult":
        """매핑 결과 체인을 유지합니다."""
        return self

    def all(self) -> list[dict[str, object]]:
        """Windows형 이미지 경로가 저장된 SKU를 반환합니다."""
        return [
            {
                "sku_id": 622,
                "sku_image_id": 71,
                "sku_code": "CHR-0622",
                "product_name": "메쉬 사무용 의자",
                "image_url": r"data\images\622\main.png",
                "image_type": "MAIN",
                "category": "의자",
                "sub_category": "사무용의자",
                "attributes": {"color": "블랙"},
                "similarity": 0.91,
            }
        ]


class _FakeSession:
    """유사 SKU 검색용 비동기 DB 세션입니다."""

    async def execute(self, _statement: object) -> _FakeResult:
        """준비된 유사 SKU 결과를 반환합니다."""
        return _FakeResult()


class _FakeGeminiService:
    """고정된 이미지 임베딩을 반환합니다."""

    def embed_image(self, _image: Image.Image) -> list[float]:
        """검색 차원에 맞는 임베딩을 반환합니다."""
        return [0.1] * similar_sku_service.EMBEDDING_DIMENSIONS


class SimilarSkuRecommendationTest(unittest.IsolatedAsyncioTestCase):
    """추천 결과가 브라우저에서 접근 가능한 이미지 URL을 제공하는지 검증합니다."""

    async def test_returns_public_sku_image_url(self) -> None:
        """DB의 Windows형 경로를 공개 SKU 이미지 URL로 변환합니다."""
        settings = config.Settings(
            gemini_api_key="test-key",
            gemini_vlm_model="test-vlm",
            gemini_embedding_model="test-embedding",
            mvp_login_id="mvp-user",
            mvp_login_password="test-password",
            image_storage_root="uploads",
            sku_image_root="data/images",
            database=config.DatabaseSettings(
                name="test",
                username="test",
                password="test",
                host="localhost",
                port=5432,
            ),
        )
        service = similar_sku_service.SimilarSkuService(
            session=typing.cast(typing.Any, _FakeSession()),
            gemini_service=typing.cast(
                gemini_service.GeminiService,
                _FakeGeminiService(),
            ),
            settings=settings,
        )
        crop = CroppedObject(
            crop_index=0,
            bbox=tagging.BoundingBox(
                xmin=100,
                ymin=200,
                xmax=600,
                ymax=900,
            ),
            image=Image.new("RGB", (20, 20), color="white"),
            image_bytes=b"image",
        )

        objects = await service.build_detected_objects([crop])

        self.assertEqual(
            objects[0].sku_candidates[0].matched_sku_image.image_url,
            "/sku-images/622/main.png",
        )


if __name__ == "__main__":
    unittest.main()
