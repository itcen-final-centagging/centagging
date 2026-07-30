import streamlit as st
import os
from PIL import Image
import json
import textwrap

from common.logger import init_logger
from common.gemini import Gemini
from common.utils import find_resource_path
from common.styles import APP_STYLES

from services.metadata_service import MetadataService
from services.product_shot_service import ProductShotService
from services.styling_service import StylingService
from services.detail_service import DetailService
from services.layout_page_service import LayoutPageService

# 로거 및 서비스 초기화
logger = init_logger()

@st.cache_resource
def get_gemini_client():
    return Gemini()

@st.cache_resource
def get_product_shot_service():
    return ProductShotService(get_gemini_client())

@st.cache_resource
def get_styling_service():
    return StylingService(get_gemini_client())

@st.cache_resource
def get_detail_service():
    return DetailService(get_gemini_client())

@st.cache_resource
def get_metadata_service():
    return MetadataService(get_gemini_client())

@st.cache_resource
def get_layout_page_service():
    return LayoutPageService(get_gemini_client())

# Define custom progress HTML (moved here to be reusable)
CUSTOM_PROGRESS_HTML = textwrap.dedent("""
    <div class="progress-container">
        <div class="progress-title">🔄 생성 중입니다...</div>
        <div class="progress-bar-wrapper">
            <div class="progress-bar-inner"></div>
        </div>
        <div class="progress-text">AI가 이미지를 생성하고 있습니다... 잠시만 기다려주세요.</div>
    </div>
""")


