import os
import streamlit as st
from PIL import Image
import pandas as pd

# 로컬 모듈 임포트
from utils import crop_image, draw_bounding_boxes
from vlm_client import VLMClient, load_api_key

# 1. 페이지 기본 설정 및 디자인
st.set_page_config(
    page_title="VLM 가구 다중 태깅 & XAI 앱",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 커스텀 CSS를 통한 UI 스타일 개선 (옵시디언 다크 테마 풍의 미려한 레이아웃)
st.markdown("""
<style>
    .sku-card {
        border: 1px solid #444;
        border-radius: 6px;
        padding: 8px;
        text-align: center;
        background-color: #1e1e1e;
        color: #ddd;
        font-size: 11px;
    }
    .main-header {
        font-family: sans-serif;
        color: #fff;
        border-bottom: 2px solid #007acc;
        padding-bottom: 8px;
        margin-bottom: 20px;
    }
    .stButton>button {
        width: 100%;
        background-color: #007acc;
        color: white;
        border-radius: 4px;
        border: none;
        padding: 10px;
        font-weight: bold;
    }
    .stButton>button:hover {
        background-color: #005999;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# 디렉토리 경로 상수 설정
IMAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")

# 2. 이미지 로드 헬퍼 함수
def load_sku_images():
    skus = {
        "sku_chair": {"file": "sku_chair.jpg", "name": "사무용 의자 (화이트)"},
        "sku_chair_black": {"file": "sku_chair_black.jpg", "name": "대조군 의자 (블랙)"},
        "sku_desk": {"file": "sku_desk.jpg", "name": "오피스 책상 (원목)"},
        "sku_lamp": {"file": "sku_lamp.jpg", "name": "데스크 스탠드 (블랙)"},
        "sku_cabinet": {"file": "sku_cabinet.jpg", "name": "이동식 서랍장 (화이트)"}
    }
    for sku_id, info in skus.items():
        path = os.path.join(IMAGE_DIR, info["file"])
        if os.path.exists(path):
            info["image"] = Image.open(path)
        else:
            # 대체용 빈 이미지
            info["image"] = Image.new("RGB", (100, 100), color="#333333")
    return skus

def load_lifestyle_image():
    path = os.path.join(IMAGE_DIR, "lifestyle_multi.jpg")
    if os.path.exists(path):
        return Image.open(path)
    return Image.new("RGB", (800, 600), color="#222222")

# 세션 상태 초기화
if "tagged_results" not in st.session_state:
    st.session_state.tagged_results = None
if "selected_object_idx" not in st.session_state:
    st.session_state.selected_object_idx = 0

# 메인 헤더
st.markdown("<h2 class='main-header'>VLM 기반 다중 객체 태깅 및 XAI 검증 App</h2>", unsafe_allow_html=True)

# 데이터 로드
sku_data = load_sku_images()
lifestyle_img = load_lifestyle_image()

# 3. [상단] 보유한 SKU 라이브러리 프리뷰
st.markdown("##### 보유한 SKU 라이브러리 (5종 카탈로그)")
sku_cols = st.columns(len(sku_data))
for idx, (sku_id, info) in enumerate(sku_data.items()):
    with sku_cols[idx]:
        st.image(info["image"], use_container_width=True)
        st.markdown(f"<div class='sku-card'><strong>{info['name']}</strong><br>{sku_id}.jpg</div>", unsafe_allow_html=True)

st.write("---")

# 4. [사이드바] 환경 설정
st.sidebar.markdown("###  시스템 환경 설정")

api_key = load_api_key()
if api_key:
    st.sidebar.success("Gemini API Key 탐지 완료 (.env)")
    mock_default = False
else:
    st.sidebar.warning("API Key가 없습니다. (Mock 모드 실행)")
    mock_default = True

use_mock = st.sidebar.checkbox("오프라인 Mock 모드 강제 적용", value=mock_default)
st.sidebar.info(
    "이 애플리케이션은 2단계 VLM 분석을 수행합니다.\n\n"
    "1단계: 연출샷에서 가구 객체 검출(Grounding)\n"
    "2단계: 각 검출 영역 크롭 후 5종 SKU 대조 루브릭 채점 및 매칭 기각(Reject) 판단"
)

# 5. [중앙 작업 영역] 단일 흐름 레이아웃으로 변경 (가독성 개선)

# 5-1. 타겟 연출샷 시각화 섹션
st.markdown("### 1. 분석 대상 연출샷")

# 분석 결과 유무에 따른 이미지 렌더링
if st.session_state.tagged_results is not None:
    detections = st.session_state.tagged_results["detections"]
    # 바운딩 박스가 렌더링된 이미지 생성
    rendered_image = draw_bounding_boxes(lifestyle_img, detections)
    st.image(rendered_image, use_container_width=True, caption="[분석 완료] 가구 객체가 검출된 연출샷")
else:
    st.image(lifestyle_img, use_container_width=True, caption="[대기 중] 분석을 진행할 원본 연출샷 (lifestyle_multi.jpg)")

st.write("---")

# 5-2. 분석 제어 섹션
st.markdown("### ⚡ AI 파이프라인 분석 제어")
trigger_btn = st.button("이미지 태깅 및 SKU 매칭 시작")

if trigger_btn:
    with st.spinner("VLM 파이프라인 가동 중... (1단계 객체 검출 ➡️ 2단계 SKU 루브릭 매칭 루프)"):
        # VLM 클라이언트 인스턴스화
        vlm = VLMClient(use_mock=use_mock)
        
        # [1단계] 객체 검출 (Grounding)
        detections = vlm.detect_objects(lifestyle_img)
        
        # [2단계] 객체별 크롭 및 SKU 루브릭 매칭
        processed_detections = []
        for idx, det in enumerate(detections):
            bbox = det["bbox"]
            label = det["label"]
            display_label = det.get("display_label", label)
            
            # 이미지 크롭 (ROI)
            cropped_patch = crop_image(lifestyle_img, bbox)
            
            # VLM 정밀 비교 & 루브릭 채점 호출
            eval_result = vlm.evaluate_matching(cropped_patch, sku_data)
            
            processed_detections.append({
                "id": idx + 1,
                "label": label,
                "display_label": display_label,
                "bbox": bbox,
                "cropped_patch": cropped_patch,
                "best_sku": eval_result["best_sku"],
                "score": eval_result["score"],
                "all_evaluations": eval_result["all_evaluations"]
            })
        
        st.session_state.tagged_results = {
            "detections": processed_detections
        }
        st.session_state.selected_object_idx = 0
        st.rerun()

st.write("---")

# 5-3. 결과 분석 리포트 섹션
if st.session_state.tagged_results is not None:
    results = st.session_state.tagged_results["detections"]
    
    st.markdown("### 2. 태깅 결과 및 XAI 분석 리포트")
    
    # 라디오 버튼 대신 정돈된 셀렉트박스로 개별 객체 선택 구현
    options = [f"#{det['id']} {det['display_label']} ➡️ [매칭 SKU: {det['best_sku']}] (스코어: {det['score']}점)" for det in results]
    selected_option = st.selectbox(
        "상세 분석을 조회할 가구 객체를 선택하세요:",
        options,
        index=st.session_state.selected_object_idx
    )
    
    # 선택된 인덱스 추적
    selected_idx = options.index(selected_option)
    st.session_state.selected_object_idx = selected_idx
    selected_det = results[selected_idx]
    
    st.write("---")
    st.markdown(f"####  #{selected_det['id']} 객체 설명 가능한 AI (XAI) 사유 리포트")
    
    # 가로 공간을 시원하게 활용하기 위해 크롭 썸네일(1)과 상세 분석 채점표(3)를 배치
    col_crop, col_details = st.columns([1, 3])
    with col_crop:
        st.image(selected_det["cropped_patch"], caption=f"크롭 영역 #{selected_det['id']}", use_container_width=True)
        
    with col_details:
        best_sku_id = selected_det["best_sku"]
        if best_sku_id != "Rejected":
            st.success(f"🏆 최종 판정: **{sku_data[best_sku_id]['name']}** 와 일치함 (점수: {selected_det['score']}점)")
        else:
            st.error("🏆 최종 판정: **기각 (Rejected)** - 일치하는 SKU 없음")
            
        # 5개 SKU에 대한 세부 평가 데이터셋 구성
        eval_list = []
        for sku_id, ev in selected_det["all_evaluations"].items():
            breakdown = ev.get("breakdown", {})
            eval_list.append({
                "SKU ID": sku_id,
                "명칭": sku_data[sku_id]["name"],
                "매칭 여부": "Matched" if ev["status"] == "Matched" else "Rejected",
                "형상 (30)": breakdown.get("structure", 0),
                "색상 (30)": breakdown.get("color", 0),
                "디테일 (20)": breakdown.get("detail", 0),
                "맥락 (20)": breakdown.get("context", 0),
                "총점 (100)": ev["total_score"],
                "XAI 기각 및 매칭 분석 사유": ev["xai_reason"]
            })
            
        df = pd.DataFrame(eval_list)
        
        # 테이블 형태로 점수 렌더링
        st.markdown("###### **1) 전체 SKU 대조 채점표**")
        st.dataframe(
            df.drop(columns=["XAI 기각 및 매칭 분석 사유"]),
            use_container_width=True,
            hide_index=True
        )
        
    # XAI 상세 서술 소견은 하단 전체 너비로 시원하게 나열
    st.markdown("###### **2) VLM이 분석한 상세 XAI 매칭/기각 소견**")
    for ev in eval_list:
        status_color = "🟢" if ev["매칭 여부"] == "Matched" else "🔴"
        with st.expander(f"{status_color} {ev['명칭']} ({ev['SKU ID']}) - 점수: {ev['총점 (100)']}점"):
            st.write(f"**상세 소견**: {ev['XAI 기각 및 매칭 분석 사유']}")
            
    st.write("---")
    
    # 리셋 버튼
    if st.button("🔄 결과 리셋"):
        st.session_state.tagged_results = None
        st.session_state.selected_object_idx = 0
        st.rerun()
else:
    st.info("💡 위의 '🚀 이미지 태깅 및 SKU 매칭 시작' 버튼을 누르면 VLM이 객체 검출 및 SKU 상세 대조 리포트를 생성합니다.")
