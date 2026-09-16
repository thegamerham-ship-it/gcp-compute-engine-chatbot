#!/usr/bin/env python3
"""
Google Cloud Run 1-Click Automated Deployment Script (ADC Mode)
Gemini 3.8 Flash / 3.7 Flash Web Chatbot (Keyless Architecture)
Based on Google Cloud Agent Platform / ADC Best Practices (capture.png)
"""

import os
import sys
import subprocess
import shutil
import argparse
from pathlib import Path

IS_WIN = sys.platform == "win32"

DEFAULT_PROJECT_ID = "iceu-songpa21"
DEFAULT_REGION = "asia-northeast3"  # 서울 리전 (Seoul)
DEFAULT_SERVICE_NAME = "gemini-chatbot-adc"

def run_command(cmd, check=True, capture=True):
    cmd_str = ' '.join(cmd) if isinstance(cmd, list) else cmd
    print(f"\n[RUNNING] {cmd_str}")
    proc = subprocess.run(
        cmd,
        shell=True if IS_WIN else isinstance(cmd, str),
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
        text=True
    )
    if capture and proc.stdout:
        print(proc.stdout.strip())
    if check and proc.returncode != 0:
        print(f"[ERROR] Command failed with exit code {proc.returncode}")
        sys.exit(proc.returncode)
    return proc

def get_current_gcloud_project():
    try:
        res = subprocess.run(
            ["gcloud", "config", "get-value", "project"],
            capture_output=True, text=True, shell=IS_WIN
        )
        proj = res.stdout.strip()
        if proj and "(unset)" not in proj:
            return proj
    except Exception:
        pass
    return DEFAULT_PROJECT_ID

def check_prerequisites():
    print("================================================================")
    print("🔍 [STEP 1] 사전 배포 환경 및 도구 확인")
    print("================================================================")
    
    if not shutil.which("gcloud"):
        print("❌ [오류] Google Cloud SDK('gcloud')가 설치되어 있지 않거나 PATH에 없습니다.")
        print("   https://cloud.google.com/sdk/docs/install 에서 설치 후 다시 시도해주세요.")
        sys.exit(1)
    print("✅ gcloud CLI 감지 완료")

    detected_proj = get_current_gcloud_project()
    print(f"✅ 활성 GCP 프로젝트: {detected_proj}")
    return detected_proj

def main():
    detected_proj = get_current_gcloud_project()

    parser = argparse.ArgumentParser(description="Deploy Gemini Chatbot (ADC Mode) to Google Cloud Run")
    parser.add_argument("--project", default=detected_proj, help=f"GCP Project ID (default: {detected_proj})")
    parser.add_argument("--region", default=DEFAULT_REGION, help=f"GCP Region (default: {DEFAULT_REGION})")
    parser.add_argument("--service", default=DEFAULT_SERVICE_NAME, help=f"Cloud Run Service Name (default: {DEFAULT_SERVICE_NAME})")
    parser.add_argument("--min-instances", default="0", help="Min instances (default: 0 for scale-to-zero cost savings)")
    parser.add_argument("--max-instances", default="5", help="Max instances (default: 5)")
    args = parser.parse_args()

    project_id = args.project
    region = args.region
    service_name = args.service

    check_prerequisites()

    print("\n================================================================")
    print(f"🚀 [STEP 2] GCP 프로젝트 설정 및 필수 API 활성화 ({project_id})")
    print("================================================================")
    run_command(["gcloud", "config", "set", "project", project_id])

    # ADC 기반 모델 호출에 필요한 필수 API (Vertex AI / Model API 필수 활성화)
    apis = [
        "aiplatform.googleapis.com",       # Vertex AI / Model API (capture.png 권장)
        "run.googleapis.com",              # Cloud Run API
        "cloudbuild.googleapis.com",       # Cloud Build API
        "artifactregistry.googleapis.com"  # Artifact Registry API
    ]
    print(f"⏳ 필수 API 활성화 확인 및 갱신 중: {', '.join(apis)}")
    run_command(["gcloud", "services", "enable", *apis])
    print("✅ 모든 필수 API 활성화 완료")

    print("\n================================================================")
    print("🔐 [STEP 3] Cloud Run 서비스 계정(ADC) IAM 권한 바인딩")
    print("================================================================")
    # 프로젝트 번호 조회
    pnum_res = run_command(["gcloud", "projects", "describe", project_id, "--format=value(projectNumber)"])
    project_number = pnum_res.stdout.strip()
    compute_sa = f"{project_number}-compute@developer.gserviceaccount.com"

    # Compute SA에 Vertex AI User(roles/aiplatform.user) 권한 부여 (ADC 방식 핵심)
    print(f"🔑 서비스 계정({compute_sa})에 'Vertex AI User(roles/aiplatform.user)' 권한 부여 중...")
    run_command([
        "gcloud", "projects", "add-iam-policy-binding", project_id,
        f"--member=serviceAccount:{compute_sa}",
        "--role=roles/aiplatform.user"
    ], check=False)

    print("✅ IAM 권한 바인딩 완료 (API Key 불필요, ADC 키리스 인증 적용)")

    print("\n================================================================")
    print(f"📦 [STEP 4] Cloud Run 컨테이너 빌드 및 배포 시작 ({service_name})")
    print("================================================================")
    script_dir = Path(__file__).resolve().parent

    deploy_cmd = [
        "gcloud", "run", "deploy", service_name,
        f"--source={str(script_dir)}",
        f"--project={project_id}",
        f"--region={region}",
        "--platform=managed",
        "--allow-unauthenticated",
        f"--min-instances={args.min_instances}",
        f"--max-instances={args.max_instances}",
        "--memory=1Gi",
        "--cpu=1",
        "--timeout=120",
        f"--set-env-vars=^#^GOOGLE_CLOUD_PROJECT={project_id}#GOOGLE_CLOUD_LOCATION=global#GOOGLE_GENAI_USE_VERTEXAI=true"
    ]

    run_command(deploy_cmd, check=True, capture=False)

    print("\n================================================================")
    print("🎉 [STEP 5] 배포 완료 및 접속 URL 확인")
    print("================================================================")
    url_res = run_command([
        "gcloud", "run", "services", "describe", service_name,
        f"--project={project_id}",
        f"--region={region}",
        "--format=value(status.url)"
    ])
    service_url = url_res.stdout.strip()

    print("================================================================")
    print("🌟 Google Cloud Run ADC 기반 배포 성공!")
    print(f"🌐 공식 HTTPS 서비스 접속 주소: {service_url}")
    print(f"🩺 헬스체크 주소: {service_url}/health")
    print(f"📊 상태 API 주소: {service_url}/api/status")
    print("🔑 인증 모드: ADC (Application Default Credentials, 완전 키리스)")
    print("================================================================")

if __name__ == "__main__":
    main()
