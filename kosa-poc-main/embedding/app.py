import streamlit as st
import os
import io
import numpy as np
from PIL import Image as PILImage
from scipy.spatial.distance import cosine
from dotenv import load_dotenv, find_dotenv

# .env 로드 (현재 디렉토리에서 상위로 거슬러 올라가며 탐색)
# 도커 실행 시에는 compose 의 env_file 로 이미 주입되므로 override 하지 않습니다.
load_dotenv(find_dotenv(usecwd=True), override=False)

# Google GenAI 임포트 예외 처리 (설치 여부 확인)
try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

# 페이지 레이아웃 설정
st.set_page_config(
    page_title="Gemini 이미지 유사도 검사 PoC",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 세션 상태 초기화
if "similarity_score" not in st.session_state:
    st.session_state.similarity_score = None
if "embedding_a" not in st.session_state:
    st.session_state.embedding_a = None
if "embedding_b" not in st.session_state:
    st.session_state.embedding_b = None
if "file_a_name" not in st.session_state:
    st.session_state.file_a_name = None
if "file_b_name" not in st.session_state:
    st.session_state.file_b_name = None
if "output_dim_prev" not in st.session_state:
    st.session_state.output_dim_prev = 3072
if "apply_grayscale_prev" not in st.session_state:
    st.session_state.apply_grayscale_prev = True

# 사이드바 설정 (API 및 임베딩 옵션)
st.sidebar.title("🛠️ API 및 임베딩 옵션")

# API Key 상태 표시 (보안상 앞 4자리와 뒷 4자리만 출력)
api_key = os.environ.get("GEMINI_API_KEY", "")
if not api_key:
    api_key_input = st.sidebar.text_input("GEMINI_API_KEY 입력", type="password")
    if api_key_input:
        os.environ["GEMINI_API_KEY"] = api_key_input
        st.sidebar.success("API Key가 설정되었습니다.")
else:
    masked_key = api_key[:4] + "..." + api_key[-4:] if len(api_key) > 8 else "Loaded"
    st.sidebar.success(f" API Key 감지됨 ({masked_key})")

# 임베딩 차원 선택 (Matryoshka Representation Learning)
output_dim = st.sidebar.selectbox(
    "임베딩 벡터 차원 (Output Dimensions)", 
    [768, 1536, 3072], 
    index=2,
    help="gemini-embedding-2는 MRL을 지원하여 원하는 차원으로 변경 가능합니다. 기본값은 3072입니다."
)

# 차원 수 설정이 변경되었을 때 캐시 초기화
if output_dim != st.session_state.output_dim_prev:
    st.session_state.embedding_a = None
    st.session_state.embedding_b = None
    st.session_state.file_a_name = None
    st.session_state.file_b_name = None
    st.session_state.similarity_score = None
    st.session_state.output_dim_prev = output_dim

st.sidebar.markdown("---")
st.sidebar.subheader(" 임베딩 전처리 옵션")
apply_grayscale = st.sidebar.checkbox(
    "Grayscale(흑백) 변환 적용", 
    value=True, 
    help="색상 차이로 인한 유사도 왜곡을 방지하기 위해 이미지를 흑백으로 변환한 뒤 임베딩을 추출합니다. (대표 SKU 매핑 최적화 전략)"
)

# 흑백 변환 옵션이 변경되었을 때 캐시 초기화
if apply_grayscale != st.session_state.apply_grayscale_prev:
    st.session_state.embedding_a = None
    st.session_state.embedding_b = None
    st.session_state.file_a_name = None
    st.session_state.file_b_name = None
    st.session_state.similarity_score = None
    st.session_state.apply_grayscale_prev = apply_grayscale

# 메인 UI
st.title("Gemini 이미지 임베딩 유사도 검사 PoC")
st.markdown("""
이 애플리케이션은 **Gemini Embedding 2 API**를 기반으로 2개 이미지 간의 수학적 유사도(Cosine Similarity)를 측정합니다.
* **대표 SKU 이미지 (기준점)**와 **연출샷 크롭 이미지 (비교 대상)**를 업로드하여 성능을 직접 검증할 수 있습니다.
""")

if not GEMINI_AVAILABLE:
    st.error("`google-genai` 패키지가 설치되지 않았거나 로드할 수 없습니다. requirements.txt를 설치해주세요.")
    st.stop()

# 이미지 파일 바이트 변환 함수
def convert_to_bytes(pil_img, format="JPEG"):
    buf = io.BytesIO()
    pil_img.save(buf, format=format)
    return buf.getvalue()

# 임베딩 추출 함수
def get_embedding(image_bytes, dimension=3072):
    try:
        client = genai.Client()
        response = client.models.embed_content(
            model="gemini-embedding-2",
            contents=[
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type="image/jpeg",
                )
            ],
            config=types.EmbedContentConfig(
                output_dimensionality=dimension
            )
        )
        return response.embeddings[0].values
    except Exception as e:
        st.error(f"Gemini API 호출 중 에러가 발생했습니다: {str(e)}")
        return None

