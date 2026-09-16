#!/usr/bin/env python3
"""
Google Cloud Run 1-Click Automated Deployment Script
Gemini 3.8 Flash / 3.7 Flash Web Chatbot
"""

import os
import sys
import subprocess
import shutil
import argparse
from pathlib import Path

IS_WIN = sys.platform == "win32"

# 기본 GCP 설정 (사용자 기존 환경과 일치)
DEFAULT_PROJECT_ID = "iceu-songpa21"
DEFAULT_REGION = "us-central1"
DEFAULT_SERVICE_NAME = "gemini-chatbot"
DEFAULT_SECRET_NAME = "GEMINI_API_KEY"

def run_command(cmd, check=True, capture=True):
    print(f"\n[RUNNING] {' '.join(cmd) if isinstance(cmd, list) else cmd}")
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

def check_prerequisites():
    print("================================================================")
    print("🔍 [STEP 1] 사전 배포 환경 및 도구 확인")
    print("================================================================")
    
    if not shutil.which("gcloud"):
        print("❌ [오류] Google Cloud SDK('gcloud')가 설치되어 있지 않거나 PATH에 없습니다.")
        print("   https://cloud.google.com/sdk/docs/install 에서 설치 후 다시 시도해주세요.")
        sys.exit(1)
    print("✅ gcloud CLI 감지 완료")

    # 프로젝트 확인
    res = subprocess.run(["gcloud", "config", "get-value", "project"], capture_output=True, text=True, shell=IS_WIN)
    current_proj = res.stdout.strip()
    return current_proj

def main():
    parser = argparse.ArgumentParser(description="Deploy Gemini Chatbot to Google Cloud Run")
    parser.add_argument("--project", default=DEFAULT_PROJECT_ID, help=f"GCP Project ID (default: {DEFAULT_PROJECT_ID})")
    parser.add_argument("--region", default=DEFAULT_REGION, help=f"GCP Region (default: {DEFAULT_REGION})")
    parser.add_argument("--service", default=DEFAULT_SERVICE_NAME, help=f"Cloud Run Service Name (default: {DEFAULT_SERVICE_NAME})")
    parser.add_argument("--secret", default=DEFAULT_SECRET_NAME, help=f"Secret Manager Key Name (default: {DEFAULT_SECRET_NAME})")
    parser.add_argument("--min-instances", default="0", help="Min instances (default: 0 for scale-to-zero cost savings)")
    parser.add_argument("--max-instances", default="5", help="Max instances (default: 5)")
    args = parser.parse_args()

    project_id = args.project
    region = args.region
    service_name = args.service
    secret_name = args.secret

    check_prerequisites()

    print("\n================================================================")
    print(f"🚀 [STEP 2] GCP 프로젝트 설정 및 필수 API 활성화 ({project_id})")
    print("================================================================")
    run_command(["gcloud", "config", "set", "project", project_id])

    # 필수 API 활성화 (Cloud Run, Cloud Build, Secret Manager, Artifact Registry)
    apis = [
        "run.googleapis.com",
        "cloudbuild.googleapis.com",
        "secretmanager.googleapis.com",
        "artifactregistry.googleapis.com"
    ]
    print(f"⏳ 필수 API 상태 확인 및 활성화 중: {', '.join(apis)}")
    run_command(["gcloud", "services", "enable", *apis])
    print("✅ 모든 필수 API 활성화 완료")

    print("\n================================================================")
    print("🔑 [STEP 3] Secret Manager 및 서비스 계정 권한 확인")
    print("================================================================")
    # 프로젝트 번호 조회
    pnum_res = run_command(["gcloud", "projects", "describe", project_id, "--format=value(projectNumber)"])
    project_number = pnum_res.stdout.strip()
    compute_sa = f"{project_number}-compute@developer.gserviceaccount.com"

    # Compute SA에 Secret Manager Secret Accessor 권한 부여
    print(f"🔐 서비스 계정({compute_sa})에 Secret Accessor 권한 부여 중...")
    run_command([
        "gcloud", "projects", "add-iam-policy-binding", project_id,
        f"--member=serviceAccount:{compute_sa}",
        "--role=roles/secretmanager.secretAccessor"
    ], check=False)

    # Secret 존재 확인
    secret_check = subprocess.run(
        ["gcloud", "secrets", "describe", secret_name, f"--project={project_id}"],
        capture_output=True, text=True, shell=IS_WIN
    )
    if secret_check.returncode != 0:
        print(f"⚠️ 경고: Secret Manager에 '{secret_name}'이 없습니다.")
        print("   배포 시 Secret 바인딩 대신 환경변수나 로컬 키를 사용하도록 시도합니다.")
        secret_flag = []
    else:
        print(f"✅ Secret Manager '{secret_name}' 확인 완료.")
        secret_flag = [f"--set-secrets=GEMINI_API_KEY={secret_name}:latest"]

    print("\n================================================================")
    print(f"📦 [STEP 4] Cloud Run 컨테이너 빌드 및 배포 시작 ({service_name})")
    print("================================================================")
    # cloud_run 디렉터리를 소스로 배포
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
        "--timeout=120"
    ] + secret_flag

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
    print("🌟 Google Cloud Run 배포 성공!")
    print(f"🌐 공식 HTTPS 서비스 접속 주소: {service_url}")
    print(f"🩺 헬스체크 주소: {service_url}/health")
    print(f"📊 상태 API 주소: {service_url}/api/status")
    print("================================================================")

if __name__ == "__main__":
    main()
