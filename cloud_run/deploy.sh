#!/usr/bin/env bash
# ==============================================================================
# Google Cloud Run 1-Click Deployment Script (Bash)
# ==============================================================================
set -e

PROJECT_ID="sesac-dev-400904"
REGION="us-central1"
SERVICE_NAME="gemini-chatbot"
SECRET_NAME="GEMINI_API_KEY"

echo "================================================================"
echo "🚀 Google Cloud Run 배포 시작: ${SERVICE_NAME} (${PROJECT_ID})"
echo "================================================================"

# 1. gcloud 프로젝트 설정
gcloud config set project "${PROJECT_ID}"

# 2. 필수 API 활성화
echo "⏳ 필수 API 활성화 확인 중..."
gcloud services enable run.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com artifactregistry.googleapis.com

# 3. Cloud Run 배포 실행 (소스 빌드 & Secret 환경변수 주입 & HTTPS 자동 발급)
echo "📦 컨테이너 빌드 및 Cloud Run 서비스 배포 중..."
gcloud run deploy "${SERVICE_NAME}" \
  --source=. \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --platform=managed \
  --allow-unauthenticated \
  --min-instances=0 \
  --max-instances=5 \
  --memory=1Gi \
  --cpu=1 \
  --timeout=120 \
  --set-secrets="GEMINI_API_KEY=${SECRET_NAME}:latest"

# 4. 서비스 URL 확인
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" --project="${PROJECT_ID}" --region="${REGION}" --format='value(status.url)')

echo "================================================================"
echo "🎉 Cloud Run 배포가 성공적으로 완료되었습니다!"
echo "🌐 접속 URL: ${SERVICE_URL}"
echo "🩺 헬스체크: ${SERVICE_URL}/health"
echo "================================================================"