def styling_cut_page():
    st.header("🎨 스타일링 컷 생성")
    st.markdown("레퍼런스 이미지와 제품 정보를 기반으로 AI가 새로운 공간을 스타일링합니다.")

    # 생성 상태 초기화
    if 'styling_generating' not in st.session_state:
        st.session_state.styling_generating = False

    col_input, col_result = st.columns([1, 1])

    with col_input:
        st.subheader("📤 입력")

        # 제품 이미지 업로드 (사용자 추가)
        product_images = st.file_uploader(
            "제품 이미지 업로드 (관련 제품)",
            type=["jpg", "jpeg", "png"],
            accept_multiple_files=True,
            disabled=st.session_state.styling_generating
        )

        product_images_loaded = False
        if product_images:
            try:
                st.write(f"업로드된 제품 이미지: {len(product_images)}장")
                # 5개씩 행으로 나누어 표시
                for row_start in range(0, len(product_images), 5):
                    row_images = product_images[row_start:row_start + 5]
                    p_preview_cols = st.columns(len(row_images))
                    for idx, img_file in enumerate(row_images):
                        with p_preview_cols[idx]:
                            st.image(Image.open(img_file), caption=img_file.name, width='stretch')
                product_images_loaded = True
            except Exception as e:
                st.error(f"제품 이미지 로드 중 오류: {e}")

        # 레퍼런스 이미지 업로드
        reference_images = st.file_uploader(
            "레퍼런스 이미지 업로드",
            type=["jpg", "jpeg", "png"],
            accept_multiple_files=True,
            disabled=st.session_state.styling_generating
        )

        reference_images_loaded = False
        if reference_images:
            try:
                st.write(f"업로드된 레퍼런스 이미지: {len(reference_images)}장")
                # 5개씩 행으로 나누어 표시
                for row_start in range(0, len(reference_images), 5):
                    row_images = reference_images[row_start:row_start + 5]
                    preview_cols = st.columns(len(row_images))
                    for idx, img_file in enumerate(row_images):
                        with preview_cols[idx]:
                            st.image(Image.open(img_file), caption=img_file.name, width='stretch')
                reference_images_loaded = True
            except Exception as e:
                st.error(f"레퍼런스 이미지 로드 중 오류: {e}")

        st.markdown("---")
        st.subheader("⚙️ 추가 설정")

        # 레퍼런스 이미지 활용 방식
        st.write("**레퍼런스 이미지 활용 방식** (중복 선택 가능)")
        generation_mode_bg_style = st.checkbox(
            "배경/스타일 분리 - 레퍼런스에서 배경/조명/스타일만 추출, 제품은 새롭게 배치",
            value=False,
            disabled=st.session_state.styling_generating,
            key="mode_bg_style"
        )
        generation_mode_product_replace = st.checkbox(
            "제품 교체 - 레퍼런스의 제품 부분을 새 제품으로 정확히 대체",
            value=False,
            disabled=st.session_state.styling_generating,
            key="mode_product_replace"
        )
        generation_mode_style_transfer = st.checkbox(
            "스타일 전이 - 레퍼런스 스타일 참고하되 제품 특성 강조",
            value=True,
            disabled=st.session_state.styling_generating,
            key="mode_style_transfer"
        )
        generation_mode_new_composition = st.checkbox(
            "완전히 새로운 구도 - 레퍼런스는 참고만, 제품에 맞는 새로운 구도",
            value=False,
            disabled=st.session_state.styling_generating,
            key="mode_new_composition"
        )

        # 비율 설정
        aspect_ratio = st.selectbox(
            "이미지 비율",
            options=["1:1", "4:3", "3:4", "16:9", "9:16"],
            index=0,
            disabled=st.session_state.styling_generating
        )

        # 생성 개수 설정
        num_outputs = st.slider(
            "생성 이미지 개수",
            min_value=1,
            max_value=4,
            value=1,
            disabled=st.session_state.styling_generating
        )

        # 모든 이미지가 로드되었는지 확인
        all_images_loaded = product_images_loaded and reference_images_loaded

        generate_button = st.button(
            "🚀 스타일링 컷 생성",
            type="primary",
            width='stretch',
            disabled=st.session_state.styling_generating or not all_images_loaded
        )
        
        validation_placeholder = st.empty()
        generation_status_placeholder = st.empty() # New placeholder

    with col_result:
        st.subheader("📥 결과")

        # Removed from here: if st.session_state.styling_generating: st.info(...) st.progress(...)

        # 결과 이미지 저장을 위한 세션 상태 초기화
        if 'generated_styling_images' not in st.session_state:
            st.session_state.generated_styling_images = []

        if generate_button:
            # 입력값 검증
            if not reference_images:
                validation_placeholder.error("⚠️ 레퍼런스 이미지를 업로드해주세요.")
            elif not product_images:
                validation_placeholder.error("⚠️ 제품 이미지를 업로드해주세요.")
            else:
                # 생성 상태 활성화
                st.session_state.styling_generating = True
                st.rerun()

        if st.session_state.styling_generating and not generate_button:
            # Display generation messages in the placeholder in col_input
            generation_status_placeholder.markdown(CUSTOM_PROGRESS_HTML, unsafe_allow_html=True)

            try:
                input_dir = "input/styling"
                os.makedirs(input_dir, exist_ok=True)
                
                # 1. 레퍼런스 이미지 저장
                ref_image_paths = []
                for img_file in reference_images:
                    # 먼저 resource 폴더에서 찾기
                    actual_path = find_resource_path(img_file.name)
                    if actual_path:
                        ref_image_paths.append(actual_path)
                        continue
                        
                    # 못 찾으면 저장
                    path = os.path.join(input_dir, f"ref_{img_file.name}")
                    with open(path, "wb") as f:
                        f.write(img_file.getbuffer())
                    ref_image_paths.append(os.path.abspath(path))

                # 2. 제품 조합 설정
                # 사용자가 업로드한 제품들로 하나의 커스텀 조합 생성
                custom_products = []
                for img_file in product_images:
                    actual_path = find_resource_path(img_file.name)
                    if actual_path:
                        path = actual_path
                    else:
                        # 못 찾으면 저장
                        path = os.path.join(input_dir, f"prod_{img_file.name}")
                        with open(path, "wb") as f:
                            f.write(img_file.getbuffer())
                        path = os.path.abspath(path)

                    custom_products.append({
                        "name": os.path.splitext(img_file.name)[0],
                        "image_path": path,
                        "placement": "공간에 어울리는 위치",
                        "size": "적절한 크기"
                    })
                # 단일 조합을 리스트에 담아 전달
                product_combinations = [custom_products]

                # 생성 모드 수집
                generation_modes = []
                if generation_mode_bg_style:
                    generation_modes.append("bg_style_separation")
                if generation_mode_product_replace:
                    generation_modes.append("product_replacement")
                if generation_mode_style_transfer:
                    generation_modes.append("style_transfer")
                if generation_mode_new_composition:
                    generation_modes.append("new_composition")

                # 기본값: 아무것도 선택 안 했으면 style_transfer
                if not generation_modes:
                    generation_modes = ["style_transfer"]

                # 3. 서비스 호출
                styling_service = get_styling_service()
                generated_images = styling_service.generate_multiple_combinations(
                    reference_images=ref_image_paths,
                    product_combinations=product_combinations,
                    aspect_ratio=aspect_ratio,
                    num_outputs=num_outputs,
                    generation_modes=generation_modes
                )
                
                # 결과 세션에 저장
                st.session_state.generated_styling_images = generated_images
                st.session_state.current_styling_index = 0

            except Exception as e:
                st.error(f"생성 중 오류 발생: {e}")
                logger.error(f"스타일링 컷 생성 실패: {e}")
            finally:
                # 생성 완료 후 상태 초기화
                st.session_state.styling_generating = False
                generation_status_placeholder.empty() # Clear placeholder on completion/error
                st.rerun()

        # 생성된 이미지 보여주기 (세션 상태 기반)
        if st.session_state.generated_styling_images:
            generated_images = st.session_state.generated_styling_images
            
            # 현재 보고 있는 이미지 인덱스 초기화
            if 'current_styling_index' not in st.session_state:
                st.session_state.current_styling_index = 0

            current_idx = st.session_state.current_styling_index

            # 인덱스가 범위를 벗어나면 초기화
            if current_idx >= len(generated_images):
                st.session_state.current_styling_index = 0
                current_idx = 0

            current_image_path = generated_images[current_idx]

            # 이미지 네비게이션
            col_prev, col_image, col_next = st.columns([1, 10, 1])

            with col_prev:
                if st.button("◀", key="prev_styling", width='stretch'):
                    st.session_state.current_styling_index = (current_idx - 1) % len(generated_images)
                    st.rerun()

            with col_image:
                st.markdown(f"### 스타일링 컷 {current_idx + 1}")
                if os.path.exists(current_image_path):
                    st.image(Image.open(current_image_path), width='stretch')

                    # 다운로드 버튼
                    with open(current_image_path, "rb") as file:
                        st.download_button(
                            label=f"💾 스타일링 컷 {current_idx + 1} 다운로드",
                            data=file,
                            file_name=os.path.basename(current_image_path),
                            mime="image/png",
                            width='stretch'
                        )
                else:
                    st.warning("이미지를 찾을 수 없습니다.")

            with col_next:
                if st.button("▶", key="next_styling", width='stretch'):
                    st.session_state.current_styling_index = (current_idx + 1) % len(generated_images)
                    st.rerun()

            # 진행 표시
            st.progress((current_idx + 1) / len(generated_images), text=f"{current_idx + 1} / {len(generated_images)}")


