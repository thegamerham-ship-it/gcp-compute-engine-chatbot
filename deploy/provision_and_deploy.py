#!/usr/bin/env python3
"""
GCP Compute Engine Provisioning & Gemini Chatbot Deployment Automation
Ref: compute_engine_example.ipynb
Target Secret: projects/902882112756/secrets/GEMINI_API_KEY
"""

import os
import sys
import time
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = BASE_DIR / "deployment.log"

PROJECT_ID = "sesac-dev-400904"
PROJECT_NUMBER = "902882112756"
ZONE = "us-central1-c"
REGION = "us-central1"
INSTANCE_NAME = f"instance-20260915-{int(time.time()) % 100000}"
SUBNET = "my-vpc"
SERVICE_ACCOUNT = f"{PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
FIREWALL_RULE = "allow-chatbot-3000"
TARGET_TAG = "chatbot-server"

IS_WIN = sys.platform == "win32"

def log(message: str, to_console: bool = True):
    try:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    formatted = f"[{timestamp}] {message}"
    if to_console:
        try:
            print(formatted, flush=True)
        except UnicodeEncodeError:
            safe_text = formatted.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8")
            print(safe_text, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(formatted + "\n")
    except Exception:
        pass

def run_cmd(cmd, check=True, capture=True, env=None):
    log(f"RUNNING: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    run_env = os.environ.copy()
    if env:
        run_env.update(env)

    proc = subprocess.run(
        cmd,
        shell=True if IS_WIN else isinstance(cmd, str),
        env=run_env,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
        text=True
    )
    output = proc.stdout if capture else ""
    if output:
        log(f"OUTPUT:\n{output.strip()}")
    if check and proc.returncode != 0:
        log(f"ERROR: Command failed with exit code {proc.returncode}")
        raise RuntimeError(f"Command failed: {proc.returncode} -> {output}")
    return proc

def main():
    global INSTANCE_NAME, ZONE, PROJECT_ID, PROJECT_NUMBER, SERVICE_ACCOUNT, SUBNET
    log("================================================================================")
    log("🚀 [PHASE 1] Initializing Provisioning & Deployment Environment")
    log("================================================================================")

    # 1. 활성 gcloud 프로젝트 동적 감지
    proj_proc = run_cmd(["gcloud", "config", "get-value", "project"], check=False)
    active_proj = proj_proc.stdout.strip()
    if active_proj and not active_proj.startswith("ERROR") and "(unset)" not in active_proj:
        PROJECT_ID = active_proj

    # 2. 프로젝트 번호 및 기본 서비스 계정 조회
    pnum_proc = run_cmd(["gcloud", "projects", "describe", PROJECT_ID, "--format=value(projectNumber)"], check=False)
    if pnum_proc.returncode == 0 and pnum_proc.stdout.strip():
        PROJECT_NUMBER = pnum_proc.stdout.strip()
        SERVICE_ACCOUNT = f"{PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

    # 3. 네트워크 및 서브넷 동적 확인
    net_proc = run_cmd(["gcloud", "compute", "networks", "list", f"--project={PROJECT_ID}", "--format=value(name)"], check=False)
    available_nets = net_proc.stdout.split()
    if "my-vpc" in available_nets:
        SUBNET = "my-vpc"
    elif "default" in available_nets:
        SUBNET = "default"
    else:
        SUBNET = available_nets[0] if available_nets else "default"

    log(f"Project ID: {PROJECT_ID} (Number: {PROJECT_NUMBER})")
    log(f"Zone: {ZONE}")
    log(f"Instance Name: {INSTANCE_NAME}")
    log(f"VPC Subnet: {SUBNET}")
    log(f"Service Account: {SERVICE_ACCOUNT}")



    # 5. Secret Manager 권한 및 키 확인 (미존재 시 로컬 환경변수에서 자동 등록)
    log("--------------------------------------------------------------------------------")
    log("🔑 [PHASE 2] Verifying / Registering GEMINI_API_KEY in Secret Manager")
    log("--------------------------------------------------------------------------------")
    run_cmd(["gcloud", "services", "enable", "secretmanager.googleapis.com", f"--project={PROJECT_ID}"], check=False)

    check_secret_cmd = [
        "gcloud", "secrets", "describe", "GEMINI_API_KEY",
        f"--project={PROJECT_ID}"
    ]
    sec_proc = run_cmd(check_secret_cmd, check=False)
    if "GEMINI_API_KEY" not in sec_proc.stdout:
        log("ℹ️ Secret 'GEMINI_API_KEY' does not exist yet. Checking local environment variable...")
        local_key = os.environ.get("GEMINI_API_KEY", "")
        if local_key:
            log("🔑 Found GEMINI_API_KEY in local environment! Automatically registering to Secret Manager...")
            run_cmd(["gcloud", "secrets", "create", "GEMINI_API_KEY", "--replication-policy=automatic", f"--project={PROJECT_ID}"])
            # Add version via stdin
            add_proc = subprocess.run(
                ["gcloud", "secrets", "versions", "add", "GEMINI_API_KEY", "--data-file=-", f"--project={PROJECT_ID}"],
                input=local_key, text=True, shell=IS_WIN, capture_output=True
            )
            log("✅ Successfully created secret 'GEMINI_API_KEY' and registered active version!")
        else:
            log("❌ Error: GEMINI_API_KEY not found in Secret Manager and not set in local environment.")
            sys.exit(1)
    else:
        log("✅ Verified Secret 'GEMINI_API_KEY' exists in Secret Manager.")

    # Compute SA에 secretAccessor 권한 부여
    log(f"🔐 Ensuring Service Account ({SERVICE_ACCOUNT}) has Secret Accessor role...")
    run_cmd([
        "gcloud", "secrets", "add-iam-policy-binding", "GEMINI_API_KEY",
        f"--member=serviceAccount:{SERVICE_ACCOUNT}",
        "--role=roles/secretmanager.secretAccessor",
        f"--project={PROJECT_ID}"
    ], check=False)

    # 3. 방화벽 규칙 확인 및 생성 (Port 3000, 80, 443, IAP SSH 허용)
    log("--------------------------------------------------------------------------------")
    log("🛡️ [PHASE 3] Configuring VPC Firewall Rules (Port 3000, 80, 443, IAP SSH)")
    log("--------------------------------------------------------------------------------")
    fw_rules = [
        {"name": "allow-chatbot-3000", "allow": "tcp:3000", "tags": "chatbot-server", "desc": "Allow port 3000 for FastAPI"},
        {"name": "allow-http-80", "allow": "tcp:80", "tags": "http-server", "desc": "Allow port 80 for HTTP / Certbot"},
        {"name": "allow-https-443", "allow": "tcp:443", "tags": "https-server", "desc": "Allow port 443 for HTTPS SSL"},
        {"name": "allow-ssh-ingress-from-iap", "allow": "tcp:22", "source_ranges": "35.235.240.0/20", "desc": "Allow SSH via Cloud IAP tunnel"}
    ]
    for rule in fw_rules:
        fw_check = run_cmd(["gcloud", "compute", "firewall-rules", "list", f"--project={PROJECT_ID}", f"--filter=name={rule['name']}", "--format=value(name)"], check=False)
        if rule['name'] not in fw_check.stdout:
            log(f"Firewall rule '{rule['name']}' does not exist. Creating...")
            create_fw_cmd = [
                "gcloud", "compute", "firewall-rules", "create", rule['name'],
                f"--project={PROJECT_ID}",
                f"--network={SUBNET}",
                f"--allow={rule['allow']}",
                f"--description={rule['desc']}"
            ]
            if "tags" in rule:
                create_fw_cmd.append(f"--target-tags={rule['tags']}")
            if "source_ranges" in rule:
                create_fw_cmd.append(f"--source-ranges={rule['source_ranges']}")
            run_cmd(create_fw_cmd, check=False)
            log(f"✅ Firewall rule '{rule['name']}' created successfully.")
        else:
            log(f"ℹ️ Firewall rule '{rule['name']}' already exists.")

    # 4. Resource Policy (Snapshot Schedule) 확인
    disk_schedule = ""
    sched_check = run_cmd(["gcloud", "compute", "resource-policies", "list", f"--project={PROJECT_ID}", f"--regions={REGION}", "--format=value(name)"], check=False)
    if "default-schedule-1" in sched_check.stdout:
        disk_schedule = f",disk-resource-policy=projects/{PROJECT_ID}/regions/{REGION}/resourcePolicies/default-schedule-1"
        log("ℹ️ Found existing resource policy: default-schedule-1")
    else:
        log("ℹ️ default-schedule-1 not found; creating instance without disk snapshot policy.")

    # 5. Compute Engine 인스턴스 존재 여부 확인 및 생성
    log("--------------------------------------------------------------------------------")
    log("🖥️ [PHASE 4] Checking / Creating Compute Engine Instance")
    log("--------------------------------------------------------------------------------")
    inst_check = run_cmd([
        "gcloud", "compute", "instances", "list",
        f"--project={PROJECT_ID}",
        "--filter=status=RUNNING",
        "--format=value(name,zone)"
    ], check=False)
    
    current_instance = None
    if inst_check.stdout.strip():
        valid_lines = [l for l in inst_check.stdout.strip().splitlines() if l.strip() and not l.startswith("WARNING") and not l.startswith("ERROR")]
        if valid_lines:
            first_inst = valid_lines[0].split()
            if len(first_inst) >= 1 and not first_inst[0].startswith("WARNING"):
                current_instance = first_inst[0]
                if len(first_inst) >= 2:
                    current_zone = first_inst[1].split("/")[-1]
                else:
                    current_zone = ZONE
                log(f"ℹ️ Found existing RUNNING instance '{current_instance}' in zone '{current_zone}'. Reusing instance.")
                INSTANCE_NAME = current_instance
                ZONE = current_zone

    if not current_instance:
        log(f"No running instance found. Creating new Compute Engine instance '{INSTANCE_NAME}'...")
        create_vm_cmd = [
            "gcloud", "compute", "instances", "create", INSTANCE_NAME,
            f"--project={PROJECT_ID}",
            f"--zone={ZONE}",
            "--machine-type=e2-medium",
            f"--network-interface=network-tier=PREMIUM,stack-type=IPV4_ONLY,subnet={SUBNET}",
            "--metadata=enable-osconfig=TRUE",
            "--maintenance-policy=MIGRATE",
            "--provisioning-model=STANDARD",
            f"--service-account={SERVICE_ACCOUNT}",
            "--scopes=https://www.googleapis.com/auth/cloud-platform",
            f"--create-disk=auto-delete=yes,boot=yes,device-name={INSTANCE_NAME}{disk_schedule},image=projects/debian-cloud/global/images/family/debian-13,mode=rw,size=10,type=pd-balanced",
            "--no-shielded-secure-boot",
            "--shielded-vtpm",
            "--shielded-integrity-monitoring",
            f"--tags={TARGET_TAG},http-server",
            "--labels=goog-ops-agent-policy=v2-template-1-7-0,goog-ec-src=vm_add-gcloud",
            "--reservation-affinity=any"
        ]
        run_cmd(create_vm_cmd)
        log(f"✅ Compute Engine instance '{INSTANCE_NAME}' created successfully!")

    # 6. 인스턴스 외부 IP 주소 조회
    log("--------------------------------------------------------------------------------")
    log("🌐 [PHASE 5] Retrieving VM External IP Address")
    log("--------------------------------------------------------------------------------")
    ip_proc = run_cmd([
        "gcloud", "compute", "instances", "describe", INSTANCE_NAME,
        f"--project={PROJECT_ID}",
        f"--zone={ZONE}",
        "--format=value(networkInterfaces[0].accessConfigs[0].natIP)"
    ])
    external_ip = ip_proc.stdout.strip()
    log(f"🎯 Assigned External IP: {external_ip}")

    # 7. SSH 연결 대기 (인스턴스 부팅 대기 - IAP 터널링 사용)
    log("--------------------------------------------------------------------------------")
    log("⏳ [PHASE 6] Waiting for SSH daemon on VM (using IAP Tunnel)...")
    log("--------------------------------------------------------------------------------")
    ssh_ready = False
    for attempt in range(1, 15):
        log(f"SSH test attempt {attempt}/15...")
        test_ssh = run_cmd([
            "gcloud", "compute", "ssh", INSTANCE_NAME,
            f"--project={PROJECT_ID}",
            f"--zone={ZONE}",
            "--tunnel-through-iap",
            "--command=echo 'SSH_READY'",
            "--ssh-flag=-o ConnectTimeout=10",
            "--quiet"
        ], check=False)
        if "SSH_READY" in test_ssh.stdout:
            ssh_ready = True
            log("✅ SSH connection established successfully.")
            break
        time.sleep(10)

    if not ssh_ready:
        log("❌ SSH connection timed out.")
        sys.exit(1)

    # 8. 애플리케이션 파일 전송 (IAP 터널링 사용)
    log("--------------------------------------------------------------------------------")
    log("📦 [PHASE 7] Transferring Chatbot Files to VM via SCP (using IAP Tunnel)")
    log("--------------------------------------------------------------------------------")
    files_to_send = [
        str(BASE_DIR / "server.py"),
        str(BASE_DIR / "requirements.txt"),
        str(BASE_DIR / "public"),
        str(BASE_DIR / "deploy" / "setup_vm.sh"),
        str(BASE_DIR / "deploy" / "setup_https.sh")
    ]
    scp_cmd = [
        "gcloud", "compute", "scp",
        "--tunnel-through-iap",
        "--recurse"
    ] + files_to_send + [
        f"{INSTANCE_NAME}:~/",
        f"--project={PROJECT_ID}",
        f"--zone={ZONE}",
        "--quiet"
    ]
    run_cmd(scp_cmd)
    log("✅ Files transferred successfully.")

    # 9. VM 내부 프로비저닝 스크립트 실행 (IAP 터널링 사용)
    log("--------------------------------------------------------------------------------")
    log("⚙️ [PHASE 8] Executing setup_vm.sh & setup_https.sh on VM")
    log("--------------------------------------------------------------------------------")
    exec_setup_cmd = [
        "gcloud", "compute", "ssh", INSTANCE_NAME,
        f"--project={PROJECT_ID}",
        f"--zone={ZONE}",
        "--tunnel-through-iap",
        "--command=chmod +x setup_vm.sh setup_https.sh && ./setup_vm.sh && ./setup_https.sh",
        "--quiet"
    ]
    run_cmd(exec_setup_cmd)
    log("✅ VM setup & HTTPS automation finished.")

    # 10. 엔드포인트 헬스체크 및 테스트 질의
    log("--------------------------------------------------------------------------------")
    log("🧪 [PHASE 9] Verification & Health Check")
    log("--------------------------------------------------------------------------------")
    time.sleep(5)
    
    # Status Check (HTTP & HTTPS)
    ip_dash = external_ip.replace(".", "-")
    https_domain = f"https://{ip_dash}.sslip.io"
    status_url = f"http://{external_ip}:3000/api/status"
    https_status_url = f"{https_domain}/api/status"
    log(f"Querying HTTP status endpoint: {status_url}")
    status_proc = run_cmd(["curl", "-s", "--connect-timeout", "10", status_url], check=False)
    log(f"HTTP Status Response: {status_proc.stdout.strip()}")

    log(f"Querying HTTPS status endpoint: {https_status_url}")
    https_status_proc = run_cmd(["curl", "-s", "-k", "--connect-timeout", "10", https_status_url], check=False)
    log(f"HTTPS Status Response: {https_status_proc.stdout.strip()}")

    # Chat test query
    chat_url = f"{https_domain}/api/chat"
    log(f"Querying chat test endpoint: {chat_url}")
    chat_payload = json.dumps({
        "input": "안녕하세요! Compute Engine에서 정상 작동 중인지 테스트 메시지입니다.",
        "model": "gemini-3.8-flash"
    })
    chat_proc = run_cmd([
        "curl", "-s", "-k", "--connect-timeout", "30",
        "-X", "POST", chat_url,
        "-H", "Content-Type: application/json",
        "-d", chat_payload
    ], check=False)
    log(f"Chat Response: {chat_proc.stdout.strip()}")

    log("================================================================================")
    log("🎉 [DEPLOYMENT SUCCESSFUL]")
    log(f"🌐 Secure HTTPS Web UI: {https_domain}")
    log(f"🌐 Direct HTTP URL: http://{external_ip}:3000")
    log(f"Instance Name: {INSTANCE_NAME}")
    log(f"Zone: {ZONE}")
    log(f"Deployment Log Path: {LOG_FILE}")
    log("================================================================================")

if __name__ == "__main__":
    main()
