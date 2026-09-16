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
import uvicorn

# 1. 로컬 개발 환경용 .env 파일 수동 로드 (환경변수 보조)
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

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# 2. Secret Manager에서 GEMINI_API_KEY 자동 조회 시도 (미설정 시)
# Cloud Run 배포 시 --set-secrets GEMINI_API_KEY=GEMINI_API_KEY:latest 설정 시 바로 환경변수로 주입됩니다.
if not GEMINI_API_KEY:
    try:
        import importlib
        secretmanager_spec = importlib.util.find_spec("google.cloud.secretmanager")
        if secretmanager_spec is not None:
            from google.cloud import secretmanager
            sm_client = secretmanager.SecretManagerServiceClient()
            gcp_proj = os.environ.get("GOOGLE_CLOUD_PROJECT", "iceu-songpa21")
            secret_name = f"projects/{gcp_proj}/secrets/GEMINI_API_KEY/versions/latest"
            response = sm_client.access_secret_version(request={"name": secret_name})
            GEMINI_API_KEY = response.payload.data.decode("UTF-8").strip()
            os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY
            print(f"[INFO] Successfully loaded GEMINI_API_KEY from Secret Manager: {secret_name}")
        else:
            print("[INFO] 'google-cloud-secret-manager' not installed locally. Please set GEMINI_API_KEY in .env file.")
    except Exception as sm_err:
        print(f"[WARN] Failed to fetch secret from Secret Manager: {sm_err}")

# Google GenAI Client 초기화
client = None
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)

def get_genai_client():
    global client, GEMINI_API_KEY
    if client is not None:
        return client
    current_key = os.environ.get("GEMINI_API_KEY", "")
    if current_key:
        GEMINI_API_KEY = current_key
        client = genai.Client(api_key=current_key)
        return client
    return None

# 지원 도구 목록 (Code execution, Google search, URL context)
TOOLS = [
    {
        'type': 'code_execution',
    },
    {
        'type': 'google_search',
    },
    {
        'type': 'url_context',
    },
]

SUPPORTED_MODELS = [
    {
        "id": "gemini-3.8-flash",
        "name": "Gemini 3.8 Flash",
        "label": "사고 모델 (3.8 Flash)",
        "description": "최신 플래그십 사고 모델 (도구 지원: 구글 검색, 코드 실행, 웹 컨텍스트)",
        "isDefault": True,
        "isAgent": False
    },
    {
        "id": "gemini-3.7-flash",
        "name": "Gemini 3.7 Flash",
        "label": "사고 모델 (3.7 Flash)",
        "description": "고속 사고 모델 (균형 잡힌 추론 및 신속한 반응 속도)",
        "isDefault": False,
        "isAgent": False
    },
    {
        "id": "antigravity-preview-05-2026",
        "name": "Antigravity Preview",
        "label": "연구 에이전트 모델",
        "description": "심층 연구 및 원격 격리 환경 자율 추론 에이전트 모델",
        "isDefault": False,
        "isAgent": True
    }
]

app = FastAPI(
    title="Gemini Chatbot API (Cloud Run)",
    description="Google Cloud Run 서버리스 컨테이너 환경의 Gemini 챗봇 백엔드",
    version="2.0.0"
)

class ChatRequest(BaseModel):
    input: str
    model: Optional[str] = "gemini-3.8-flash"
    previousInteractionId: Optional[str] = None

# Cloud Run 헬스체크 및 스타트업 프로브용 엔드포인트
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "gemini-chatbot-cloud-run",
        "environment": "cloud-run"
    }

