FROM python:3.10-slim

WORKDIR /app

# 시스템 의존성 설치 (curl 은 헬스체크용)
# 파이썬 의존성은 모두 wheel 로 설치되므로 빌드 도구는 필요 없습니다.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 파이썬 의존성 설치 (소스보다 먼저 복사해 레이어 캐시 활용)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 소스 복사
COPY . .

# 실행 중 생성되는 디렉토리 (compose 에서 output/results 는 볼륨으로 덮어씁니다)
RUN mkdir -p input output results

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health

ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]