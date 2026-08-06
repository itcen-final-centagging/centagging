# Centagging

AI 기반 인테리어 연출 이미지 가구 자동 태깅 솔루션
## 0. 기술 스택

- 백엔드: FastAPI
- 프론트엔드: Streamlit
- 데이터베이스: PostgreSQL + pgvector
- AI: Gemini VLM 및 이미지 임베딩
- 팀 공통 실행 환경: Docker Compose

## 1. 사전 준비

팀 공통 실행에는 아래 도구가 필요합니다.

- Git
- Docker Desktop
- 본인의 Gemini API 키

Anaconda/Miniconda는 Docker 실행에 필수는 아니지만, 로컬에서 Python 코드 품질 검사나 디버깅을 할 때 사용합니다. Docker 컨테이너의 Python 버전은 3.10.20으로 고정되어 있습니다.

Docker Desktop을 설치한 뒤 실행 상태인지 먼저 확인합니다.

```powershell
docker --version
docker compose version
```

## 2. Repository Clone

작업할 위치에서 저장소를 복제합니다.

```powershell
git clone https://github.com/itcen-final-centagging/centagging-backend.git
cd centagging-backend
```

`kosa-poc-main/`은 기존 참고 샘플 코드입니다. 프로젝트 구현을 위해 직접 수정하지 않습니다.

## 3. 환경 변수 설정

환경 변수 예시 파일을 복사해 개인용 `.env` 파일을 만듭니다.

```powershell
Copy-Item .env.example .env
```

`.env`에서 Gemini API 키를 입력합니다.

```env
GEMINI_API_KEY=your-gemini-api-key-here
GEMINI_VLM_MODEL=gemini-3.5-flash
GEMINI_EMBEDDING_MODEL=gemini-embedding-2
```

`.env`는 개인별 설정 파일이며 Git에서 제외됩니다. 실제 API 키를 `.env.example`, 소스 코드, 커밋, 메신저에 넣으면 안 됩니다.

> **주의:** Windows 시스템 환경 변수 또는 터미널 환경 변수에 `GEMINI_API_KEY`가 있으면 Docker Compose가 `.env`보다 그 값을 우선할 수 있습니다. 프로젝트에서는 시스템 변수 대신 `.env`만 사용하세요.

## 4. Docker 기반 통합 실행

프로젝트 루트에서 처음 실행하거나 Dockerfile/의존성이 변경된 경우 다음을 실행합니다.

```powershell
docker compose up --build -d
```

실행 상태를 확인합니다.

```powershell
docker compose ps
```

| 서비스 | 주소 | 용도 |
| --- | --- | --- |
| FastAPI | http://localhost:8000 | 백엔드 API 포트 |
| FastAPI Docs | http://localhost:8000/docs | API 스웨거 테스트 화면 |
| Streamlit | http://localhost:8501 | 프론트앤드 포트 |
| PostgreSQL + pgvector | localhost:5432 | 로컬 데이터베이스 |

소스 코드만 변경했다면 볼륨 마운트와 `--reload`가 적용되어 API 컨테이너가 자동으로 갱신됩니다. 일반적인 재실행은 아래 명령으로 충분합니다.

```powershell
docker compose up -d
```

## 5. Gemini API 호출 확인