def product_shot_page():
    st.header("🖼️ 단품 컷 생성")
    st.markdown("제품의 실제 사진을 기반으로 5가지 각도(정면, 반측면(45도), 측면(90도), 후측면(135도), 후면(180도))의 고품질 단품 컷을 생성합니다.")

    # 생성 상태 초기화
    if 'product_generating' not in st.session_state:
        st.session_state.product_generating = False

    col_input, col_result = st.columns([1, 1])

    with col_input:
        st.subheader("📤 입력")

        # 제품 이미지 업로드
        source_images = st.file_uploader(
            "제품 사진 업로드",
            type=["jpg", "jpeg", "png"],
            accept_multiple_files=True,
            disabled=st.session_state.product_generating
        )

        source_images_loaded = False
        if source_images:
            try:
                st.write(f"업로드된 제품 사진: {len(source_images)}장")
                # 5개씩 행으로 나누어 표시
                for row_start in range(0, len(source_images), 5):
                    row_images = source_images[row_start:row_start + 5]
                    preview_cols = st.columns(len(row_images))
                    for idx, img_file in enumerate(row_images):
                        with preview_cols[idx]:
                            st.image(Image.open(img_file), caption=img_file.name, width='stretch')
                source_images_loaded = True
            except Exception as e:
                st.error(f"제품 이미지 로드 중 오류: {e}")

        # 소재 레퍼런스 이미지 업로드
        fabric_reference = st.file_uploader(
            "소재 레퍼런스 이미지 업로드 (선택사항)",
            type=["jpg", "jpeg", "png"],
            key="fabric_reference",
            disabled=st.session_state.product_generating
        )
        if fabric_reference:
            st.image(Image.open(fabric_reference), caption="소재 레퍼런스", width=200)

        st.markdown("---")
        st.subheader("⚙️ 추가 설정")

        # 비율 설정
        aspect_ratio = st.selectbox(
            "이미지 비율",
            options=["1:1", "4:3", "3:4", "16:9", "9:16"],
            index=0,
            disabled=st.session_state.product_generating,
            key="product_shot_aspect_ratio"
        )

        # 해상도 선택
        resolution_options = {
            "1K (1024x1024)": "1K",
            "2K (2048x2048)": "2K",
            "4K (4096x4096)": "4K",
        }
        selected_resolution_label = st.selectbox(
            "해상도 선택",
            options=list(resolution_options.keys()),
            index=1,  # Default to 2K
            disabled=st.session_state.product_generating
        )

        if selected_resolution_label == "직접 입력":
            selected_resolution = st.text_input("해상도 입력 (예: 2K)", "2K", disabled=st.session_state.product_generating)
        else:
            selected_resolution = resolution_options[selected_resolution_label]

        # 배경 타입 선택
        background_type_options = {
            "스튜디오 화이트": "studio_white",
            "스튜디오 그레이": "studio_gray",
            "순수 화이트": "pure_white",
            "그라데이션 배경": "gradient_background",
            "직접 입력": "custom"
        }
        selected_background_label = st.selectbox(
            "배경 타입 선택",
            options=list(background_type_options.keys()),
            index=0,  # Default to studio_white
            disabled=st.session_state.product_generating
        )

        if selected_background_label == "직접 입력":
            selected_background_type = st.text_input("배경 타입 입력 (예: studio_white)", "studio_white", disabled=st.session_state.product_generating)
        else:
            selected_background_type = background_type_options[selected_background_label]

        # 렌더링 스타일 선택
        rendering_style_options = [
            "포토리얼리스틱 (Photorealistic)",
            "스튜디오 렌더링 (Studio Render)",
            "소프트 라이팅 (Soft Lighting)",
            "하이 콘트라스트 (High Contrast)",
            "직접 입력"
        ]
        selected_rendering_style_label = st.selectbox(
            "렌더링 스타일 선택",
            options=rendering_style_options,
            index=0,  # Default to Photorealistic
            disabled=st.session_state.product_generating
        )

        if selected_rendering_style_label == "직접 입력":
            selected_rendering_style = st.text_input("렌더링 스타일 입력", "포토리얼리스틱 (Photorealistic)", disabled=st.session_state.product_generating)
        else:
            selected_rendering_style = selected_rendering_style_label

        # 조명 스타일 선택
        lighting_style_options = [
            "3점 조명법",
            "2점 조명법",
            "소프트 라이트",
            "자연광 스타일",
            "드라마틱 라이팅",
            "직접 입력"
        ]
        selected_lighting_style_label = st.selectbox(
            "조명 스타일 선택",
            options=lighting_style_options,
            index=0,  # Default to 3점 조명법
            disabled=st.session_state.product_generating
        )

        if selected_lighting_style_label == "직접 입력":
            selected_lighting_style = st.text_input("조명 스타일 입력", "3점 조명법", disabled=st.session_state.product_generating)
        else:
            selected_lighting_style = selected_lighting_style_label

        generate_button = st.button(
            "🚀 단품 컷 생성",
            type="primary",
            width='stretch',
            disabled=st.session_state.product_generating or not source_images_loaded
        )
        
        validation_placeholder = st.empty()
        generation_status_placeholder = st.empty()


    with col_result:
        st.subheader("📥 결과")

        # Removed from here: if st.session_state.product_generating: st.info(...) st.progress(...)

        # 결과 이미지 저장을 위한 세션 상태 초기화
        if 'generated_product_images' not in st.session_state:
            st.session_state.generated_product_images = {}

        if generate_button:
            if not source_images:
                validation_placeholder.error("⚠️ 제품 실제 사진을 업로드해주세요.")
            else:
                # 생성 상태 활성화
                st.session_state.product_generating = True
                st.rerun()

        if st.session_state.product_generating and not generate_button:
            generation_status_placeholder.markdown(CUSTOM_PROGRESS_HTML, unsafe_allow_html=True)

            try:
                with st.spinner("단품 컷 생성 중..."):
                    input_dir = "input/product"
                    os.makedirs(input_dir, exist_ok=True)
                    
                    source_image_paths = []
                    for img_file in source_images:
                        # 먼저 resource 폴더에서 찾기
                        actual_path = find_resource_path(img_file.name)
                        if actual_path:
                            source_image_paths.append(actual_path)
                            continue
                            
                        # 못 찾으면 저장
                        path = os.path.join(input_dir, img_file.name)
                        with open(path, "wb") as f:
                            f.write(img_file.getbuffer())
                        source_image_paths.append(os.path.abspath(path))

                    # 소재 레퍼런스 이미지 처리
                    fabric_reference_path = None
                    if fabric_reference:
                        # 먼저 resource 폴더에서 찾기
                        actual_path = find_resource_path(fabric_reference.name)
                        if actual_path:
                            fabric_reference_path = actual_path
                        else:
                            # 못 찾으면 저장
                            fabric_ref_path = os.path.join(input_dir, f"fabric_{fabric_reference.name}")
                            with open(fabric_ref_path, "wb") as f:
                                f.write(fabric_reference.getbuffer())
                            fabric_reference_path = os.path.abspath(fabric_ref_path)

                    product_shot_service = get_product_shot_service()
                    angle_images = product_shot_service.generate_all_angles(
                        source_images=source_image_paths,
                        product_name="product",  # 기본값 사용
                        fabric="fabric",  # 기본값 사용
                        fabric_reference_path=fabric_reference_path,
                        aspect_ratio=aspect_ratio,
                        resolution=selected_resolution,
                        file_format="PNG",  # 고정값
                        background_type=selected_background_type,
                        rendering_style=selected_rendering_style,
                        lighting_style=selected_lighting_style
                    )
                    
                    # 결과 세션에 저장
                    st.session_state.generated_product_images = angle_images
                    st.session_state.current_angle_index = 0

            except Exception as e:
                st.error(f"생성 중 오류 발생: {e}")
                logger.error(f"단품 컷 생성 실패: {e}")
            finally:
                # 생성 완료 후 상태 초기화
                st.session_state.product_generating = False
                generation_status_placeholder.empty()
                st.rerun()

        # 생성된 이미지 보여주기 (세션 상태 기반)
        if st.session_state.generated_product_images:
            angle_images = st.session_state.generated_product_images
            
            angles = ["front", "half_side", "side", "back_side", "back"]
            angle_names = {
                "front": "정면 (0도)",
                "half_side": "반측면 (45도)",
                "side": "측면 (90도)",
                "back_side": "후측면 (135도)",
                "back": "후면 (180도)"
            }

            # 현재 보고 있는 이미지 인덱스 초기화
            if 'current_angle_index' not in st.session_state:
                st.session_state.current_angle_index = 0

            current_idx = st.session_state.current_angle_index
            current_angle = angles[current_idx]
            current_image = angle_images.get(current_angle)

            # 이미지 네비게이션
            col_prev, col_image, col_next = st.columns([1, 10, 1])

            with col_prev:
                if st.button("◀", key="prev_angle", width='stretch'):
                    st.session_state.current_angle_index = (current_idx - 1) % len(angles)
                    st.rerun()

            with col_image:
                st.markdown(f"### {angle_names[current_angle]}")
                if current_image and os.path.exists(current_image):
                    st.image(Image.open(current_image), width='stretch')

                    # 다운로드 버튼
                    with open(current_image, "rb") as file:
                        st.download_button(
                            label=f"💾 {angle_names[current_angle]} 다운로드",
                            data=file,
                            file_name=os.path.basename(current_image),
                            mime="image/png",
                            width='stretch'
                        )
                else:
                    st.warning("이미지를 찾을 수 없습니다.")

            with col_next:
                if st.button("▶", key="next_angle", width='stretch'):
                    st.session_state.current_angle_index = (current_idx + 1) % len(angles)
                    st.rerun()

            # 진행 표시
            st.progress((current_idx + 1) / len(angles), text=f"{current_idx + 1} / {len(angles)}")


