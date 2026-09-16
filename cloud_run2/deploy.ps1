# ==============================================================================
# Google Cloud Run 1-Click Deployment Script (PowerShell - ADC Mode)
# ==============================================================================
$ErrorActionPreference = "Stop"

$DetectedProj = (gcloud config get-value project 2>$null)
if (-not $DetectedProj -or $DetectedProj.Contains("(unset)")) {
    $ProjectId = "iceu-songpa21"
} else {
    $ProjectId = $DetectedProj.Trim()
}

$Region = "asia-northeast3"
$ServiceName = "gemini-chatbot-adc"

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "🚀 Google Cloud Run (ADC Keyless) 배포 시작: $ServiceName ($ProjectId)" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

# 1. gcloud 프로젝트 설정
Write-Host "🔧 GCP 프로젝트 설정 중: $ProjectId" -ForegroundColor Yellow
gcloud config set project $ProjectId

# 2. 필수 API 활성화 (Vertex AI / Model API 필수)
Write-Host "⏳ 필수 API 활성화 확인 중..." -ForegroundColor Yellow
gcloud services enable aiplatform.googleapis.com run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

# 3. 서비스 계정 IAM 바인딩 (Vertex AI User 권한 부여 -> ADC 인증 활성화)
$ProjectNumber = (gcloud projects describe $ProjectId --format="value(projectNumber)").Trim()
$ComputeSa = "${ProjectNumber}-compute@developer.gserviceaccount.com"
Write-Host "🔐 서비스 계정($ComputeSa)에 Vertex AI User 역할 부여 중..." -ForegroundColor Yellow
gcloud projects add-iam-policy-binding $ProjectId `
  --member="serviceAccount:$ComputeSa" `
  --role="roles/aiplatform.user" | Out-Null

# 4. Cloud Run 배포 실행 (소스 빌드 & ADC 환경변수 주입)
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
  --set-env-vars="^#^GOOGLE_CLOUD_PROJECT=$ProjectId#GOOGLE_CLOUD_LOCATION=global#GOOGLE_GENAI_USE_VERTEXAI=true"

# 5. 서비스 URL 확인
$ServiceUrl = (gcloud run services describe $ServiceName --project=$ProjectId --region=$Region --format="value(status.url)").Trim()

Write-Host "================================================================" -ForegroundColor Green
Write-Host "🎉 Cloud Run 배포가 성공적으로 완료되었습니다!" -ForegroundColor Green
Write-Host "🌐 접속 URL: $ServiceUrl" -ForegroundColor Green
Write-Host "🩺 헬스체크: $ServiceUrl/health" -ForegroundColor Green
Write-Host "🔑 인증 방식: Google Cloud ADC (애플리케이션 기본 사용자 인증 정보)" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Green
