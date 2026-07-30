# KOSA PoC — 연출샷 가구 SKU 자동 매칭 파이프라인

연출샷(라이프스타일 이미지) 안에 놓인 가구가 **우리가 보유한 어떤 단품 SKU인지**를 자동으로 판정하는 PoC입니다.

하나의 문제를 두 단계로 나누어 검증합니다.

| 단계 | 모듈 | 역할 | 모델 |
|------|------|------|------|
| **1차** | [`embedding/`](./embedding) | 이미지 임베딩 → 코사인 유사도로 **빠르게 후보를 좁히는 스크리닝** | `gemini-embedding-2` |
| **2차** | [`vlm-tagging/`](./vlm-tagging) | 객체 검출 + 루브릭 채점으로 **왜 맞는지/틀린지 설명(XAI)** | `gemini-3.5-flash` |

---

## 1. 왜 두 단계인가

임베딩만으로는 "닮았다"는 것까지만 알 수 있고, **왜 닮았는지**를 설명하지 못합니다.
반대로 VLM만 쓰면 전체 SKU 카탈로그를 매번 다 비교해야 해서 비용과 지연이 커집니다.

그래서 두 모델의 성격을 역할로 나눴습니다.

```
연출샷 (lifestyle shot)
      │
      ▼
┌─────────────────────────────┐
│ Stage 1. 임베딩 스크리닝     │   embedding/
│  · 이미지 → 벡터(768~3072d) │
│  · 코사인 유사도 계산        │
└─────────────────────────────┘
      │
      ├── score ≥ 0.81 ────────────▶ 🟢 Match  (즉시 확정, VLM 호출 생략)
      │
      ├── 0.75 ≤ score < 0.81 ──┐
      │                          ▼
      │              ┌─────────────────────────────┐
      │              │ Stage 2. VLM 정밀 검증       │   vlm-tagging/
      │              │  · 가구 객체 검출 + 크롭      │
      │              │  · 5종 SKU 대조 루브릭 채점   │
      │              │  · XAI 소견 생성             │
      │              └─────────────────────────────┘
      │                          │
      │                          ├── total ≥ 70 ──▶ ✅ Matched
      │                          └── total <  70 ──▶ ❌ Rejected (사유 포함)
      │
      └── score < 0.75 ─────────────▶ 🔴 Reject (기각)
```

**핵심 아이디어**: 확실한 건 1차에서 싸게 끊고, 애매한 회색지대(0.75~0.80)만 2차 VLM과 HITL(사람 검수) 큐로 넘깁니다.

---

## 2. 모듈별 요약

### `embedding/` — 임베딩 유사도 검사 앱

두 장의 이미지를 올려 코사인 유사도를 측정하는 Streamlit 앱입니다.

- **MRL 차원 선택**: 768 / 1536 / 3072 차원 중 선택 (Matryoshka Representation Learning)
- **Grayscale 전처리 옵션**: 색상 차이로 인한 유사도 왜곡을 줄여 **형태 위주 매칭**을 강화
- **판정 구간**: `≥0.81` Match / `0.75~0.80` Uncertain(HITL) / `<0.75` Reject
- Docker / docker-compose 배포 구성 포함

### `vlm-tagging/` — 다중 객체 태깅 & XAI 검증 앱

연출샷 한 장에서 여러 가구를 한 번에 찾아 SKU와 대조하는 Streamlit 앱입니다.

- **1단계 Grounding**: 의자·책상·조명·서랍장의 바운딩 박스 검출 (`[ymin, xmin, ymax, xmax]`, 0~1000 정규화)
- **2단계 매칭**: 크롭 패치를 5종 기준 SKU와 대조, 4대 루브릭으로 100점 채점
  - 구조 30점 / 색상 30점 / 디테일 20점 / 맥락(오클루전) 20점 → **70점 이상 Matched**