def metadata_extract_page():
    st.header("📊 메타데이터 추출")
    st.markdown("제품 이미지에서 카테고리, 속성, 특징 등의 메타데이터를 추출합니다.")

    # 생성 상태 초기화
    if 'metadata_extracting' not in st.session_state:
        st.session_state.metadata_extracting = False

    col_input, col_result = st.columns([1, 1])

    with col_input:
        st.subheader("📤 입력")

        # 제품 이미지 업로드
        product_image = st.file_uploader(
            "제품 이미지 업로드",
            type=["jpg", "jpeg", "png"],
            key="metadata_source",
            disabled=st.session_state.metadata_extracting
        )

        product_image_loaded = False
        if product_image:
            try:
                st.image(Image.open(product_image), caption="제품 이미지", width="stretch")
                product_image_loaded = True
            except Exception as e:
                st.error(f"제품 이미지 로드 중 오류: {e}")

        extract_button = st.button(
            "🚀 메타데이터 추출",
            type="primary",
            width='stretch',
            disabled=st.session_state.metadata_extracting or not product_image_loaded
        )

        validation_placeholder = st.empty()
        extraction_status_placeholder = st.empty()

        # 덮어쓰기 확인 다이얼로그
        if 'metadata_file_exists' in st.session_state and st.session_state.metadata_file_exists:
            validation_placeholder.warning(f"⚠️ '{st.session_state.metadata_filename}.json' 파일이 이미 존재합니다.")
            col_yes, col_no = st.columns(2)
            with col_yes:
                if st.button("덮어쓰기", type="primary", use_container_width=True, key="overwrite_yes"):
                    st.session_state.metadata_file_exists = False
                    st.session_state.metadata_extracting = True
                    st.rerun()
            with col_no:
                if st.button("취소", use_container_width=True, key="overwrite_no"):
                    st.session_state.metadata_file_exists = False
                    st.rerun()

    with col_result:
        st.subheader("📥 결과")

        # 결과 저장을 위한 세션 상태 초기화
        if 'extracted_metadata' not in st.session_state:
            st.session_state.extracted_metadata = None

        if extract_button:
            if not product_image:
                validation_placeholder.error("⚠️ 제품 이미지를 업로드해주세요.")
            else:
                # 동일 파일명 체크
                filename = os.path.splitext(product_image.name)[0]
                output_json_path = os.path.join("output/metadata", f"{filename}.json")

                if os.path.exists(output_json_path):
                    # 덮어쓰기 여부 확인
                    st.session_state.metadata_file_exists = True
                    st.session_state.metadata_filename = filename
                else:
                    st.session_state.metadata_extracting = True
                st.rerun()

        if st.session_state.metadata_extracting and not extract_button:
            progress_html = textwrap.dedent("""
                <div class="progress-container">
                    <div class="progress-title">🔄 메타데이터 추출 중입니다...</div>
                    <div class="progress-bar-wrapper">
                        <div class="progress-bar-inner"></div>
                    </div>
                    <div class="progress-text">AI가 제품을 분석하고 있습니다... 잠시만 기다려주세요.</div>
                </div>
            """)
            extraction_status_placeholder.markdown(progress_html, unsafe_allow_html=True)

            try:
                input_dir = "input/metadata"
                os.makedirs(input_dir, exist_ok=True)

                # 이미지 저장
                actual_path = find_resource_path(product_image.name)
                if actual_path:
                    image_path = actual_path
                else:
                    image_path = os.path.join(input_dir, product_image.name)
                    with open(image_path, "wb") as f:
                        f.write(product_image.getbuffer())
                    image_path = os.path.abspath(image_path)

                # 메타데이터 추출
                metadata_service = get_metadata_service()
                metadata = metadata_service.extract_metadata(image_path)

                # Add filename and image_path to metadata
                metadata['filename'] = product_image.name
                metadata['image_path'] = image_path # Add the actual path of the input image

                # 결과 세션에 저장
                st.session_state.extracted_metadata = metadata

            except Exception as e:
                st.error(f"메타데이터 추출 중 오류 발생: {e}")
                logger.error(f"메타데이터 추출 실패: {e}")
            finally:
                st.session_state.metadata_extracting = False
                extraction_status_placeholder.empty()
                st.rerun()

        # 추출된 메타데이터 보여주기
        if st.session_state.extracted_metadata:
            metadata = st.session_state.extracted_metadata

            st.markdown("#### 📝 추출된 메타데이터")

            # 데이터 준비
            category = metadata.get('category', 'N/A')
            sub_category = metadata.get('sub_category', 'N/A')
            key_features = metadata.get('key_features', [])
            attributes = metadata.get('attributes', {})
            description = metadata.get('description', {})
            if isinstance(description, dict):
                desc_text = description.get('description', 'N/A')
            else:
                desc_text = description

            # HTML 테이블 생성
            html = '<table class="metadata-table">'
            html += f"<tr><th>파일 이름</th><td>{metadata.get('filename', 'N/A')}</td></tr>"
            html += f"<tr><th>이미지 경로</th><td>{metadata.get('image_path', 'N/A')}</td></tr>"
            html += f"<tr><th>카테고리</th><td>{category}</td></tr>"
            html += f"<tr><th>서브 카테고리</th><td>{sub_category}</td></tr>"

            if key_features:
                features_html = "<ul>" + "".join([f"<li>{item}</li>" for item in key_features]) + "</ul>"
                html += f"<tr><th>주요 특징</th><td>{features_html}</td></tr>"

            if attributes:
                for key, value in attributes.items():
                    if isinstance(value, dict):
                        val = value.get('value', 'N/A')
                        reason = value.get('reason', '')

                        # reason이 있으면 tooltip으로 표시
                        if reason:
                            val_html = f'<span class="tooltip">{val}<span class="tooltiptext">{reason}</span></span>'
                        else:
                            val_html = val
                    else:
                        val_html = value

                    html += f"<tr><th>{key}</th><td>{val_html}</td></tr>"

            html += f"<tr><th>제품 설명</th><td>{desc_text}</td></tr>"
            html += "</table>"

            st.markdown(html, unsafe_allow_html=True)

            st.markdown("---")

            # JSON 다운로드
            import json as json_module
            metadata_json = json_module.dumps(metadata, ensure_ascii=False, indent=2)
            st.download_button(
                label="💾 메타데이터 JSON 다운로드",
                data=metadata_json,
                file_name=f"metadata_{metadata.get('filename', 'product')}.json",
                mime="application/json",
                type="primary",
                use_container_width=True
            )


