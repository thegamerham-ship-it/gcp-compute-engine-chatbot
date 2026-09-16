import os
import time
import asyncio
from typing import Optional, List, Dict, Any
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from google import genai
import google.auth
from google.auth.exceptions import DefaultCredentialsError
import uvicorn

# ------------------------------------------------------------------------------
# 1. 로컬 개발 환경용 .env 파일 로드 (환경변수 보조)
# ------------------------------------------------------------------------------
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip("\"'")
            if k and not os.environ.get(k):
                os.environ[k] = v

DEFAULT_PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "iceu-songpa21")
DEFAULT_LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# ------------------------------------------------------------------------------
# 2. ADC (Application Default Credentials, 애플리케이션 기본 사용자 인증 정보) 진단 및 초기화
# ------------------------------------------------------------------------------
def check_adc_credentials():
    """ADC 자격 증명 유효성을 사전 확인합니다."""
    try:
        creds, proj = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        return True, proj or DEFAULT_PROJECT_ID, None
    except DefaultCredentialsError as e:
        return False, None, str(e)
    except Exception as e:
        return False, None, str(e)

client = None

def get_genai_client():
    """ADC(애플리케이션 기본 사용자 인증 정보) 기반 GenAI 클라이언트를 반환합니다."""
    global client
    if client is not None:
        return client

    proj = os.environ.get("GOOGLE_CLOUD_PROJECT", DEFAULT_PROJECT_ID)
    loc = os.environ.get("GOOGLE_CLOUD_LOCATION", DEFAULT_LOCATION)

    # 1. ADC 기반 초기화 (권장: capture.png 참조)
    has_adc, detected_proj, err = check_adc_credentials()
    if has_adc:
        try:
            client = genai.Client(
                vertexai=True,
                project=detected_proj or proj,
                location=loc
            )
            print(f"[INFO] ✅ GenAI Client initialized successfully with ADC.")
            print(f"       Project: {detected_proj or proj} | Location: {loc}")
            return client
        except Exception as init_err:
            print(f"[WARN] Failed to initialize Vertex AI client with ADC: {init_err}")

    # 2. 보조: 환경변수 GEMINI_API_KEY가 제공된 경우의 Fallback
    current_key = os.environ.get("GEMINI_API_KEY", "")
    if current_key:
        try:
            client = genai.Client(api_key=current_key)
            print("[INFO] Fallback to GEMINI_API_KEY client.")
            return client
        except Exception as key_err:
            print(f"[WARN] Failed to initialize client with GEMINI_API_KEY: {key_err}")

    return None

SUPPORTED_MODELS = [
    {
        "id": "gemini-2.5-flash",
        "name": "Gemini 2.5 Flash",
        "label": "사고 모델 (2.5 Flash)",
        "description": "Google Cloud Model API 최신 플래그십 사고 모델 (도감 심층 분석 및 배틀 전략)",
        "isDefault": True,
        "isAgent": False
    },
    {
        "id": "gemini-2.0-flash",
        "name": "Gemini 2.0 Flash",
        "label": "고속 검색 (2.0 Flash)",
        "description": "초고속 응답 속도 및 효율적인 정보 조회를 위한 고속 모델",
        "isDefault": False,
        "isAgent": False
    },
    {
        "id": "gemini-1.5-flash",
        "name": "Gemini 1.5 Flash",
        "label": "안정 모델 (1.5 Flash)",
        "description": "장기 검증된 안정적인 도감 데이터 조회 모델",
        "isDefault": False,
        "isAgent": False
    }
]

def resolve_target_model(model_id: Optional[str]) -> str:
    """클라이언트 요청 모델 ID를 Vertex AI 실제 배포 모델로 안전하게 매핑합니다."""
    if not model_id:
        return "gemini-2.5-flash"
    mapping = {
        "gemini-3.8-flash": "gemini-2.5-flash",
        "gemini-3.7-flash": "gemini-2.0-flash",
        "antigravity-preview-05-2026": "gemini-2.5-flash",
        "gemini-2.5-flash": "gemini-2.5-flash",
        "gemini-2.0-flash": "gemini-2.0-flash",
        "gemini-1.5-flash": "gemini-1.5-flash"
    }
    return mapping.get(model_id, "gemini-2.5-flash")

app = FastAPI(
    title="Gemini Chatbot API (Cloud Run - ADC Mode)",
    description="Google Cloud Run 서버리스 컨테이너 환경의 ADC(애플리케이션 기본 사용자 인증 정보) 기반 Gemini 챗봇 백엔드",
    version="2.1.0"
)

class ChatRequest(BaseModel):
    input: str
    model: Optional[str] = "gemini-3.8-flash"
    previousInteractionId: Optional[str] = None

# Cloud Run 헬스체크 및 스타트업 프로브용 엔드포인트
@app.get("/health")
async def health_check():
    has_adc, proj, _ = check_adc_credentials()
    return {
        "status": "healthy",
        "service": "gemini-chatbot-cloud-run2-adc",
        "environment": "cloud-run",
        "authMode": "ADC (Application Default Credentials)",
        "adcReady": has_adc,
        "projectId": proj or DEFAULT_PROJECT_ID
    }

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    fav_path = public_dir / "nurse_joy.jpg"
    if fav_path.exists():
        return FileResponse(fav_path, media_type="image/jpeg")
    return JSONResponse(content={"status": "ok"})