# 레이아웃 분할 (업로드 영역)
col1, col2 = st.columns(2)

# 화면 출력용 가로/세로 규격 정의 (1:1 비율 매칭용)
DISPLAY_SIZE = (300, 300)

with col1:
    st.subheader("Image A (표준 SKU 또는 기준 이미지)")
    file_a = st.file_uploader("대표 SKU 이미지를 업로드하세요", type=["jpg", "jpeg", "png"], key="uploader_a")
    
    if file_a:
        pil_a = PILImage.open(file_a)
        
        # 회전 정보 정규화 및 RGB 변환
        if pil_a.mode != "RGB":
            pil_a = pil_a.convert("RGB")
            
        # 화면 출력을 위해 동일 비율(300x300)로 강제 리사이징하여 높이 일치화
        pil_a_disp = pil_a.resize(DISPLAY_SIZE, PILImage.Resampling.LANCZOS)
        st.image(pil_a_disp, caption="Image A 원본 (300x300 크기 맞춤)", width=DISPLAY_SIZE[0])
        
        if apply_grayscale:
            gray_a = pil_a.convert("L")
            gray_a_disp = gray_a.resize(DISPLAY_SIZE, PILImage.Resampling.LANCZOS)
            st.image(gray_a_disp, caption="Image A 흑백 변환 (300x300 크기 맞춤)", width=DISPLAY_SIZE[0])
            img_a_processed = gray_a
        else:
            img_a_processed = pil_a
            
        # 파일이 변경되었거나 임베딩이 없으면 임베딩 추출 (실제 추출 및 API 송신은 원본 비율로 진행)
        if st.session_state.file_a_name != file_a.name or st.session_state.embedding_a is None:
            with st.spinner("Image A 임베딩 추출 중..."):
                bytes_a = convert_to_bytes(img_a_processed)
                emb_a = get_embedding(bytes_a, output_dim)
                if emb_a is not None:
                    st.session_state.embedding_a = emb_a
                    st.session_state.file_a_name = file_a.name
                    st.session_state.similarity_score = None
                    st.rerun()
        
        # 개별 임베딩 정보 바로 출력
        if st.session_state.embedding_a is not None:
            st.success("Image A 임베딩 완료!")
            with st.expander("Image A 임베딩 벡터 확인"):
                st.write(f"**차원**: {len(st.session_state.embedding_a)}차원")
                st.write(st.session_state.embedding_a)
    else:
        st.session_state.embedding_a = None
        st.session_state.file_a_name = None
        st.session_state.similarity_score = None