def detail_cut_page():
    st.header("🔍 디테일 컷 생성")
    st.markdown("제품의 특정 부분을 강조하는 디테일 컷을 생성합니다.")

    # 생성 상태 초기화
    if 'detail_generating' not in st.session_state:
        st.session_state.detail_generating = False

    col_input, col_result = st.columns([1, 1])

    with col_input:
        st.subheader("📤 입력")

        # 대표 이미지 업로드
        source_image = st.file_uploader(
            "대표 이미지 업로드",
            type=["jpg", "jpeg", "png"],
            key="detail_source",
            disabled=st.session_state.detail_generating
        )

        source_image_loaded = False
        if source_image:
            try:
                st.image(Image.open(source_image), caption="대표 이미지", width="stretch")
                source_image_loaded = True
            except Exception as e:
                st.error(f"대표 이미지 로드 중 오류: {e}")

        # 디테일 촬영 레퍼런스 이미지 업로드
        detail_reference = st.file_uploader(
            "디테일 촬영 레퍼런스 이미지 업로드 (선택사항)",
            type=["jpg", "jpeg", "png"],
            key="detail_reference",
            disabled=st.session_state.detail_generating,
            help="이런 스타일로 디테일을 촬영하고 싶다는 예시 이미지"
        )
        if detail_reference:
            st.image(Image.open(detail_reference), caption="디테일 레퍼런스", width=200)

        st.markdown("---")
        st.subheader("⚙️ 추가 설정")

        # 강조할 특징 텍스트 입력
        features_text = st.text_area(
            "강조할 특징 입력",
            value="",
            help="예: 패브릭 질감, 쿠션감, 봉제선, 다리 디자인, 팔걸이, 등받이",
            height=100,
            disabled=st.session_state.detail_generating
        )

        generate_button = st.button(
            "🚀 디테일 컷 생성",
            type="primary",
            width='stretch',
            disabled=st.session_state.detail_generating or not source_image_loaded
        )
        
        validation_placeholder = st.empty()
        generation_status_placeholder = st.empty() # New placeholder

    with col_result:
        st.subheader("📥 결과")

        # Removed from here: if st.session_state.detail_generating: st.info(...) st.progress(...)

        # 결과 이미지 저장을 위한 세션 상태 초기화
        if 'generated_detail_images' not in st.session_state:
            st.session_state.generated_detail_images = {}

        if generate_button:
            # 입력값 검증
            if not source_image:
                validation_placeholder.error("⚠️ 대표 이미지를 업로드해주세요.")
            else:
                # 특징 텍스트가 비어있는 경우 메타데이터 확인
                features_list = [f.strip() for f in features_text.split(",") if f.strip()]
                
                if not features_list:
                    filename_no_ext = os.path.splitext(source_image.name)[0]
                    metadata_path = os.path.join("output/metadata", f"{filename_no_ext}.json")
                    
                    if os.path.exists(metadata_path):
                        try:
                            with open(metadata_path, 'r', encoding='utf-8') as f:
                                metadata = json.load(f)
                            
                            extracted_features = DetailService.extract_detail_features_from_metadata(metadata)
                            if extracted_features:
                                features_list = extracted_features
                                validation_placeholder.success(f"✅ 메타데이터에서 특징을 불러왔습니다: {', '.join(features_list)}")
                            else:
                                validation_placeholder.warning("⚠️ 메타데이터를 찾았으나 특징 정보를 추출할 수 없습니다. 기본 특징(패브릭 질감)으로 진행합니다.")
                                features_list = ["패브릭 질감"]
                        except Exception as e:
                            validation_placeholder.error(f"⚠️ 메타데이터 로드 중 오류 발생: {e}")
                            features_list = ["패브릭 질감"] # Fallback
                    else:
                        validation_placeholder.warning(f"⚠️ 메타데이터 파일({filename_no_ext}.json)을 찾을 수 없습니다. 기본 특징(패브릭 질감)으로 진행합니다.")
                        features_list = ["패브릭 질감"] # Fallback

                # 생성 상태 활성화 (features_list가 준비되었으므로)
                st.session_state.detail_features_list = features_list # Store for use in processing block
                st.session_state.detail_generating = True
                st.rerun()

        if st.session_state.detail_generating and not generate_button:
            generation_status_placeholder.markdown(CUSTOM_PROGRESS_HTML, unsafe_allow_html=True)

            try:
                with st.spinner("디테일 컷 생성 중..."):
                    input_dir = "input/detail"
                    os.makedirs(input_dir, exist_ok=True)
                    
                    # 먼저 resource 폴더에서 찾기
                    actual_path = find_resource_path(source_image.name)
                    if actual_path:
                        source_image_path = actual_path
                    else:
                        # 못 찾으면 저장
                        source_image_path = os.path.join(input_dir, source_image.name)
                        with open(source_image_path, "wb") as f:
                            f.write(source_image.getbuffer())
                        source_image_path = os.path.abspath(source_image_path)

                    # 디테일 레퍼런스 이미지 처리
                    detail_reference_path = None
                    if detail_reference:
                        # 먼저 resource 폴더에서 찾기
                        actual_path = find_resource_path(detail_reference.name)
                        if actual_path:
                            detail_reference_path = actual_path
                        else:
                            # 못 찾으면 저장
                            detail_ref_path = os.path.join(input_dir, f"detail_ref_{detail_reference.name}")
                            with open(detail_ref_path, "wb") as f:
                                f.write(detail_reference.getbuffer())
                            detail_reference_path = os.path.abspath(detail_ref_path)

                    # 특징 리스트 가져오기 (세션에서)
                    features_list = st.session_state.get('detail_features_list', [])
                    # 만약 세션에 없다면(새로고침 등 이슈), 다시 텍스트에서 시도하거나 기본값
                    if not features_list:
                         features_list = [f.strip() for f in features_text.split(",") if f.strip()]
                         if not features_list:
                             features_list = ["패브릭 질감"] # Safety fallback

                    detail_service = get_detail_service()
                    detail_images = detail_service.generate_all_detail_shots(
                        source_image_path=source_image_path,
                        product_name="product",  # 기본값 사용
                        fabric="fabric",  # 기본값 사용
                        features=features_list,
                        reference_image_path=detail_reference_path
                    )
                    
                    # 결과 세션에 저장
                    st.session_state.generated_detail_images = detail_images
                    st.session_state.current_detail_index = 0

            except Exception as e:
                st.error(f"생성 중 오류 발생: {e}")
                logger.error(f"디테일 컷 생성 실패: {e}")
            finally:
                # 생성 완료 후 상태 초기화
                st.session_state.detail_generating = False
                generation_status_placeholder.empty()
                st.rerun()

        # 생성된 이미지 보여주기 (세션 상태 기반)
        if st.session_state.generated_detail_images:
            detail_images = st.session_state.generated_detail_images
            
            # dictionary를 list로 변환
            detail_items = list(detail_images.items())

            # 현재 보고 있는 이미지 인덱스 초기화
            if 'current_detail_index' not in st.session_state:
                st.session_state.current_detail_index = 0

            current_idx = st.session_state.current_detail_index

            # 인덱스가 범위를 벗어나면 초기화
            if current_idx >= len(detail_items):
                st.session_state.current_detail_index = 0
                current_idx = 0

            current_feature, current_image_path = detail_items[current_idx]

            # 이미지 네비게이션
            col_prev, col_image, col_next = st.columns([1, 10, 1])

            with col_prev:
                if st.button("◀", key="prev_detail", width='stretch'):
                    st.session_state.current_detail_index = (current_idx - 1) % len(detail_items)
                    st.rerun()

            with col_image:
                st.markdown(f"### {current_feature}")
                if os.path.exists(current_image_path):
                    st.image(Image.open(current_image_path), width='stretch')

                    # 다운로드 버튼
                    with open(current_image_path, "rb") as file:
                        st.download_button(
                            label=f"💾 {current_feature} 다운로드",
                            data=file,
                            file_name=os.path.basename(current_image_path),
                            mime="image/png",
                            width='stretch'
                        )
                else:
                    st.warning("이미지를 찾을 수 없습니다.")

            with col_next:
                if st.button("▶", key="next_detail", width='stretch'):
                    st.session_state.current_detail_index = (current_idx + 1) % len(detail_items)
                    st.rerun()

            # 진행 표시
            st.progress((current_idx + 1) / len(detail_items), text=f"{current_idx + 1} / {len(detail_items)}")


