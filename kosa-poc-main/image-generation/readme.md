# FURSYS 가구 이미지 생성 PoC

## 1. PoC 개요
"일관된" 품질 기준으로, "최소한"의 수작업으로, 가구 제품 이미지를 자동 생성하는 것을 목표로 합니다.

### 핵심 포인트
- **AI 기반 스타일링 컷 생성**: 실제 제품 사진을 활용한 공간 리뉴얼 이미지 자동 생성
- **다각도 단품 컷 제작**: 휴대폰 촬영 이미지 → 스튜디오 수준 제품 컷 변환
- **디테일 컷 자동화**: 상세 페이지용 재질/소재 강조 이미지 제작
- **다중 제품 조합 지원**: 엠버 소파, 테싯, 필즈 등 제품 조합 시뮬레이션
- **다중 소재 렌더링**: 동일 제품의 여러 소재(패브릭) 버전 자동 생성
- **Gemini 기반 이미지 생성**: 대규모 언어/비전 모델(Gemini 2.5 Flash, Imagen 3)의 이미지 이해 및 생성 능력 활용

## 2. PoC 시나리오

### 입력 데이터
- **레퍼런스 이미지**: 스타일링의 기반이 될 공간 이미지
- **제품 이미지**: 공간에 배치하거나 단품 컷으로 만들 실제 제품 사진

### 주요 기능 (Streamlit App)
1. **스타일링 컷 생성**: 레퍼런스 이미지와 제품 이미지를 업로드하여 새로운 공간 스타일링 이미지 생성
2. **단품 컷 생성**: 제품 사진을 업로드하고 해상도, 배경, 스타일 등을 설정하여 스튜디오 품질의 단품 컷 생성
3. **디테일 컷 생성**: 제품의 특정 부위(재질, 봉제선 등)를 강조한 클로즈업 이미지 생성

---

## 프로젝트 구조
```
image-generation/
├── app.py                     # Streamlit 웹 애플리케이션 진입점
├── common/
│   ├── gemini.py              # Gemini & Imagen API 클라이언트
│   ├── logger.py              # 로깅 설정
│   ├── prompt.py              # 프롬프트 템플릿
│   └── utils.py               # 유틸리티
├── services/
│   ├── styling_service.py      # 스타일링 컷 생성 서비스
│   ├── product_shot_service.py # 단품 컷 생성 서비스
│   ├── detail_service.py       # 디테일 컷 생성 서비스
│   ├── metadata_service.py     # 제품 메타데이터 추출 서비스
│   └── layout_page_service.py  # 레이아웃 페이지 생성 서비스
├── resource/                  # PoC 테스트용 샘플 리소스 (기능별 1개씩)
│   ├── 레퍼런스 이미지/
│   ├── 예제/
│   └── 제품사진/
├── Dockerfile
├── requirements.txt
└── readme.md
```

아래 디렉토리는 앱 실행 중 자동으로 생성되며 `.gitignore` 로 제외됩니다.

| 디렉토리 | 내용 |
|---|---|
| `input/` | 업로드된 이미지 사본 (`resource/` 에서 같은 이름을 찾으면 그쪽을 사용) |
| `output/` | 생성된 이미지 및 메타데이터 (`styling/`, `product_shots/`, `details/`, `metadata/`, `layout_pages/`) |
| `results/` | `billing.csv` — API 호출 비용 로깅 |

## 설치 및 실행

### 1. 환경 설정
```bash
# 가상환경 생성
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt
```

**주요 의존성**:
- `google-genai`: Gemini API 클라이언트
- `pillow`: 이미지 처리
- `streamlit`: 웹 애플리케이션 UI
- `python-dotenv`: `.env` 로드
- `colorlog`: 컬러 로깅

### 2. 환경 변수 설정
API 키는 **저장소 루트(`kosa-poc/`)의 `.env`** 를 `embedding`, `vlm-tagging` 앱과 공유합니다.
```bash
cp ../.env.example ../.env   # 최초 1회
```
```env
GEMINI_API_KEY=your-gemini-api-key-here
```
사용 모델은 `common/gemini.py` 의 `self.model` / `self.image_model` 에 지정되어 있습니다.

### 3. 실행 방법
Streamlit 웹 애플리케이션을 실행하여 모든 기능을 GUI 환경에서 사용할 수 있습니다.
```bash
streamlit run app.py
```

Docker 로 실행하려면 저장소 루트에서:
```bash
docker compose up --build image-generation   # http://localhost:8503
```
포트는 루트 `.env` 의 `IMAGE_GEN_PORT` 로 바꿀 수 있습니다.

실행 후 웹 브라우저에서 사이드바 메뉴를 통해 원하는 생성 기능을 선택하여 사용할 수 있습니다.

### 4. 출력 결과
생성된 이미지는 `output/` 디렉토리의 각 하위 폴더에 저장되며, 웹 UI에서도 바로 확인 및 다운로드가 가능합니다.

## 주요 기능 구현

### 1. 스타일링 컷 생성 (services/styling_service.py)
- **공간 분석**: Gemini 2.5 Flash를 활용해 레퍼런스 이미지의 공간 특성(크기, 조명, 색감)을 분석
- **이미지 생성**: Imagen 3 모델(imagen-3.0-generate-002)을 사용하여 실제 제품을 레퍼런스 공간에 자연스럽게 합성

### 2. 단품 컷 생성 (services/product_shot_service.py)
- **배경 제거**: Gemini Vision 모델을 활용하여 복잡한 배경을 정밀하게 제거 (프롬프트 기반)
- **스튜디오 컷**: 사용자가 설정한 조명, 배경, 스타일 옵션을 반영하여 고품질 단품 컷 생성

### 3. 디테일 컷 생성 (services/detail_service.py)
- **특징 강조**: 패브릭 질감, 봉제선 등 제품의 주요 특징을 부각시키는 클로즈업 샷 생성
- **자동화**: 프롬프트 엔지니어링을 통해 일관된 품질의 디테일 컷 확보

## 주의사항
- **API 사용량**: Google Cloud Vertex AI API 비용이 발생할 수 있습니다. `results/billing.csv`에 호출 내역이 기록됩니다.
- **입력 이미지**: 고해상도 이미지를 사용할수록 결과물의 품질이 향상됩니다.
- **모델 버전**:
  - 텍스트/멀티모달 분석: `gemini-2.5-flash`
  - 이미지 생성: `imagen-3.0-generate-002`

## 문제 해결
### API 오류
**오류 메시지**: `404 NOT_FOUND` 또는 `Gemini API 호출 실패`
- `.env` 파일의 설정(API Key, Project ID, Location)이 올바른지 확인하세요.
- 해당 프로젝트에서 Vertex AI API 및 Imagen API 사용 권한이 활성화되어 있는지 확인하세요.

### 이미지 생성 품질 저하
- 입력 이미지의 해상도나 조명 상태를 확인하세요.
- 프롬프트가 구체적일수록 더 좋은 결과를 얻을 수 있습니다. (현재 프롬프트는 `common/prompt.py`에서 관리됨)

---