with col2:
    st.subheader("Image B (연출샷 크롭 또는 비교 이미지)")
    file_b = st.file_uploader("비교할 연출샷 크롭 이미지를 업로드하세요", type=["jpg", "jpeg", "png"], key="uploader_b")
    
    if file_b:
        pil_b = PILImage.open(file_b)
        
        if pil_b.mode != "RGB":
            pil_b = pil_b.convert("RGB")
            
        # 화면 출력을 위해 동일 비율(300x300)로 강제 리사이징하여 높이 일치화
        pil_b_disp = pil_b.resize(DISPLAY_SIZE, PILImage.Resampling.LANCZOS)
        st.image(pil_b_disp, caption="Image B 원본 (300x300 크기 맞춤)", width=DISPLAY_SIZE[0])
        
        if apply_grayscale:
            gray_b = pil_b.convert("L")
            gray_b_disp = gray_b.resize(DISPLAY_SIZE, PILImage.Resampling.LANCZOS)
            st.image(gray_b_disp, caption="Image B 흑백 변환 (300x300 크기 맞춤)", width=DISPLAY_SIZE[0])
            img_b_processed = gray_b
        else:
            img_b_processed = pil_b
            
        # 파일이 변경되었거나 임베딩이 없으면 임베딩 추출 (실제 추출 및 API 송신은 원본 비율로 진행)
        if st.session_state.file_b_name != file_b.name or st.session_state.embedding_b is None:
            with st.spinner("Image B 임베딩 추출 중..."):
                bytes_b = convert_to_bytes(img_b_processed)
                emb_b = get_embedding(bytes_b, output_dim)
                if emb_b is not None:
                    st.session_state.embedding_b = emb_b
                    st.session_state.file_b_name = file_b.name
                    st.session_state.similarity_score = None
                    st.rerun()
        
        # 개별 임베딩 정보 바로 출력
        if st.session_state.embedding_b is not None:
            st.success("✅ Image B 임베딩 완료!")
            with st.expander("🔍 Image B 임베딩 벡터 확인"):
                st.write(f"**차원**: {len(st.session_state.embedding_b)}차원")
                st.write(st.session_state.embedding_b)
    else:
        st.session_state.embedding_b = None
        st.session_state.file_b_name = None
        st.session_state.similarity_score = None

# 유사도 연산 및 실행 버튼
st.markdown("---")
st.subheader("유사도 연산 실행")

if st.session_state.embedding_a is not None and st.session_state.embedding_b is not None:
    if st.button("이미지 유사도 분석 시작", type="primary", use_container_width=True):
        emb_a = st.session_state.embedding_a
        emb_b = st.session_state.embedding_b
        
        # 코사인 유사도 연산 (1 - Cosine Distance)
        similarity = 1 - cosine(emb_a, emb_b)
        st.session_state.similarity_score = float(similarity)
        st.success("유사도 연산 완료!")
else:
    if not file_a or not file_b:
        st.warning("분석을 시작하려면 Image A와 Image B를 모두 업로드해 주세요.")
    else:
        st.info("임베딩을 추출하는 중입니다...")

# 결과 시각화
if st.session_state.similarity_score is not None:
    score = st.session_state.similarity_score
    st.markdown("---")
    st.subheader("분석 결과 리포트")
    
    # 결과 요약 카드형 레이아웃
    res_col1, res_col2 = st.columns([1, 2])
    
    with res_col1:
        st.metric(label="코사인 유사도 (Cosine Similarity)", value=f"{score:.4f}")
        
        # 매칭 판정 로직
        if score >= 0.81:
            st.markdown('<div style="background-color:#d4edda; color:#155724; padding:15px; border-radius:5px; font-weight:bold; text-align:center;">'
                        '🟢 Match (동일 가구 확정)'
                        '</div>', unsafe_allow_html=True)
            st.markdown("유사도가 매우 높습니다. 2단계 VLM 검증 없이 1단계만으로도 **동일 제품**으로 분류될 신뢰 수준입니다.")
        elif score >= 0.75:
            st.markdown('<div style="background-color:#fff3cd; color:#856404; padding:15px; border-radius:5px; font-weight:bold; text-align:center;">'
                        '🟡 Uncertain (판정 보류 / HITL 대상)'
                        '</div>', unsafe_allow_html=True)
            st.markdown("형태적 유사성은 인지되나, 가림/각도 왜곡 등으로 스코어가 완화되었습니다. **수동 검증(HITL) 큐** 전송 및 VLM 2차 판정이 권장됩니다.")
        else:
            st.markdown('<div style="background-color:#f8d7da; color:#721c24; padding:15px; border-radius:5px; font-weight:bold; text-align:center;">'
                        '🔴 Reject (불일치)'
                        '</div>', unsafe_allow_html=True)
            st.markdown("유사도가 기준치 미만입니다. **이종 가구**이거나 인지가 불가할 정도의 극단적 왜곡이 발생한 상태입니다.")
            
    with res_col2:
        st.write("📈 유사도 범위 차트")
        st.progress(score)
        
        st.info("""
        **판정 기준 참고**
        * **0.81 이상**: 동일 SKU 매칭 확정 구간.
        * **0.75 ~ 0.80**: 가림(Occlusion 30%~50%) 또는 앵글 왜곡으로 인해 유사도가 하락한 보류 구간.
        * **0.75 미만**: 기각 구간.
        """)