def layout_based_detail_page():
    st.header("📄 레이아웃 기반 상세페이지 생성")
    st.markdown("제품 이미지와 레이아웃 레퍼런스를 기반으로 상세페이지를 생성합니다.  \n제품에 대한 메타데이터가 없는 경우, 자동으로 생성을 제안합니다.")

    # 생성 상태 초기화
    if 'layout_page_generating' not in st.session_state:
        st.session_state.layout_page_generating = False
    
    # 메타데이터 및 이미지 경로 세션 상태 초기화
    if 'layout_metadata' not in st.session_state:
        st.session_state.layout_metadata = None
    if 'layout_product_image_path' not in st.session_state:
        st.session_state.layout_product_image_path = None

    col_input, col_result = st.columns([1, 1])

    with col_input:
        st.subheader("📤 입력")

        # 1. 제품 이미지 업로드 (메타데이터 조회/생성용)
        product_image_file = st.file_uploader(
            "제품 이미지 업로드",
            type=["jpg", "jpeg", "png"],
            key="layout_page_product_image",
            disabled=st.session_state.layout_page_generating
        )
        
        # 제품 이미지 처리 로직
        metadata_ready = False
        product_image_loaded = False

        if product_image_file:
            # 이미지 저장 (항상 최신 파일로 덮어쓰기 or 유지)
            input_dir = "input/layout_pages"
            os.makedirs(input_dir, exist_ok=True)

            # 파일명 기반 경로 설정
            image_filename = product_image_file.name
            current_image_path = os.path.abspath(os.path.join(input_dir, image_filename))

            # 이미지가 세션에 없거나, 새로 업로드된 경우 저장
            # Streamlit 특성상 매번 실행되므로, 파일이 없으면 저장
            if not os.path.exists(current_image_path):
                with open(current_image_path, "wb") as f:
                    f.write(product_image_file.getbuffer())

            st.session_state.layout_product_image_path = current_image_path

            try:
                st.image(Image.open(current_image_path), caption="제품 이미지", width=200)
                product_image_loaded = True
            except Exception as e:
                st.error(f"제품 이미지 로드 중 오류: {e}")

            # 메타데이터 확인
            filename_no_ext = os.path.splitext(image_filename)[0]
            metadata_json_path = os.path.join("output/metadata", f"{filename_no_ext}.json")
            
            # 이미 생성된 메타데이터가 세션에 있다면 그것을 사용 (방금 생성한 경우 등)
            if st.session_state.layout_metadata and st.session_state.layout_metadata.get('filename') == image_filename:
                metadata_ready = True
                st.success("✅ 메타데이터가 준비되었습니다.")
                with st.expander("메타데이터 확인"):
                    st.json(st.session_state.layout_metadata)
            
            # 세션엔 없지만 파일로 존재하는 경우 로드
            elif os.path.exists(metadata_json_path):
                try:
                    with open(metadata_json_path, 'r', encoding='utf-8') as f:
                        loaded_metadata = json.load(f)
                    
                    # 중요: 메타데이터의 image_path를 현재 업로드된 경로로 갱신
                    loaded_metadata['image_path'] = current_image_path
                    loaded_metadata['filename'] = image_filename # 파일명도 확실히
                    
                    st.session_state.layout_metadata = loaded_metadata
                    metadata_ready = True
                    st.success("✅ 기존 메타데이터를 불러왔습니다.")
                    with st.expander("메타데이터 확인"):
                        st.json(loaded_metadata)
                except Exception as e:
                    st.error(f"메타데이터 로드 실패: {e}")
            
            # 메타데이터가 없는 경우 -> 생성 제안
            else:
                st.warning("⚠️ 이 제품의 메타데이터가 없습니다.")
                st.info("상세페이지 생성을 위해 메타데이터가 필요합니다.")
                
                if st.button("✨ 메타데이터 생성하기", type="primary", key="generate_metadata_btn"):
                    try:
                        with st.spinner("메타데이터 생성 중..."):
                            metadata_service = get_metadata_service()
                            # extract_metadata는 내부적으로 파일 저장도 수행함
                            new_metadata = metadata_service.extract_metadata(current_image_path)
                            
                            # image_path 확인 및 보정
                            new_metadata['image_path'] = current_image_path
                            
                            st.session_state.layout_metadata = new_metadata
                            metadata_ready = True
                            st.rerun()
                    except Exception as e:
                        st.error(f"메타데이터 생성 실패: {e}")
                        logger.error(f"Layout page metadata generation failed: {e}")

        # 2. 레이아웃 레퍼런스 이미지 업로드
        layout_reference_image = st.file_uploader(
            "레이아웃 레퍼런스 이미지 업로드",
            type=["jpg", "jpeg", "png"],
            key="layout_page_reference_image",
            disabled=st.session_state.layout_page_generating
        )

        layout_reference_loaded = False
        if layout_reference_image:
            try:
                st.image(Image.open(layout_reference_image), caption="레이아웃 레퍼런스", width=200)
                layout_reference_loaded = True
            except Exception as e:
                st.error(f"레이아웃 레퍼런스 이미지 로드 중 오류: {e}")

        st.markdown("---")
        st.subheader("⚙️ 추가 설정")

        # 비율 설정
        aspect_ratio = st.selectbox(
            "이미지 비율",
            options=["1:1", "4:3", "3:4", "16:9", "9:16"],
            index=0,
            disabled=st.session_state.layout_page_generating,
            key="layout_page_aspect_ratio"
        )

        # 생성 개수 설정
        num_outputs = st.slider(
            "생성 이미지 개수",
            min_value=1,
            max_value=4,
            value=1,
            disabled=st.session_state.layout_page_generating
        )

        # 생성 버튼 활성화 조건: 메타데이터 준비됨 AND 이미지 모두 로드됨
        all_images_loaded = product_image_loaded and layout_reference_loaded
        generate_disabled = st.session_state.layout_page_generating or not (metadata_ready and all_images_loaded)
        
        generate_button = st.button(
            "🚀 상세페이지 생성",
            type="primary",
            width='stretch',
            disabled=generate_disabled
        )
        
        validation_placeholder = st.empty()
        generation_status_placeholder = st.empty()

    with col_result:
        st.subheader("📥 결과")

        # 결과 저장을 위한 세션 상태 초기화
        if 'generated_layout_pages' not in st.session_state:
            st.session_state.generated_layout_pages = []

        if generate_button:
            # 입력값 검증 (버튼이 활성화되었다면 이미 통과한 것이지만 안전장치)
            if not st.session_state.layout_metadata:
                validation_placeholder.error("⚠️ 메타데이터가 없습니다.")
            elif not layout_reference_image:
                validation_placeholder.error("⚠️ 레이아웃 레퍼런스 이미지를 업로드해주세요.")
            else:
                # 생성 상태 활성화
                st.session_state.layout_page_generating = True
                st.rerun()

        if st.session_state.layout_page_generating and not generate_button:
            generation_status_placeholder.markdown(CUSTOM_PROGRESS_HTML, unsafe_allow_html=True)

            try:
                with st.spinner("상세페이지 생성 중..."):
                    input_dir = "input/layout_pages"
                    os.makedirs(input_dir, exist_ok=True)
                    
                    # 레이아웃 레퍼런스 이미지 저장
                    # find_resource_path 사용 고려했으나, 사용자가 직접 올린 파일 우선
                    layout_image_path = os.path.join(input_dir, layout_reference_image.name)
                    with open(layout_image_path, "wb") as f:
                        f.write(layout_reference_image.getbuffer())
                    layout_image_path = os.path.abspath(layout_image_path)
                    
                    # 서비스 호출
                    # 메타데이터에는 이미 image_path가 올바르게 설정되어 있음
                    layout_service = get_layout_page_service()
                    generated_images = layout_service.generate_layout_page(
                        metadata=st.session_state.layout_metadata,
                        layout_image_path=layout_image_path,
                        num_outputs=num_outputs,
                        aspect_ratio=aspect_ratio
                    )
                    
                    # 결과 세션에 저장
                    st.session_state.generated_layout_pages = generated_images
                    st.session_state.current_layout_page_index = 0

            except Exception as e:
                st.error(f"상세페이지 생성 중 오류 발생: {e}")
                logger.error(f"레이아웃 기반 상세페이지 생성 실패: {e}")
            finally:
                # 생성 완료 후 상태 초기화
                st.session_state.layout_page_generating = False
                generation_status_placeholder.empty()
                st.rerun()

        # 생성된 이미지 보여주기 (세션 상태 기반)
        if st.session_state.generated_layout_pages:
            generated_images = st.session_state.generated_layout_pages
            
            # 현재 보고 있는 이미지 인덱스 초기화
            if 'current_layout_page_index' not in st.session_state:
                st.session_state.current_layout_page_index = 0

            current_idx = st.session_state.current_layout_page_index

            # 인덱스가 범위를 벗어나면 초기화
            if current_idx >= len(generated_images):
                st.session_state.current_layout_page_index = 0
                current_idx = 0

            current_image_path = generated_images[current_idx]

            # 이미지 네비게이션
            col_prev, col_image, col_next = st.columns([1, 10, 1])

            with col_prev:
                if st.button("◀", key="prev_layout_page", width='stretch'):
                    st.session_state.current_layout_page_index = (current_idx - 1) % len(generated_images)
                    st.rerun()

            with col_image:
                st.markdown(f"### 상세페이지 {current_idx + 1}")
                if os.path.exists(current_image_path):
                    st.image(Image.open(current_image_path), width='stretch')

                    # 다운로드 버튼
                    with open(current_image_path, "rb") as file:
                        st.download_button(
                            label=f"💾 상세페이지 {current_idx + 1} 다운로드",
                            data=file,
                            file_name=os.path.basename(current_image_path),
                            mime="image/png",
                            width='stretch'
                        )
                else:
                    st.warning("이미지를 찾을 수 없습니다.")

            with col_next:
                if st.button("▶", key="next_layout_page", width='stretch'):
                    st.session_state.current_layout_page_index = (current_idx + 1) % len(generated_images)
                    st.rerun()

            # 진행 표시
            st.progress((current_idx + 1) / len(generated_images), text=f"{current_idx + 1} / {len(generated_images)}")


