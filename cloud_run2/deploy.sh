#!/usr/bin/env bash
# ==============================================================================
# Google Cloud Run 1-Click Deployment Script (Bash - ADC Mode)
# ==============================================================================
set -e

PROJECT_ID=$(gcloud config get-value project 2>/dev/null || echo "iceu-songpa21")
REGION="asia-northeast3"
SERVICE_NAME="gemini-chatbot-adc"

echo "================================================================"
echo "🚀 Google Cloud Run (ADC Keyless) 배포 시작: ${SERVICE_NAME} (${PROJECT_ID})"
echo "================================================================"

# 1. gcloud 프로젝트 설정
gcloud config set project "${PROJECT_ID}"

# 2. 필수 API 활성화 (Vertex AI / Model API 필수)
echo "⏳ 필수 API 활성화 확인 중..."
gcloud services enable aiplatform.googleapis.com run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

# 3. 서비스 계정 IAM 바인딩 (Vertex AI User 권한 부여 -> ADC 인증 활성화)
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
echo "🔐 서비스 계정(${COMPUTE_SA})에 Vertex AI User 역할 부여..."
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${COMPUTE_SA}" \
  --role="roles/aiplatform.user" || true

# 4. Cloud Run 배포 실행 (소스 빌드 & ADC 환경변수 주입)
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
  --set-env-vars="^#^GOOGLE_CLOUD_PROJECT=${PROJECT_ID}#GOOGLE_CLOUD_LOCATION=global#GOOGLE_GENAI_USE_VERTEXAI=true"

# 5. 서비스 URL 확인
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" --project="${PROJECT_ID}" --region="${REGION}" --format='value(status.url)')

echo "================================================================"
echo "🎉 Cloud Run 배포가 성공적으로 완료되었습니다!"
echo "🌐 접속 URL: ${SERVICE_URL}"
echo "🩺 헬스체크: ${SERVICE_URL}/health"
echo "🔑 인증 방식: Google Cloud ADC (애플리케이션 기본 사용자 인증 정보)"
echo "================================================================"
