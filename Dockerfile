FROM python:3.11-slim

WORKDIR /app

# 필요 라이브러리 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 전체 소스 코드 복사
COPY . .

# Cloud Run 기본 포트 환경변수 및 실행
ENV PORT=8080
CMD exec python server.py