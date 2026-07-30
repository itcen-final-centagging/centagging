FROM python:3.10-slim

WORKDIR /app

# 시스템 의존성 설치
#  - build-essential : 일부 패키지 빌드용
#  - libgl1, libglib2.0-0 : opencv-python 런타임 요구사항 (utils.py 의 cv2 임포트)
#  - curl : 헬스체크용
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 파이썬 의존성 설치 (소스보다 먼저 복사해 레이어 캐시 활용)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 소스 복사
COPY . .

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health

ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]