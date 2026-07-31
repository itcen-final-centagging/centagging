# Centagging Backend

## Gemini API 연동 확인

이 프로젝트는 Mock 없이 실제 Gemini API를 사용합니다. 실행 전 `.env.example`을 `.env`로 복사한 뒤, 개인 API 키를 입력합니다. `.env`는 Git에 커밋하지 않습니다.

```env
GEMINI_API_KEY=your-gemini-api-key-here
GEMINI_VLM_MODEL=gemini-3.5-flash
GEMINI_EMBEDDING_MODEL=gemini-embedding-2
```

Docker Compose 실행 후 다음 API로 설정과 실제 호출을 확인합니다.

```powershell
# API 키 노출 없이 설정 여부와 모델명 확인
Invoke-RestMethod http://localhost:8000/api/v1/gemini/status

# Gemini VLM과 임베딩 모델을 실제로 한 번씩 호출
Invoke-RestMethod -Method Post http://localhost:8000/api/v1/gemini/verify
```

`/verify`는 실제 API 호출 비용이 발생할 수 있으므로, 필요할 때만 실행합니다. 성공 시 임베딩 차원 `3072`를 반환합니다.

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
