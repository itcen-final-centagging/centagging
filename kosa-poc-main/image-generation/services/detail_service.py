"""
디테일 컷 생성 서비스
제품의 재질, 소재 강조 이미지 생성
"""

import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.gemini import Gemini
from common.prompt import (
    create_detail_shot_prompt,
    create_layout_composition_prompt
)
from common.logger import init_logger
from common.utils import get_unique_filepath_pair

logger = init_logger()


class DetailService:
    """디테일 컷 생성 서비스"""

    def __init__(self, gemini_client: Gemini, output_dir: str = "output/details"):
        """
        Args:
            gemini_client: Gemini API 클라이언트
            output_dir: 출력 디렉토리
        """
        self.gemini = gemini_client
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.metadata = {}

    @staticmethod
    def extract_detail_features_from_metadata(metadata: dict) -> List[str]:
        """
        메타데이터에서 디테일 특징 추출
        Args:
            metadata: 메타데이터 딕셔너리 (key_features 포함)

        Returns:
            디테일 특징 리스트
        """
        # key_features에서 추출
        key_features = metadata.get('key_features', [])

        if isinstance(key_features, str):
            try:
                import json
                key_features = json.loads(key_features)
            except:
                # JSON 파싱 실패 시 콜론으로 분리된 리스트로 처리
                key_features = [feature.split(':')[0].strip() for feature in key_features.split('\n') if feature.strip()]

        # 리스트가 아니면 빈 리스트 반환
        if not isinstance(key_features, list):
            logger.warning(f"key_features가 리스트가 아닙니다: {type(key_features)}")
            return []

        # 특징 문자열에서 실제 특징명만 추출 (예: "특징1: 구체적 관찰 내용" -> "특징1")
        extracted_features = []
        for feature in key_features:
            if isinstance(feature, str):
                # 콜론으로 분리된 경우
                if ':' in feature:
                    feature_name = feature.split(':')[0].strip()
                else:
                    feature_name = feature.strip()
                extracted_features.append(feature_name)

        logger.info(f"메타데이터에서 추출한 특징: {extracted_features}")
        return extracted_features

    def generate_detail_shot(
        self,
        source_image_path: str,
        product_name: str,
        fabric: str,
        feature: str,
        reference_image_path: Optional[str] = None,
        zoom_level: float = 3.0,
        base_filename: Optional[str] = None
    ) -> str:
        """
        디테일 컷 생성
        Args:
            source_image_path: 원본 제품 이미지 경로
            product_name: 제품명
            fabric: 패브릭 종류
            feature: 강조할 특징
            reference_image_path: 디테일 촬영 레퍼런스 이미지 경로 (선택사항)
            zoom_level: 확대 배율
            base_filename: 출력 파일의 기본 이름 (확장자 제외)

        Returns:
            생성된 이미지 경로
        """
        logger.info(f"디테일 컷 생성 시작: {product_name} - {fabric} - {feature}")
        if reference_image_path:
            logger.info(f"레퍼런스 이미지 사용: {reference_image_path}")

        try:
            # base_filename이 없으면 입력 파일명에서 추출
            if base_filename is None:
                base_filename = os.path.splitext(os.path.basename(source_image_path))[0]

            # Gemini로 디테일 샷 프롬프트 생성
            prompt = create_detail_shot_prompt(
                product_name=product_name,
                fabric=fabric,
                feature=feature,
                reference_image_path=reference_image_path
            )

            # 레퍼런스 이미지가 있으면 프롬프트에 추가 설명

            # Gemini API를 사용하여 디테일 컷 생성
            # 1. 레퍼런스가 있으면 레퍼런스를 reference_image로, 제품 이미지를 product_images로 전달
            # 2. 레퍼런스가 없으면 제품 이미지를 reference_image로 사용
            if reference_image_path:
                generated_image_bytes = self.gemini.call_generate_image(
                    prompt=prompt,
                    reference_image=reference_image_path,
                    product_images=[source_image_path]
                )
            else:
                generated_image_bytes = self.gemini.call_generate_image(
                    prompt=prompt,
                    reference_image=source_image_path,
                    product_images=None
                )

            # 생성된 이미지 저장
            # 특징명을 파일명에 안전하게 사용 (공백 제거 등)
            safe_feature = feature.replace(" ", "_").replace("/", "_")
            output_filename = f"{base_filename}_detail_{safe_feature}.png"
            output_path = os.path.join(self.output_dir, output_filename)

            json_filename = f"{base_filename}_detail_{safe_feature}.json"
            json_path = os.path.join(self.output_dir, json_filename)

            # 중복 파일명 처리
            output_path, json_path = get_unique_filepath_pair(output_path, json_path)

            # 실제 저장되는 파일명 업데이트
            output_filename = os.path.basename(output_path)

            with open(output_path, "wb") as f:
                f.write(generated_image_bytes)

            # 개별 JSON 메타데이터 저장
            metadata = {
                "source_image": source_image_path,
                "product": product_name,
                "fabric": fabric,
                "feature": feature,
                "reference_image": reference_image_path,
                "zoom_level": zoom_level,
                "output_file": output_filename,
                "generation_time": datetime.now().isoformat(),
                # 추가 메타데이터
                "prompt": prompt,
                "model_name": self.gemini.image_model,
                "aspect_ratio": "1:1",
                "resolution": "1K"
            }
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)

            logger.info(f"디테일 컷 생성 완료: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"디테일 컷 생성 실패: {str(e)}")
            raise e

    def generate_all_detail_shots(
        self,
        source_image_path: str,
        product_name: str,
        fabric: str,
        features: List[str],
        reference_image_path: Optional[str] = None
    ) -> Dict[str, str]:
        """
        모든 디테일 컷 생성

        Args:
            source_image_path: 원본 제품 이미지 경로
            product_name: 제품명
            fabric: 패브릭 종류
            features: 강조할 특징 리스트 (필수)
            reference_image_path: 디테일 촬영 레퍼런스 이미지 경로 (선택사항)

        Returns:
            특징별 생성된 이미지 경로 딕셔너리
        """
        logger.info(f"전체 디테일 컷 생성 시작: {product_name} - {fabric}")
        if reference_image_path:
            logger.info(f"레퍼런스 이미지 사용: {reference_image_path}")

        if not features:
            logger.warning("특징 리스트가 비어있습니다. 디테일 컷을 생성할 수 없습니다.")
            return {}

        detail_images = {}

        for feature in features:
            try:
                output_path = self.generate_detail_shot(
                    source_image_path=source_image_path,
                    product_name=product_name,
                    fabric=fabric,
                    feature=feature,
                    reference_image_path=reference_image_path
                )
                detail_images[feature] = output_path

            except Exception as e:
                logger.error(f"{feature} 디테일 생성 실패: {str(e)}")
                continue

        logger.info(f"전체 디테일 컷 생성 완료: {len(detail_images)}개")
        return detail_images

    def create_layout_composition(
        self,
        product_image_path: str,
        detail_images: List[str],
        layout_type: str = "상세페이지_레이아웃1",
        reference_layout_path: str = None,
        output_filename: str = "layout_composition.png"
    ) -> str:
        """
        레이아웃 합성

        Args:
            product_image_path: 제품 이미지 경로
            detail_images: 디테일 이미지 경로 리스트
            layout_type: 레이아웃 타입
            reference_layout_path: 레이아웃 참고 이미지 경로 (resource/레퍼런스 이미지)
            output_filename: 출력 파일명

        Returns:
            생성된 레이아웃 이미지 경로
        """
        logger.info(f"레이아웃 합성 시작: {layout_type}")

        try:
            # 프롬프트 생성
            elements = ["제품 메인 이미지"] + [f"디테일 이미지 {i+1}" for i in range(len(detail_images))]
            prompt = create_layout_composition_prompt(layout_type, elements, reference_layout_path)

            # Gemini API로 레이아웃 합성 이미지 생성
            # product_image를 reference_image로, detail_images를 product_images로 전달
            
            target_reference = reference_layout_path if reference_layout_path else product_image_path
            target_products = [product_image_path] + detail_images if reference_layout_path else detail_images

            generated_image_bytes = self.gemini.call_generate_image(
                prompt=prompt,
                reference_image=target_reference,
                product_images=target_products
            )

            # 생성된 이미지 저장
            output_path = os.path.join(self.output_dir, output_filename)
            with open(output_path, "wb") as f:
                f.write(generated_image_bytes)

            logger.info(f"레이아웃 합성 완료: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"레이아웃 합성 실패: {str(e)}")
            raise e

    def _save_metadata(self):
        """메타데이터를 JSON 파일로 저장"""
        metadata_path = os.path.join(self.output_dir, "detail_metadata.json")
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)
        logger.debug(f"메타데이터 저장: {metadata_path}")



