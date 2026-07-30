FROM python:3.10-slim

WORKDIR /app

# 필수 의존성 빌드 도구 설치
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 파이썬 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 소스 복사
COPY . .

# Streamlit 포트 노출
EXPOSE 8501

# Streamlit 헬스체크 설정
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health

# 실행 명령어 정의
ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