@app.get("/api/status")
async def get_status():
    has_adc, proj, err = check_adc_credentials()
    cli = get_genai_client()
    has_auth = (cli is not None)

    diagnostic_msg = "ADC 인증 정상 작동 중"
    if not has_auth:
        diagnostic_msg = (
            "ADC 자격 증명이 감지되지 않았습니다. 로컬 개발 환경이라면 터미널에서 "
            "'gcloud auth application-default login'을 실행하거나, "
            "capture.png의 setup_adc.sh를 실행하세요."
        )

    return {
        "status": "ok",
        "platform": "Google Cloud Run (ADC Keyless Architecture)",
        "authMode": "ADC (애플리케이션 기본 사용자 인증 정보)",
        "hasAuth": has_auth,
        "hasApiKey": has_auth,  # 기존 프론트엔드 호환성 유지
        "hasAdc": has_adc,
        "projectId": proj or DEFAULT_PROJECT_ID,
        "location": os.environ.get("GOOGLE_CLOUD_LOCATION", DEFAULT_LOCATION),
        "defaultModel": "gemini-3.8-flash",
        "models": SUPPORTED_MODELS,
        "diagnostic": diagnostic_msg,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    user_input = req.input.strip()
    if not user_input:
        raise HTTPException(status_code=400, detail="질문 내용을 입력해주세요.")
    if len(user_input) > 10000:
        raise HTTPException(status_code=400, detail="질문 길이는 최대 10,000자까지 가능합니다.")

    genai_cli = get_genai_client()
    if not genai_cli:
        raise HTTPException(
            status_code=500,
            detail=(
                "Google Cloud ADC(애플리케이션 기본 사용자 인증 정보)가 구성되어 있지 않습니다. "
                "로컬 환경에서는 'gcloud auth application-default login'을 실행해주시고, "
                "Cloud Run 환경에서는 서비스 계정에 'roles/aiplatform.user' 권한이 부여되었는지 확인해주세요."
            )
        )

    selected_model_id = req.model or "gemini-2.5-flash"
    target_model = resolve_target_model(selected_model_id)

    try:
        # 간호순 누나 페르소나 시스템 프롬프트
        nurse_joy_prompt = (
            "당신은 포켓몬스터 1세대 관동지방 포켓몬 센터의 상냥하고 싹싹한 '간호순 누나(Nurse Joy)'이자 최고의 포켓몬 도감 길잡이입니다.\n"
            "- 트레이너를 항상 '트레이너님'이라고 부르며, 다정하고 친절하며 전문적인 어조(~해요, ~답니다, 럭키와 함께 도와드릴게요! 등)로 답변하세요.\n"
            "- 포켓몬의 진화 조건, 추천 기술 배치, 배틀 타입 상성, 체육관 관장(웅이, 이슬이 등) 공략법, 포켓몬 건강 및 회복 팁을 명쾌하고 상세하게 설명하세요.\n"
            "- 답변 중간에 포켓볼(🔴⚪), 하트(💖), 번개(⚡), 별(✨) 등 포켓몬 관련 이모지를 귀엽고 따뜻하게 곁들여주세요."
        )

        from google.genai import types
        config = types.GenerateContentConfig(
            system_instruction=nurse_joy_prompt,
            temperature=0.7,
        )

        response = genai_cli.models.generate_content(
            model=target_model,
            contents=user_input,
            config=config
        )
        reply_text = response.text or ""
        interaction_id = f"adc-{int(time.time()*1000)}"

        return {
            "reply": reply_text,
            "interactionId": interaction_id,
            "model": selected_model_id,
            "targetModel": target_model,
            "hasThought": False,
            "authMode": "ADC",
            "toolsUsed": {
                "googleSearch": False,
                "codeExecution": False
            },
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Chat error [{selected_model_id}]:", e)
        raise HTTPException(status_code=500, detail=f"API 처리 중 오류가 발생했습니다: {str(e)}")

# 정적 파일 서빙 (public 디렉터리)
public_dir = Path(__file__).parent / "public"
if public_dir.exists():
    app.mount("/", StaticFiles(directory=str(public_dir), html=True), name="static")

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))
    has_adc, proj, _ = check_adc_credentials()
    print("================================================================")
    print(" [START] Gemini Chatbot Server (Cloud Run - ADC Mode)")
    print(f" URL: http://{host}:{port}")
    print(" Auth Mode: Application Default Credentials (ADC)")
    print(f" ADC Detected: {has_adc} (Project: {proj or DEFAULT_PROJECT_ID})")
    print(f" Location: {DEFAULT_LOCATION}")
    print(" Tools: code_execution, google_search, url_context")
    print("================================================================")
    uvicorn.run(app, host=host, port=port, log_level="info")