- **XAI 리포트**: 항목별 기각 사유를 자연어 소견으로 제공
- **오프라인 Mock 모드**: API 키가 없으면 정적 데이터로 데모 동작
- 상세 문서는 [`vlm-tagging/README.md`](./vlm-tagging/README.md) 참고

#### 기준 SKU 카탈로그 (5종)

| SKU ID | 명칭 | 용도 |
|--------|------|------|
| `sku_chair` | 사무용 의자 (화이트) | 정답 후보 |
| `sku_chair_black` | 대조군 의자 (블랙) | **색상 오탐 검증용** — 형태는 같고 색만 다름 |
| `sku_desk` | 오피스 책상 (원목) | 정답 후보 |
| `sku_lamp` | 데스크 스탠드 (블랙) | 정답 후보 |
| `sku_cabinet` | 이동식 서랍장 (화이트) | **미존재 객체 기각 검증용** |

`sku_chair` ↔ `sku_chair_black` 쌍이 이 PoC의 핵심 난이도입니다. 형태는 거의 동일하고 색만 다르기 때문에, 임베딩 단독으로는 구분이 흔들리고 VLM의 색상 루브릭이 필요해집니다.

---

## 3. 실행 방법

### 사전 준비: `.env` 설정

API 키는 **리포지토리 루트의 `.env` 파일 한 곳**에서만 관리합니다. 두 앱이 이 파일을 공유합니다.

```bash
cp .env.example .env
```

생성된 `.env`를 열어 키를 채워 넣으세요.

```dotenv
GEMINI_API_KEY=발급받은-키를-여기에

EMBEDDING_PORT=8501
VLM_PORT=8502
```

