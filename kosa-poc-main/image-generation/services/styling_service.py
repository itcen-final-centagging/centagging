"""
스타일링 컷 생성 서비스
레퍼런스 이미지 기반으로 제품 조합 스타일링 이미지 생성
"""

import os
import json
from datetime import datetime
from typing import Dict, List, Optional
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.gemini import Gemini
from common.prompt import (
    create_space_analysis_prompt,
    create_styling_cut_prompt
)
from common.logger import init_logger
from common.utils import save_image, load_image, get_unique_filepath_pair

logger = init_logger()


class StylingService:
    """스타일링 컷 생성 서비스"""

    def __init__(self, gemini_client: Gemini, output_dir: str = "output/styling"):
        """
        Args:
            gemini_client: Gemini API 클라이언트
            output_dir: 출력 디렉토리
        """
        self.gemini = gemini_client
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.metadata = {}

    def analyze_space(self, reference_image_path: str) -> Dict:
        """
        레퍼런스 이미지에서 공간 분석

        Args:
            reference_image_path: 레퍼런스 이미지 경로
        Returns:
            공간 분석 결과
        """
        logger.info(f"공간 분석 시작: {reference_image_path}")

        try:
            # Gemini로 공간 분석 프롬프트 전송
            prompt = create_space_analysis_prompt(reference_image_path)
            
            # Gemini API 호출 (이미지 + 텍스트)
            # call_gemini_image_text는 텍스트 응답을 반환
            response_text = self.gemini.call_gemini_image_text(
                prompt=prompt,
                image=reference_image_path,
                response_type="application/json"
            )

            # JSON 파싱
            if response_text.startswith("```json"):
                response_text = response_text.replace("```json", "").replace("```", "")
            
            space_analysis = json.loads(response_text)
            print(json.dumps(space_analysis, indent=4, sort_keys=True, ensure_ascii=False))
            logger.info("공간 분석 완료")

            # 공간 분석 결과 저장
            results_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
            os.makedirs(results_dir, exist_ok=True)
            ref_image_basename = os.path.splitext(os.path.basename(reference_image_path))[0]
            output_filename = f"{ref_image_basename}_space_analysis.json"
            output_path = os.path.join(results_dir, output_filename)

            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(space_analysis, f, ensure_ascii=False, indent=2)
            logger.info(f"공간 분석 결과 저장: {output_path}")

            return space_analysis

        except Exception as e:
            logger.error(f"공간 분석 실패: {str(e)}")
            # 실패 시 기본값 반환
            return {
                "space_type": "unknown",
                "atmosphere": "unknown",
                "lighting": {},
                "features": []
            }

    def generate_styling_cut(
        self,
        reference_image_path: str,
        products: List[Dict],
        output_filename_prefix: str,
        combination_id: str = "default",
        aspect_ratio: str = "1:1",
        num_outputs: int = 1,
        generation_modes: List[str] = None,
        base_filename: Optional[str] = None
    ) -> List[str]:
        """
        스타일링 컷 생성

        Args:
            reference_image_path: 레퍼런스 이미지 경로
            products: 배치할 제품 리스트
            output_filename_prefix: 출력 파일명 접두사
            combination_id: 조합 ID
            aspect_ratio: 이미지 비율
            num_outputs: 생성할 이미지 개수
            generation_modes: 생성 모드 리스트 (예: ['bg_style_separation', 'style_transfer'])
            base_filename: 출력 파일의 기본 이름 (확장자 제외)

        Returns:
            생성된 이미지 경로 리스트
        """
        if generation_modes is None:
            generation_modes = ["style_transfer"]
        logger.info(f"스타일링 컷 생성 시작: {combination_id}, 비율: {aspect_ratio}, 개수: {num_outputs}, 모드: {generation_modes}")

        generated_paths = []

        try:
            # base_filename이 없으면 첫 번째 제품 이미지에서 추출
            if base_filename is None and products:
                first_product_image = products[0].get('image_path')
                if first_product_image:
                    base_filename = os.path.splitext(os.path.basename(first_product_image))[0]
                else:
                    base_filename = "styling"

            if base_filename is None:
                base_filename = "styling"

            # 공간 분석
            space_analysis = self.analyze_space(reference_image_path)

            # 프롬프트 생성 (비율)
            reference_desc = f"공간 타입: {space_analysis.get('space_type', 'unknown')}, " \
                             f"분위기: {space_analysis.get('atmosphere', 'unknown')}"

            prompt = create_styling_cut_prompt(
                reference_desc,
                products,
                aspect_ratio=aspect_ratio,
                generation_modes=generation_modes
            )

            print(prompt)

            # 요청한 개수만큼 반복 생성
            for i in range(num_outputs):
                output_filename = f"{base_filename}_styling_{i+1}.png"
                output_path = os.path.join(self.output_dir, output_filename)

                json_filename = f"{base_filename}_styling_{i+1}.json"
                json_path = os.path.join(self.output_dir, json_filename)

                # 중복 파일명 처리
                output_path, json_path = get_unique_filepath_pair(output_path, json_path)

                # 실제 저장되는 파일명 업데이트
                output_filename = os.path.basename(output_path)

                # 제품 이미지 경로 리스트 추출
                product_image_paths = []
                for product in products:
                    if 'image_path' in product and product['image_path']:
                         product_image_paths.append(product['image_path'])

                # Gemini API 호출 (실제 이미지 생성)
                try:
                    generated_image_bytes = self.gemini.call_generate_image(
                        prompt=prompt,
                        reference_image=reference_image_path,
                        product_images=product_image_paths,
                        aspect_ratio=aspect_ratio
                    )

                    # 생성된 이미지 저장
                    with open(output_path, "wb") as f:
                        f.write(generated_image_bytes)

                except Exception as e:
                    logger.error(f"이미지 생성 API 호출 실패 ({i+1}/{num_outputs}): {e}")
                    # 실패 시 임시로 레퍼런스 이미지 저장 (Fallback)
                    # 실제 운영에서는 에러를 던지거나 빈 이미지를 처리해야 함
                    try:
                        reference_image = load_image(reference_image_path)
                        save_image(reference_image, output_path)
                    except Exception as fallback_e:
                        logger.error(f"Fallback 저장 실패: {fallback_e}")

                generated_paths.append(output_path)

                # 개별 JSON 메타데이터 저장
                metadata = {
                    "reference_image": reference_image_path,
                    "products_used": products,
                    "space_analysis": space_analysis,
                    "lighting": space_analysis.get("lighting", {}),
                    "output_file": output_filename,
                    "generation_time": datetime.now().isoformat(),
                    "aspect_ratio": aspect_ratio,
                    "generation_modes": generation_modes,
                    # 추가 메타데이터
                    "prompt": prompt,
                    "model_name": self.gemini.image_model,
                    "resolution": "1K"
                }
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, ensure_ascii=False, indent=2)

            logger.info(f"스타일링 컷 생성 완료: {len(generated_paths)}장")
            return generated_paths

        except Exception as e:
            logger.error(f"스타일링 컷 생성 실패: {str(e)}")
            raise

    def generate_multiple_combinations(
        self,
        reference_images: List[str],
        product_combinations: List[List[Dict]],
        aspect_ratio: str = "1:1",
        num_outputs: int = 1,
        generation_modes: List[str] = None
    ) -> List[str]:
        """
        여러 조합의 스타일링 컷 생성

        Args:
            reference_images: 레퍼런스 이미지 경로 리스트
            product_combinations: 제품 조합 리스트
            aspect_ratio: 이미지 비율
            num_outputs: 생성할 이미지 개수
            generation_modes: 생성 모드 리스트 (예: ['bg_style_separation', 'style_transfer'])

        Returns:
            생성된 이미지 경로 리스트 (모든 결과 포함)
        """
        if generation_modes is None:
            generation_modes = ["style_transfer"]
        logger.info(f"다중 스타일링 컷 생성 시작: {len(reference_images)} 레퍼런스, "
                   f"{len(product_combinations)} 조합, 비율: {aspect_ratio}, 개수: {num_outputs}, 모드: {generation_modes}")

        all_generated_images = []

        for ref_idx, ref_image in enumerate(reference_images, 1):
            for comb_idx, products in enumerate(product_combinations, 1):
                combination_id = f"ref{ref_idx}_comb{comb_idx}"
                output_filename_prefix = f"styling_{combination_id}"

                try:
                    output_paths = self.generate_styling_cut(
                        reference_image_path=ref_image,
                        products=products,
                        output_filename_prefix=output_filename_prefix,
                        combination_id=combination_id,
                        aspect_ratio=aspect_ratio,
                        num_outputs=num_outputs,
                        generation_modes=generation_modes
                    )
                    all_generated_images.extend(output_paths)

                except Exception as e:
                    logger.error(f"조합 {combination_id} 생성 실패: {str(e)}")
                    continue

        logger.info(f"다중 스타일링 컷 전체 생성 완료: {len(all_generated_images)}개")
        return all_generated_images

    def _save_metadata(self):
        """메타데이터를 JSON 파일로 저장"""
        metadata_path = os.path.join(self.output_dir, "iloom_테싯_styling_1.json")
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)
        logger.debug(f"메타데이터 저장: {metadata_path}")




