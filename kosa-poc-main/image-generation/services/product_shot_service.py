"""
단품 컷 생성 서비스
제품 이미지에서 다각도 스튜디오 컷 생성
"""

import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from PIL import Image
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.gemini import Gemini
from common.prompt import (
    create_product_shot_prompt,
    create_background_removal_prompt
)
from common.logger import init_logger
from common.utils import save_image, load_image, get_unique_filepath_pair

logger = init_logger()


class ProductShotService:
    """단품 컷 생성 서비스"""

    # 표준 촬영 각도
    STANDARD_ANGLES = ["front", "half_side", "side", "back_side", "back"]

    def __init__(self, gemini_client: Gemini, output_dir: str = "output/product_shots"):
        """
        Args:
            gemini_client: Gemini API 클라이언트
            output_dir: 출력 디렉토리
        """
        self.gemini = gemini_client
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.metadata = {}

    def remove_background(self, image_path: str) -> Image.Image:
        """
        배경 제거
        Args:
            image_path: 이미지 경로
        Returns:
            배경이 제거된 이미지 (PIL Image)
        """
        logger.info(f"배경 제거 시작: {image_path}")

        try:
            # 배경 제거 프롬프트 생성
            prompt = create_background_removal_prompt("remove background and make it transparent or white")

            # Gemini로 배경 제거 요청
            # generate_image는 bytes를 반환
            generated_image_bytes = self.gemini.call_generate_image(
                prompt=prompt,
                reference_image=image_path, # 원본 이미지를 레퍼런스로 전달
            )

            # bytes를 PIL Image로 변환
            import io
            output_image = Image.open(io.BytesIO(generated_image_bytes))

            logger.info("배경 제거 완료")
            return output_image

        except Exception as e:
            logger.error(f"배경 제거 실패: {str(e)}")
            # 실패 시 원본 반환 (Fallback)
            return load_image(image_path)

    def generate_angle_shot(
        self,
        source_image_path: str,
        product_name: str,
        fabric: str,
        angle: str,
        remove_bg: bool = True,
        fabric_reference_path: Optional[str] = None,
        aspect_ratio: str = "1:1",
        resolution: str = "2K",
        file_format: str = "PNG",
        background_type: str = "studio_white",
        rendering_style: str = "포토리얼리스틱 (Photorealistic)",
        lighting_style: str = "3점 조명법",
        base_filename: Optional[str] = None
    ) -> str:
        """
        특정 각도의 단품 컷 생성

        Args:
            source_image_path: 원본 이미지 경로
            product_name: 제품명
            fabric: 패브릭 종류
            angle: 촬영 각도
            remove_bg: 배경 제거 여부
            fabric_reference_path: 소재 참조 이미지 경로
            aspect_ratio: 이미지 비율
            resolution: 결과물 해상도
            file_format: 파일 형식 (PNG, JPG)
            background_type: 배경 타입
            rendering_style: 렌더링 스타일
            lighting_style: 조명 스타일
            base_filename: 출력 파일의 기본 이름 (확장자 제외)

        Returns:
            생성된 이미지 경로
        """
        logger.info(f"단품 컷 생성 시작: {product_name} - {fabric} - {angle} ({resolution})")

        try:
            # 입력 파일명에서 기본 이름 추출
            if base_filename is None:
                base_filename = os.path.splitext(os.path.basename(source_image_path))[0]

            target_image_path = source_image_path

            if remove_bg:
                # 배경 제거 수행 후 임시 저장
                bg_removed_img = self.remove_background(source_image_path)
                intermediate_filename = f"bg_removed_{os.path.basename(source_image_path)}"
                intermediate_path = os.path.join(self.output_dir, intermediate_filename)
                save_image(bg_removed_img, intermediate_path)
                target_image_path = intermediate_path

            # 프롬프트 생성
            has_fabric_ref = fabric_reference_path is not None
            prompt = create_product_shot_prompt(
                product_name=product_name,
                fabric=fabric,
                angle=angle,
                background_type=background_type,
                has_fabric_reference=has_fabric_ref,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                file_format=file_format,
                rendering_style=rendering_style,
                lighting_style=lighting_style
            )

            # Gemini로 단품 컷 생성
            product_imgs = [target_image_path]
            ref_img = fabric_reference_path if has_fabric_ref else None

            try:
                generated_image_bytes = self.gemini.call_generate_image(
                    prompt=prompt,
                    reference_image=ref_img,
                    product_images=product_imgs,
                    aspect_ratio=aspect_ratio
                )

                output_filename = f"{base_filename}_{angle}.png"
                output_path = os.path.join(self.output_dir, output_filename)

                json_filename = f"{base_filename}_{angle}.json"
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
                    "angle": angle,
                    "rotation": self._get_rotation_angle(angle),
                    "resolution": resolution,
                    "aspect_ratio": aspect_ratio,
                    "background_type": background_type,
                    "rendering_style": rendering_style,
                    "lighting_style": lighting_style,
                    "output_file": output_filename,
                    "generation_time": datetime.now().isoformat(),
                    # 추가 메타데이터
                    "prompt": prompt,
                    "model_name": self.gemini.image_model,
                    "fabric_reference": fabric_reference_path if has_fabric_ref else None,
                    "remove_bg": remove_bg
                }
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, ensure_ascii=False, indent=2)

                # 임시 파일 삭제
                if remove_bg and os.path.exists(target_image_path) and target_image_path != source_image_path:
                    os.remove(target_image_path)

                logger.info(f"단품 컷 생성 완료: {output_path}")
                return output_path

            except Exception as e:
                logger.error(f"단품 컷 생성 API 호출 실패: {e}")
                # 실패 시 원본 저장 (Fallback)
                output_filename = f"{base_filename}_{angle}.png"
                output_path = os.path.join(self.output_dir, output_filename)

                # 원본 이미지를 복사
                img = load_image(source_image_path)
                save_image(img, output_path)
                return output_path

        except Exception as e:
            logger.error(f"단품 컷 생성 실패: {str(e)}")
            raise

    def generate_all_angles(
        self,
        source_images: List[str],
        product_name: str,
        fabric: str,
        reference_quality_image: Optional[str] = None,
        fabric_reference_path: Optional[str] = None,
        aspect_ratio: str = "1:1",
        resolution: str = "2K",
        file_format: str = "PNG",
        background_type: str = "studio_white",
        rendering_style: str = "포토리얼리스틱 (Photorealistic)",
        lighting_style: str = "3점 조명법"
    ) -> Dict[str, str]:
        """
        5가지 각도의 단품 컷 모두 생성

        Args:
            source_images: 원본 이미지 경로 리스트
            product_name: 제품명
            fabric: 패브릭 종류
            reference_quality_image: 품질 레퍼런스 이미지 경로
            fabric_reference_path: 소재 참조 이미지 경로
            aspect_ratio: 이미지 비율
            resolution: 결과물 해상도
            file_format: 파일 형식 (PNG, JPG)
            background_type: 배경 타입
            rendering_style: 렌더링 스타일
            lighting_style: 조명 스타일

        Returns:
            각도별 생성된 이미지 경로 딕셔너리
        """
        logger.info(f"전체 각도 단품 컷 생성 시작: {product_name} - {fabric}")
        angle_images = {}

        # 첫 번째 소스 이미지에서 base_filename 추출
        source_image = source_images[0] if source_images else None
        if not source_image:
            logger.error("원본 이미지가 없습니다.")
            return angle_images

        base_filename = os.path.splitext(os.path.basename(source_image))[0]

        for angle in self.STANDARD_ANGLES:
            try:
                output_path = self.generate_angle_shot(
                    source_image_path=source_image,
                    product_name=product_name,
                    fabric=fabric,
                    angle=angle,
                    remove_bg=True,
                    fabric_reference_path=fabric_reference_path,
                    aspect_ratio=aspect_ratio,
                    resolution=resolution,
                    file_format=file_format,
                    background_type=background_type,
                    rendering_style=rendering_style,
                    lighting_style=lighting_style,
                    base_filename=base_filename
                )

                angle_images[angle] = output_path

            except Exception as e:
                logger.error(f"{angle} 각도 생성 실패: {str(e)}")
                continue

        # 메타데이터 저장
        metadata_key = f"{product_name}_{fabric}"
        self.metadata[metadata_key] = {
            "source_images": source_images,
            "reference_quality": reference_quality_image,
            "fabric": fabric,
            "angles": {
                angle: {
                    "file": os.path.basename(path),
                    "rotation": self._get_rotation_angle(angle),
                    "camera_distance": 2.5,
                    "resolution": resolution
                }
                for angle, path in angle_images.items()
            },
            "processing": {
                "background_removed": True,
                "upscaled": False,
                "color_corrected": False
            },
            "generation_time": datetime.now().isoformat()
        }

        self._save_metadata()

        logger.info(f"전체 각도 단품 컷 생성 완료: {len(angle_images)}개")
        return angle_images

    def generate_multi_fabric_shots(
        self,
        source_images: List[str],
        product_name: str,
        fabrics: List[str]
    ) -> Dict[str, Dict[str, str]]:
        """
        다중 소재 버전 단품 컷 생성

        Args:
            source_images: 원본 이미지 경로 리스트
            product_name: 제품명
            fabrics: 패브릭 종류 리스트

        Returns:
            소재별, 각도별 이미지 경로 딕셔너리
        """
        logger.info(f"다중 소재 단품 컷 생성 시작: {product_name} - {len(fabrics)}개 소재")

        all_fabric_images = {}

        for fabric in fabrics:
            try:
                angle_images = self.generate_all_angles(
                    source_images=source_images,
                    product_name=product_name,
                    fabric=fabric
                )
                all_fabric_images[fabric] = angle_images

            except Exception as e:
                logger.error(f"{fabric} 소재 생성 실패: {str(e)}")
                continue

        logger.info(f"다중 소재 단품 컷 생성 완료: {len(all_fabric_images)}개 소재")
        return all_fabric_images

    def generate_modeling_images_from_real_photos(
        self,
        real_photo_dir: str,
        fabric_reference_path: str,
        product_name: str,
        fabric: str,
        output_subdir: Optional[str] = None
    ) -> Dict[str, str]:
        """
        실제 제품 사진들에서 모델링 이미지 생성

        Args:
            real_photo_dir: 실제 제품 사진들이 있는 디렉토리
            fabric_reference_path: 소재 참조 이미지 경로
            product_name: 제품명
            fabric: 패브릭 종류
            output_subdir: 출력 서브디렉토리 (지정하지 않으면 기본 output_dir 사용)

        Returns:
            각도별 생성된 모델링 이미지 경로 딕셔너리
        """
        logger.info(f"실제 사진에서 모델링 이미지 생성 시작: {product_name} - {fabric}")

        # 실제 제품 사진들 수집
        import glob
        photo_extensions = ['*.jpg', '*.jpeg', '*.png', '*.JPG', '*.JPEG', '*.PNG']
        real_photos = []
        for ext in photo_extensions:
            real_photos.extend(glob.glob(os.path.join(real_photo_dir, ext)))

        if not real_photos:
            raise ValueError(f"실제 제품 사진을 찾을 수 없습니다: {real_photo_dir}")

        logger.info(f"발견된 실제 제품 사진: {len(real_photos)}개")

        # 출력 디렉토리 설정
        if output_subdir:
            output_dir = os.path.join(self.output_dir, output_subdir)
            os.makedirs(output_dir, exist_ok=True)
        else:
            output_dir = self.output_dir

        # 각 표준 각도별로 모델링 이미지 생성
        modeling_images = {}

        for angle in self.STANDARD_ANGLES:
            try:
                logger.info(f"{angle} 각도 모델링 이미지 생성 중...")

                # 프롬프트 생성
                prompt = create_product_shot_prompt(
                    product_name=product_name,
                    fabric=fabric,
                    angle=angle,
                    background_type="studio_white",
                    has_fabric_reference=True
                )

                # Gemini API 호출 (wrapper 사용)
                # fabric_reference_path를 reference_image로
                # real_photos를 product_images로 전달 (최대 5개)
                target_photos = real_photos[:5]

                try:
                    generated_image_bytes = self.gemini.call_generate_image(
                        prompt=prompt,
                        reference_image=fabric_reference_path,
                        product_images=target_photos
                    )

                    # 생성된 이미지 저장
                    output_filename = f"단품_IMG_{product_name}_{fabric}_BG_{angle}.png"
                    output_path = os.path.join(output_dir, output_filename)

                    with open(output_path, "wb") as f:
                        f.write(generated_image_bytes)

                    modeling_images[angle] = output_path
                    logger.info(f"{angle} 각도 모델링 이미지 생성 완료: {output_path}")

                except Exception as e:
                    logger.error(f"{angle} 각도 모델링 이미지 생성 실패: {str(e)}")
                    # 실패 시 원본 저장 (Fallback)
                    if target_photos:
                        output_filename = f"단품_IMG_{product_name}_{fabric}_BG_{angle}.png"
                        output_path = os.path.join(output_dir, output_filename)
                        img = load_image(target_photos[0])
                        save_image(img, output_path)
                        modeling_images[angle] = output_path
                    continue

            except Exception as e:
                logger.error(f"{angle} 각도 처리 중 오류: {str(e)}")
                continue

        logger.info(f"모델링 이미지 생성 완료: {len(modeling_images)}개")
        return modeling_images

    def _get_rotation_angle(self, angle_name: str) -> int:
        """각도 이름에서 회전 각도 반환"""
        angle_map = {
            "front": 0,
            "half_side": 45,
            "side": 90,
            "back_side": 135,
            "back": 180
        }
        return angle_map.get(angle_name, 0)

    def _save_metadata(self):
        """메타데이터를 JSON 파일로 저장"""
        metadata_path = os.path.join(self.output_dir, "product_shot_metadata.json")
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)
        logger.debug(f"메타데이터 저장: {metadata_path}")

