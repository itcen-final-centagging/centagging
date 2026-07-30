# VLM 기반 다중 객체 태깅 및 XAI 검증 App

본 프로젝트는 최신 Google Gemini API(`gemini-3.5-flash`) 모델과 신형 `google-genai` SDK를 활용하여 연출샷 내 가구 객체를 자동으로 탐지하고, 보유 중인 단품 SKU 카탈로그와 정밀 대조 및 평가 점수를 내리는 설명 가능한 AI(XAI) 데모 애플리케이션입니다.

---

## 1. 주요 기능

1. **1단계: 가구 객체 검출 (Grounding)**
   * 입력된 복합 인테리어 연출샷에서 의자, 책상, 조명 등의 가구 위치를 파악하여 박스 좌표를 획득합니다.
2. **2단계: SKU 매칭 및 XAI 평가**
   * 검출된 영역을 크롭하여 5가지 기준 SKU 이미지와 직접 일치 여부를 평가합니다.
   * 기하 형상, 색상, 디테일 힌트, 맥락적 오클루전 등 4대 루브릭 기준으로 채점하고 기각(Reject) 여부와 사유 소견을 제공합니다.
3. **Streamlit 웹 UI**
   * 분석 진행 상황에 대한 실시간 디버그 로깅, 전체 채점표 데이터프레임 시각화, 항목별 상세 XAI 서술형 리포트를 아코디언 컴포넌트로 탐색할 수 있습니다.

---

## 🛠️ 기술 스택

* **Frontend/UI**: Streamlit
* **AI SDK**: google-genai (구글 차세대 공식 SDK)
* **Model**: gemini-3.5-flash
* **Language**: Python 3.10+
* **Dependencies**: pillow, pandas, opencv-python, numpy

---

## 🚀 실행 방법

### 1. 가상환경 구성 및 패키지 설치
```bash
# 가상환경 생성 및 활성화
python3 -m venv .venv
source .venv/bin/activate

# 의존성 패키지 설치
pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Gemini API 키 설정 (보안 주의)

API 키는 **리포지토리 루트의 `.env` 파일**에서 관리합니다. Stage 1(`embedding/`)과 공용입니다.

```bash
# 리포지토리 루트에서 실행
cp .env.example .env
```

생성된 `.env`에 키를 채워 넣으세요.

```dotenv
GEMINI_API_KEY=발급받은-키를-여기에
```

* 로컬 실행 시 `python-dotenv`가 상위 디렉토리까지 탐색해 자동 로드하므로, `vlm-tagging/`에서 실행해도 루트 `.env`를 찾습니다.
* 도커 실행 시에는 compose의 `env_file`로 주입됩니다.
* 일회성으로 쓰려면 환경 변수를 직접 지정해도 됩니다: `export GEMINI_API_KEY="..."`
* `.env`는 `.gitignore`로 제외됩니다. 절대 커밋하지 마세요.
* *키가 없을 경우, 기본 정의된 오프라인 Mock 데이터 모드로 시뮬레이션 동작합니다.*

### 3. 애플리케이션 실행
```bash
streamlit run app.py
```
실행 후 터미널에 노출되는 웹 주소(`http://localhost:8501`)로 접속하십시오.
