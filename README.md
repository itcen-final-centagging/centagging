# Centagging Backend

VLM 기반 가구 자동 태깅 및 SKU 매칭 솔루션입니다.

## 현재 구성

- API: FastAPI
- 관리자 화면: Streamlit
- 팀 공통 실행 환경: Docker Compose, Python 3.10.20
- 로컬 Python 환경: Anaconda, Python 3.10.20 (선택 사항)
- 참고 샘플: `kosa-poc-main/` (수정하지 않음)

## 로컬 실행

```bash
conda env create -f environment.yml
conda activate centagging
```

환경 변수를 사용하기 전에 `.env.example`을 복사해 `.env` 파일을 만듭니다. `.env`에는 실제 Gemini API 키 등 민감 정보를 입력하며 Git에 커밋하지 않습니다.

FastAPI는 다음 명령으로 실행합니다.

```bash
uvicorn app.main:app --reload
```

- API 상태 확인: `http://localhost:8000/health`
- API 문서: `http://localhost:8000/docs`

Streamlit은 별도 터미널에서 실행합니다.

```bash
streamlit run frontend/app.py
```

- 관리자 화면: `http://localhost:8501`

## Docker 실행 (팀 공통 기준)

팀 공통 실행 환경은 Docker Compose를 기준으로 합니다. Docker Desktop을 설치한 뒤, 저장소 루트에서 아래 명령을 실행합니다.

```bash
docker compose up --build
```

- FastAPI 상태 확인: `http://localhost:8000/health`
- FastAPI 문서: `http://localhost:8000/docs`
- Streamlit 관리자 화면: `http://localhost:8501`
- PostgreSQL + PGVector: `localhost:5432`

Gemini API를 사용할 때만 `.env.example`을 복사해 `.env`를 만들고 `GEMINI_API_KEY`를 입력합니다. `.env`는 Git에 커밋하지 않습니다.

`requirements.txt`와 Docker 이미지 digest는 이 Docker 환경에서 실제 기동 검증한 버전으로 고정되어 있습니다. 버전을 변경할 때는 반드시 Docker Compose 재빌드와 헬스체크를 다시 수행합니다.

```bash
docker compose down
```

위 명령은 컨테이너만 종료합니다. 로컬 DB 데이터까지 초기화해야 할 때만 `docker compose down -v`를 사용합니다.
