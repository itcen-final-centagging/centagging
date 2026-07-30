"""
메타데이터 추출 서비스
제품 이미지에서 카테고리, 속성, 설명 등의 메타데이터 추출
"""

import os
import json
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import config
from common.gemini import Gemini
from common.prompt import (
    create_product_category_prompt,
    create_product_attribute_prompt,
    create_common_attribute_prompt,
    create_product_description_prompt
)
from common.logger import init_logger
from common.utils import get_unique_filepath

logger = init_logger()


class MetadataService:
    """메타데이터 추출 서비스"""

    def __init__(self, gemini_client: Gemini, output_dir: str = "output/metadata"):
        """
        Args:
            gemini_client: Gemini API 클라이언트
            output_dir: 출력 디렉토리
        """
        self.gemini = gemini_client
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.base_columns = [
            'filename',
            'category',
            'sub_category',
            'attributes',
            'description'
        ]
        self.all_columns = set(self.base_columns)

    def extract_metadata(self, image_path: str) -> dict:
        """
        단일 이미지에서 메타데이터 추출
        Args:
            image_path: 이미지 경로

        Returns:
            메타데이터 딕셔너리 (category, sub_category, key_features, attributes 등)
        """
        logger.info(f"메타데이터 추출 시작: {image_path}")

        try:
            # 1. Analyze Category - 메인 카테고리 분석
            category_prompt = create_product_category_prompt(
                product_categories=json.dumps(config.PRODUCT_CATEGORY, ensure_ascii=False, indent=4),
                category_keys=list(config.PRODUCT_CATEGORY.keys()),
                category_values=list(config.PRODUCT_CATEGORY.values())
            )
            category_response = self.gemini.call_gemini_image_text(prompt=category_prompt, image=image_path)
            category_data = json.loads(category_response)

            main_category = category_data.get('category', '')
            sub_category = category_data.get('sub_category', '')
            key_features = category_data.get('key_feature', [])

            logger.info(f"카테고리: {main_category}, 서브카테고리: {sub_category}")

            # 2. Analyze Category-specific Attributes - 카테고리별 가변 속성
            product_attributes = {}
            if main_category in config.PRODUCT_ATTRIBUTE:
                product_attr_config = config.PRODUCT_ATTRIBUTE[main_category]

                # 카테고리별 속성 분석 프롬프트 생성
                product_attr_prompt = create_product_attribute_prompt(
                    category=main_category,
                    attributes_config=json.dumps(product_attr_config, ensure_ascii=False, indent=4)
                )
                product_attr_response = self.gemini.call_gemini_image_text(prompt=product_attr_prompt, image=image_path)
                product_attributes = json.loads(product_attr_response)

            logger.info(f"카테고리별 속성: {list(product_attributes.keys())}")

            # 3. Analyze Common Attributes - 공통 속성 (스타일, 색상, 무늬 등)
            common_attr_prompt = create_common_attribute_prompt(
                colors=list(config.COMMON_ATTRIBUTE['색상']),
                patterns=config.COMMON_ATTRIBUTE['무늬'],
                styles=config.COMMON_ATTRIBUTE['스타일'],
                target_customers=config.COMMON_ATTRIBUTE['타겟 고객'],
                target_ages=config.COMMON_ATTRIBUTE['타겟 연령층']
            )
            common_attr_response = self.gemini.call_gemini_image_text(prompt=common_attr_prompt, image=image_path)
            common_attributes = json.loads(common_attr_response)

            logger.info(f"공통 속성: {list(common_attributes.keys())}")

            # 4. 모든 속성 통합
            all_attributes = {}
            all_attributes.update(product_attributes)
            all_attributes.update(common_attributes)

            # 5. Generate Description
            description_prompt = create_product_description_prompt(
                attributes=json.dumps(all_attributes, ensure_ascii=False, indent=4)
            )
            description_response = self.gemini.call_gemini_text(prompt=description_prompt)
            description_data = json.loads(description_response)

            # 결과 정리
            result = {
                'image_path': image_path,
                'filename': os.path.basename(image_path),
                'category': main_category,
                'sub_category': sub_category,
                'key_features': key_features,
                'attributes': all_attributes,
                'description': description_data
            }

            # JSON 파일로 저장
            self.save_result_json(result)

            logger.info(f"메타데이터 추출 완료: {os.path.basename(image_path)}")
            return result

        except Exception as e:
            logger.error(f"메타데이터 추출 실패: {str(e)}")
            raise

    def save_result_json(self, result):
        """
        메타데이터 결과를 JSON 파일로 저장

        Args:
            result: 메타데이터 결과 딕셔너리
        """
        filename = result['filename']
        name, ext = os.path.splitext(filename)

        # Create output directory
        os.makedirs(self.output_dir, exist_ok=True)
        output_path = os.path.join(self.output_dir, f'{name}.json')

        # 중복 파일명 처리
        output_path = get_unique_filepath(output_path)

        json_data = {key: value for key, value in result.items() if key != 'image_path'}

        # Save as JSON file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=4)

        logger.info(f"JSON 결과 저장: {output_path}")
        return output_path

    @staticmethod
    def load_metadata(json_path: str) -> dict:
        """
        저장된 메타데이터 JSON 파일 로드
        Args:
            json_path: JSON 파일 경로

        Returns:
            메타데이터 딕셔너리
        """
        if not os.path.exists(json_path):
            raise FileNotFoundError(f"메타데이터 파일을 찾을 수 없습니다: {json_path}")

        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)