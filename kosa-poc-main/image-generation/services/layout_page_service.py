import os
import json
from datetime import datetime
from io import BytesIO
from PIL import Image

from common.logger import init_logger
from common.gemini import Gemini
from common.prompt import create_layout_generation_prompt, create_layout_analysis_prompt
from common.utils import get_unique_filepath_pair

logger = init_logger()

class LayoutPageService:
    # 상수 정의
    DEFAULT_OUTPUT_DIR = "output/layout_pages"
    DEFAULT_ASPECT_RATIO = "1:1"
    DEFAULT_RESOLUTION = "2K"
    DEFAULT_OUTPUT_MIME_TYPE = "image/png"
    DEFAULT_LAYOUT_TYPE = "알 수 없음"

    def __init__(self, gemini_client: Gemini, output_dir: str = None):
        self.gemini = gemini_client
        self.output_dir = output_dir or self.DEFAULT_OUTPUT_DIR
        os.makedirs(self.output_dir, exist_ok=True)

    def _get_default_layout_analysis(self) -> dict:
        """기본 레이아웃 분석 결과 반환"""
        return {
            "layout_type": self.DEFAULT_LAYOUT_TYPE,
            "sections": [],
            "image_areas": [],
            "text_areas": [],
            "design_elements": {},
            "color_scheme": {}
        }

    def analyze_layout(self, layout_image_path: str) -> dict:
        """
        레이아웃 레퍼런스 이미지를 분석하여 구조 정보 추출
        Args:
            layout_image_path: 레이아웃 레퍼런스 이미지 경로

        Returns:
            레이아웃 분석 결과 (dict)
        """
        logger.info(f"레이아웃 분석 시작: {layout_image_path}")
        analysis_response = None

        try:
            analysis_prompt = create_layout_analysis_prompt()
            analysis_response = self.gemini.call_gemini_image_text(
                prompt=analysis_prompt,
                image=layout_image_path
            )
            layout_analysis = json.loads(analysis_response)
            logger.info(f"레이아웃 분석 완료: {layout_analysis.get('layout_type', 'unknown')}")
            return layout_analysis

        except json.JSONDecodeError as e:
            logger.error(f"레이아웃 분석 결과 JSON 파싱 실패: {e}")
            if analysis_response:
                logger.error(f"응답 내용: {analysis_response}")
            return self._get_default_layout_analysis()
        except Exception as e:
            logger.error(f"레이아웃 분석 실패: {e}")
            raise

    def generate_layout_page(self, metadata: dict, layout_image_path: str, num_outputs: int = 1, aspect_ratio: str = None, resolution: str = None) -> list[str]:
        """
        레이아웃 기반 상세페이지 생성

        Args:
            metadata: 제품 메타데이터
            layout_image_path: 레이아웃 레퍼런스 이미지 경로
            num_outputs: 생성할 이미지 개수
            aspect_ratio: 이미지 비율 (1:1, 16:9, 9:16, 4:3, 3:4 등)
            resolution: 해상도 (1K, 2K, 4K)

        Returns:
            생성된 이미지 경로 리스트
        """
        aspect_ratio = aspect_ratio or self.DEFAULT_ASPECT_RATIO
        resolution = resolution or self.DEFAULT_RESOLUTION

        logger.info(f"Generating layout-based detail page with metadata: {metadata}, layout: {layout_image_path}, outputs: {num_outputs}, aspect_ratio: {aspect_ratio}, resolution: {resolution}")
        generated_image_paths = []

        # 제품 이미지 경로 및 파일명 추출
        product_image_path = metadata.get('image_path')
        if not product_image_path or not os.path.exists(product_image_path):
            logger.warning(f"Product image path not found or does not exist: {product_image_path}")
            product_images = None
            base_filename = os.path.splitext(metadata.get('filename', 'layout_page'))[0]
        else:
            product_images = [product_image_path]
            base_filename = os.path.splitext(os.path.basename(product_image_path))[0]

        # 1단계: 레이아웃 분석
        logger.info("1단계: 레이아웃 레퍼런스 이미지 분석 중...")
        layout_analysis = self.analyze_layout(layout_image_path)

        # 분석 결과 저장
        analysis_path = os.path.join(self.output_dir, f"{base_filename}_layout_analysis.json")
        with open(analysis_path, 'w', encoding='utf-8') as f:
            json.dump(layout_analysis, f, ensure_ascii=False, indent=2)
        logger.info(f"레이아웃 분석 결과 저장: {analysis_path}")

        # 2단계: 레이아웃 기반 상세페이지 생성
        logger.info("2단계: 분석된 레이아웃 정보를 바탕으로 상세페이지 생성 중...")
        prompt = create_layout_generation_prompt(metadata, layout_analysis)

        for i in range(num_outputs):
            try:
                # 파일 경로 설정
                output_path = os.path.join(self.output_dir, f"{base_filename}_layout_{i+1}.png")
                json_path = os.path.join(self.output_dir, f"{base_filename}_layout_{i+1}.json")
                output_path, json_path = get_unique_filepath_pair(output_path, json_path)

                # 이미지 생성
                image_bytes = self.gemini.call_generate_image(
                    prompt=prompt,
                    reference_image=layout_image_path,
                    product_images=product_images,
                    aspect_ratio=aspect_ratio,
                    resolution=resolution
                )

                if image_bytes:
                    # 이미지 저장
                    image = Image.open(BytesIO(image_bytes))
                    image.save(output_path)
                    logger.info(f"Generated layout page image: {output_path}")

                    # 메타데이터 저장
                    metadata_to_save = {
                        "product_image": product_image_path,
                        "layout_reference": layout_image_path,
                        "metadata": metadata,
                        "output_file": os.path.basename(output_path),
                        "generation_time": datetime.now().isoformat(),
                        # 추가 메타데이터
                        "prompt": prompt,
                        "model_name": self.gemini.image_model,
                        "aspect_ratio": aspect_ratio,
                        "resolution": resolution,
                        "layout_analysis": layout_analysis
                    }
                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(metadata_to_save, f, ensure_ascii=False, indent=2)

                    generated_image_paths.append(os.path.abspath(output_path))
                else:
                    logger.error(f"Failed to generate image {i+1}")

            except Exception as e:
                logger.error(f"Error generating layout page {i+1}: {e}")

        return generated_image_paths