@app.get("/api/status")
async def get_status():
    cli = get_genai_client()
    return {
        "status": "ok",
        "platform": "Google Cloud Run",
        "defaultModel": "gemini-3.8-flash",
        "models": SUPPORTED_MODELS,
        "hasApiKey": bool(cli is not None),
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
            detail="서버에 GEMINI_API_KEY 환경변수가 설정되어 있지 않거나 유효하지 않습니다."
        )

    selected_model_id = req.model or "gemini-3.8-flash"
    model_info = next((m for m in SUPPORTED_MODELS if m["id"] == selected_model_id), SUPPORTED_MODELS[0])

    try:
        # 1. Interaction 생성 파라미터 구성 (포켓몬 도감 & 간호순 누나 페르소나 적용)
        nurse_joy_prompt = (
            "당신은 포켓몬스터 1세대 관동지방 포켓몬 센터의 상냥하고 싹싹한 '간호순 누나(Nurse Joy)'이자 최고의 포켓몬 도감 길잡이입니다.\n"
            "- 트레이너를 항상 '트레이너님'이라고 부르며, 다정하고 친절하며 전문적인 어조(~해요, ~답니다, 럭키와 함께 도와드릴게요! 등)로 답변하세요.\n"
            "- 포켓몬의 진화 조건, 추천 기술 배치, 배틀 타입 상성, 체육관 관장(웅이, 이슬이 등) 공략법, 포켓몬 건강 및 회복 팁을 명쾌하고 상세하게 설명하세요.\n"
            "- 답변 중간에 포켓볼(🔴⚪), 하트(💖), 번개(⚡), 별(✨) 등 포켓몬 관련 이모지를 귀엽고 따뜻하게 곁들여주세요."
        )
        kwargs: Dict[str, Any] = {
            "input": user_input,
            "background": True,
            "tools": TOOLS,
            "system_instruction": nurse_joy_prompt,
        }

        if model_info.get("isAgent"):
            kwargs["agent"] = selected_model_id
            kwargs["environment"] = {
                'type': 'remote',
                'network': 'disabled',
            }
        else:
            kwargs["model"] = selected_model_id

        if req.previousInteractionId:
            kwargs["previous_interaction_id"] = req.previousInteractionId

        # 2. Interactions create 호출
        interaction = genai_cli.interactions.create(**kwargs)
        interaction_id = interaction.id

        # 3. 비동기 폴링 루프 (Cloud Run 요청 타임아웃을 고려한 제어)
        start_time = time.time()
        timeout_seconds = 60.0
        poll_interval = 1.0

        while True:
            interaction = genai_cli.interactions.get(interaction_id)
            if interaction.status == "completed":
                break
            elif interaction.status == "failed":
                err_msg = str(getattr(interaction, "error", "Interaction execution failed"))
                raise HTTPException(status_code=502, detail=f"Gemini 처리 실패: {err_msg}")

            if time.time() - start_time > timeout_seconds:
                raise HTTPException(status_code=504, detail="Gemini 모델 응답 시간 초과 (60초)")

            await asyncio.sleep(poll_interval)
            # 폴링 주기를 점진적으로 조절
            poll_interval = min(poll_interval + 0.3, 3.0)

        reply_text = interaction.output_text or ""
        
        # steps 분석 (사고 과정 및 사용된 도구 파악)
        steps = getattr(interaction, "steps", []) or []
        step_types = [getattr(s, "type", "") for s in steps]
        has_thought = "thought" in step_types
        has_search = any("google_search" in st for st in step_types)
        has_code = any("code_execution" in st for st in step_types)

        return {
            "reply": reply_text,
            "interactionId": interaction.id,
            "model": selected_model_id,
            "hasThought": has_thought,
            "toolsUsed": {
                "googleSearch": has_search,
                "codeExecution": has_code
            },
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Interaction error [{selected_model_id}]:", e)
        raise HTTPException(status_code=500, detail=f"API 처리 중 오류가 발생했습니다: {str(e)}")

# 정적 파일 서빙 (public 디렉터리)
public_dir = Path(__file__).parent / "public"
if public_dir.exists():
    app.mount("/", StaticFiles(directory=str(public_dir), html=True), name="static")

if __name__ == "__main__":
    # Cloud Run은 환경변수 PORT를 주입하며 기본값은 8080입니다.
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))
    print("=========================================")
    print(" [START] Gemini Chatbot Server (Cloud Run)")
    print(f" URL: http://{host}:{port}")
    print(" Engine: google-genai client.interactions")
    print(" Tools: code_execution, google_search, url_context")
    print(f" API Key Loaded: {bool(get_genai_client())}")
    print("=========================================")
    uvicorn.run(app, host=host, port=port, log_level="info")