키 발급은 [Google AI Studio](https://aistudio.google.com/apikey)에서 할 수 있습니다.

> `.env`는 `.gitignore`에 등록되어 있습니다. 절대 커밋하지 마세요.
> 키가 설정되지 않으면 `vlm-tagging`은 오프라인 Mock 모드로, `embedding`은 사이드바 직접 입력 모드로 동작합니다.

`.env`는 두 경로 모두에서 읽힙니다.

| 실행 방식 | 주입 경로 |
|-----------|-----------|
| Docker | `docker-compose.yml`의 `env_file` |
| 로컬 | `python-dotenv`가 상위 디렉토리까지 탐색해 자동 로드 |

### 방법 A — Docker (권장)

루트에서 한 번에 두 앱을 띄웁니다.

```bash
docker compose up --build
```

| 앱 | 주소 |
|----|------|
| Stage 1 — embedding | http://localhost:8501 |
| Stage 2 — vlm-tagging | http://localhost:8502 |

한쪽만 필요하다면 서비스명을 지정하세요.

```bash
docker compose up embedding      # Stage 1 만
docker compose up vlm-tagging    # Stage 2 만
docker compose down              # 종료
docker compose logs -f           # 로그 확인
```

포트를 바꾸려면 `.env`의 `EMBEDDING_PORT` / `VLM_PORT` 값을 수정하면 됩니다.

### 방법 B — 로컬 실행

두 앱은 의존성이 다르므로 가상환경을 각각 만듭니다.

```bash
# Stage 1
cd embedding
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py                        # http://localhost:8501
```

```bash
# Stage 2 (별도 터미널)
cd vlm-tagging
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py --server.port 8502     # http://localhost:8502
```

> 두 앱의 Streamlit 기본 포트가 모두 8501이라 동시에 띄울 때는 한쪽에 `--server.port`를 지정해야 합니다.

---

## 4. 측정 결과 (Stage 1)

직접 측정한 실측값입니다. 모두 Grayscale 전처리 적용 기준이며, 사용한 이미지는 [`embedding/result/`](./embedding/result)에 있습니다.

| 기준(A) | 비교(B) | 유사도 | 판정 |
|---------|---------|--------|------|
| `sku_chair` | `lifestyle_multi-crop` (크롭) | **0.8229** | 🟢 Match |
| `sku_chair` | `lifestyle_multi` (전체 연출샷) | 0.8183 | 🟢 Match |
| `sku_chair` | `lifestyle_multi-crop-cut` (일부 가림) | 0.8056 | 🟢 Match |
| `sku_chair_black` | `lifestyle_multi-crop` (크롭) | **0.7525** | 🟡 Uncertain |

**읽는 법**

- 동일 의자 계열은 크롭 여부·가림 정도와 무관하게 0.80대를 안정적으로 유지합니다.
- 결정적 케이스는 마지막 행입니다. **형태는 같고 색만 다른 블랙 의자**가 0.7525로 임계선 바로 위에 걸립니다. 즉 임베딩 단독으로는 오탐 위험이 있고, 이 구간이 정확히 Stage 2로 넘겨야 할 회색지대입니다.
- 실제로 Stage 2의 VLM은 이 케이스를 `structure 28 / color 5`로 채점해 **색상 불일치를 근거로 기각**합니다. 두 단계를 나눈 설계 근거가 이 한 줄에 있습니다.

---

## 5. 디렉토리 구조

```
kosa-poc/
├── README.md                  # 전체 파이프라인 개요
├── docker-compose.yml         # 두 앱 통합 실행
├── .env.example               # 환경 변수 템플릿 (커밋 대상)
├── .env                       # 실제 키 — git 제외, 직접 생성
├── .gitignore
│
├── embedding/                 # Stage 1 — 임베딩 유사도 스크리닝
│   ├── app.py
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── docker-compose.yml     # 단독 실행용 (루트 .env 참조)
│   └── result/                # 4장 측정에 사용한 이미지
│
├── vlm-tagging/               # Stage 2 — VLM 태깅 & XAI 검증
│   ├── app.py                 # Streamlit UI
│   ├── vlm_client.py          # Gemini 호출 + Mock 폴백
│   ├── utils.py               # 크롭 / 바운딩 박스 렌더링
│   ├── images/                # 기준 SKU 5종 + 연출샷 샘플
│   ├── requirements.txt
│   ├── Dockerfile
│   └── README.md
│
└── docs/                      # 산출 문서
    └── VLM 가구 태깅 솔루션.xlsx
```

---

## 6. 기술 스택

| 구분 | 사용 기술 |
|------|-----------|
| Language | Python 3.10+ |
| UI | Streamlit |
| AI SDK | `google-genai` |
| Model | `gemini-embedding-2` (Stage 1), `gemini-3.5-flash` (Stage 2) |
| 이미지 처리 | Pillow, OpenCV, NumPy |
| 연산 | SciPy (cosine distance), Pandas |
| 배포 | Docker, docker-compose |

---

## 7. 한계와 다음 단계

**현재 PoC의 한계**

- 두 단계가 아직 **UI 상 분리**되어 있습니다. Stage 1의 Uncertain 판정이 Stage 2로 자동 전달되지 않고, 사람이 이미지를 다시 올려야 합니다.
- SKU 카탈로그가 5종 하드코딩입니다. 실제 운영 규모에서는 벡터 DB 기반 Top-K 검색이 필요합니다.
- 임계값(0.81 / 0.75, 70점)이 소수 샘플 기준으로 잡혀 있어 통계적 검증이 되지 않았습니다.

**다음 단계 제안**

1. **파이프라인 통합** — 두 앱을 단일 서비스로 합치고, Stage 1 → Stage 2 자동 라우팅 구현
2. **벡터 DB 도입** — 전체 SKU 임베딩을 사전 색인하고 Top-K만 VLM에 전달해 호출 비용 절감
3. **임계값 재보정** — 라벨링된 평가셋으로 precision/recall 곡선을 그려 임계값 확정
4. **HITL 큐** — Uncertain 판정 건을 검수 대기열로 적재하고, 검수 결과를 임계값 재학습에 반영