먼저 Gemini 설정 상태를 확인합니다.(http://localhost:8000/docs 에서 테스트 권장)

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/gemini/status
```

`configured` 값이 `true`이면 실제 호출 검증을 실행합니다.

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/api/v1/gemini/verify
```

정상 응답 예시는 아래와 같습니다.

```json
{
  "status": "ok",
  "vlm_model": "gemini-3.5-flash",
  "embedding_model": "gemini-embedding-2",
  "embedding_dimensions": 3072
}
```

`/api/v1/gemini/verify`는 Gemini VLM과 임베딩 API를 실제로 각각 호출합니다. 사용량이 발생할 수 있으므로 연동 확인이 필요할 때만 실행합니다.

## 6. 로컬 Python 환경 (선택)

Docker 외에 로컬에서 코드 품질 검사 또는 디버깅을 하려면 Conda 환경을 생성합니다.

```powershell
conda env create -f environment.yml
conda activate centagging
pre-commit install
```

전체 코드 품질 검사는 아래처럼 실행합니다.

```powershell
pre-commit run --all-files
```

Python 코드는 [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)를 따르며, 세부 협업 기준은 [docs/CODING_CONVENTION.md](docs/CODING_CONVENTION.md)를 확인합니다.

## 7. 종료 및 초기화(Docker Desktop앱을 이용해도 무관)

실행 중인 컨테이너만 멈추려면 다음을 사용합니다.

```powershell
docker compose stop
```

컨테이너와 네트워크를 정리하되 로컬 DB 데이터는 유지하려면 다음을 사용합니다.

```powershell
docker compose down
```

로컬 DB 데이터까지 완전히 초기화해야 할 때만 아래 명령을 사용합니다.

```powershell
docker compose down -v
```

`-v` 옵션은 PostgreSQL 볼륨을 삭제하므로, 필요한 로컬 데이터가 있다면 실행하지 않습니다.

## 8. 문제 해결

### Docker Desktop 또는 컨테이너가 실행되지 않을 때

Docker Desktop이 실행 중인지 확인한 뒤 상태와 로그를 확인합니다.

```powershell
docker compose ps
docker compose logs api --tail 100
```

### `.env`의 Gemini 키를 변경했는데 이전 키가 계속 사용될 때

환경 변수는 컨테이너 생성 시점에 주입됩니다. API 컨테이너를 재생성합니다.

```powershell
Remove-Item Env:GEMINI_API_KEY -ErrorAction SilentlyContinue
docker compose up -d --force-recreate --no-deps api
```

위 명령 후 `/api/v1/gemini/verify`를 다시 실행합니다. Windows 시스템 환경 변수에 `GEMINI_API_KEY`가 남아 있다면 `환경 변수 편집`에서 삭제하고 새 터미널을 열어야 합니다.

### Gemini 호출이 `API_KEY_INVALID`로 실패할 때

- `.env`에 올바른 Gemini API 키가 입력됐는지 확인합니다.
- 키 앞뒤 공백이나 따옴표가 없는지 확인합니다.
- Google AI Studio에서 발급한 Gemini용 키인지 확인합니다.
- 실제 키가 노출됐다면 해당 키를 즉시 폐기하고 새 키를 발급합니다.
- API 키를 변경한 후에는 API 컨테이너를 재생성합니다.

### 포트가 이미 사용 중일 때

`.env`에서 필요한 포트를 변경한 뒤 전체 서비스를 재생성합니다.

```env
API_PORT=8001
STREAMLIT_PORT=8502
POSTGRES_PORT=5433
```

```powershell
docker compose up -d --force-recreate
```

## 9. 주요 파일

```text
centagging-backend/
├─ .github/
│  ├─ workflows/
│  │  └─ python-style.yml       # Python 스타일 검사 GitHub Actions(dev,main 브랜치에 PR하면, CI 동작)
│  └─ pull_request_template.md  # PR 작성 템플릿
│
├─ app/                         # FastAPI 백엔드
│  ├─ api/
│  │  └─ gemini.py              # Gemini 연결·검증 API
│  ├─ core/
│  │  └─ config.py              # 환경 변수·설정 관리
│  ├─ services/
│  │  └─ gemini_service.py      # Gemini API 호출 로직
│  └─ main.py                   # FastAPI 애플리케이션 시작점
│
├─ frontend/                    # Streamlit 프론트엔드
│  └─ app.py                    # Streamlit 시작점
│
├─ docker/
│  └─ db/
│     └─ init/
│        └─ 01-enable-vector.sql # PostgreSQL pgvector 확장 활성화
│
├─ docs/
│  └─ CODING_CONVENTION.md      # Google Python Style 기반 협업 규칙
│
├─ kosa-poc-main/               # 받은 샘플 코드 - 참고용, 수정 금지
│  ├─ embedding/
│  ├─ image-generation/
│  └─ vlm-tagging/
│
├─ .env                         # 개인 로컬 비밀값 - Git 제외
├─ .env.example                 # 팀 공유용 환경 변수 템플릿
├─ .gitignore                   # 비밀값·캐시·가상환경 제외 규칙
├─ .pre-commit-config.yaml      # 로컬 커밋 전 코드 검사 설정
├─ .dockerignore                # Docker 빌드 제외 규칙
├─ docker-compose.yml           # API·Frontend·DB 통합 실행
├─ Dockerfile.api               # FastAPI 컨테이너 이미지 정의
├─ Dockerfile.frontend          # Streamlit 컨테이너 이미지 정의
├─ requirements.txt             # Python 패키지 정확 버전 고정
├─ environment.yml              # Conda 환경 정의
├─ pyproject.toml               # Black 등 Python 도구 설정
└─ README.md                    # 팀 공통 설치·실행 가이드
```