def main():
    """Streamlit App Main"""
    st.set_page_config(
        page_title="FURSYS AI 이미지 생성",
        page_icon="🛋️",
        layout="wide"
    )

    # 커스텀 CSS 적용
    st.markdown(APP_STYLES, unsafe_allow_html=True)

    st.sidebar.title("FURSYS PoC")
    st.sidebar.markdown("---")

    page_options = {
                "📊 메타데이터 추출": metadata_extract_page,
                "🎨 스타일링 컷 생성": styling_cut_page,
                "🖼️ 단품 컷 생성": product_shot_page,
                "🔍 디테일 컷 생성": detail_cut_page,
                "📄 레이아웃 기반 상세페이지 생성": layout_based_detail_page
            }

    selected_page = st.sidebar.radio("메뉴를 선택하세요", list(page_options.keys()))
    st.sidebar.markdown("---")

    # Copyright 정보
    st.sidebar.markdown("""
    <div style='text-align: center; font-size: 1rem; color: #888; padding: 0.5rem 0;'>
        Copyright © 2026<br>
        ITCEN CLOIT<br>
        All rights reserved.
    </div>
    """, unsafe_allow_html=True)
        
    page_options[selected_page]() # 선택된 페이지 함수 실행
        
        
if __name__ == "__main__":
    import sys
    from streamlit.web import cli as stcli

    if st.runtime.exists():
        main()
    else:
        sys.argv = ["streamlit", "run", sys.argv[0]]
        sys.exit(stcli.main())
        