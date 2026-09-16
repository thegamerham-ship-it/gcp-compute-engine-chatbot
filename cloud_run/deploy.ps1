# ==============================================================================
# Google Cloud Run 1-Click Deployment Script (PowerShell)
# ==============================================================================
$ErrorActionPreference = "Stop"

$ProjectId = "sesac-dev-400904"
$Region = "us-central1"
$ServiceName = "gemini-chatbot"
$SecretName = "GEMINI_API_KEY"

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "🚀 Google Cloud Run 배포 시작: $ServiceName ($ProjectId)" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

# 1. gcloud 프로젝트 설정
Write-Host "🔧 GCP 프로젝트 설정 중: $ProjectId" -ForegroundColor Yellow
gcloud config set project $ProjectId

# 2. 필수 API 활성화
Write-Host "⏳ 필수 API 활성화 확인 중..." -ForegroundColor Yellow
gcloud services enable run.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com artifactregistry.googleapis.com

# 3. Cloud Run 배포 실행 (소스 빌드 & Secret 환경변수 주입 & HTTPS 자동 발급)
Write-Host "📦 컨테이너 빌드 및 Cloud Run 서비스 배포 중..." -ForegroundColor Yellow
gcloud run deploy $ServiceName `
  --source=. `
  --project=$ProjectId `
  --region=$Region `
  --platform=managed `
  --allow-unauthenticated `
  --min-instances=0 `
  --max-instances=5 `
  --memory=1Gi `
  --cpu=1 `
  --timeout=120 `
  --set-secrets="GEMINI_API_KEY=${SecretName}:latest"

# 4. 서비스 URL 확인
$ServiceUrl = (gcloud run services describe $ServiceName --project=$ProjectId --region=$Region --format='value(status.url)').Trim()

Write-Host "================================================================" -ForegroundColor Green
Write-Host "🎉 Cloud Run 배포가 성공적으로 완료되었습니다!" -ForegroundColor Green
Write-Host "🌐 접속 URL: $ServiceUrl" -ForegroundColor Green
Write-Host "🩺 헬스체크: $ServiceUrl/health" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Green
