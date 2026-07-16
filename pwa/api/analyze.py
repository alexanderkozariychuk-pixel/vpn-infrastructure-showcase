from fastapi import APIRouter, Depends
from concurrent.futures import ThreadPoolExecutor
import asyncio
from openai import AsyncOpenAI
from auth.jwt import require_auth
from services.net_manager import get_analysis_data
from config import OPENROUTER_API_KEY

router = APIRouter()
executor = ThreadPoolExecutor()

_PROMPT = """You are a Senior SRE analyzing a distributed VPN infrastructure.

CONTEXT:
- Bot runs in Docker on the app server
- Logs collected via SSH from the foreign exit node
- Architecture: Client → AmneziaWG (RU entry) → AmneziaWG backbone → foreign exit node → Internet

STRICT RULES:
1. DO NOT suggest installing journalctl locally
2. Plain text only, no markdown headers
3. Under 200 words
4. Structure:
   STATS: (metrics summary)
   ISSUES: (what is broken or concerning)
   FIX: (exact actionable commands if needed)

Metrics:
{metrics}

Logs:
{logs}

Respond in English."""


async def _analyze(logs: str, metrics: str) -> str:
    client = AsyncOpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1",
        timeout=60.0,
    )
    response = await client.chat.completions.create(
        model="google/gemini-2.0-flash-001",
        messages=[{
            "role": "user",
            "content": _PROMPT.format(logs=logs, metrics=metrics)
        }],
        max_tokens=600,
        temperature=0.2,
        extra_headers={
            "HTTP-Referer": "http://localhost",
            "X-Title": "VPN SRE PWA",
        }
    )
    return response.choices[0].message.content


@router.post("/api/analyze")
async def analyze(_: dict = Depends(require_auth)):
    loop = asyncio.get_running_loop()
    logs, metrics = await loop.run_in_executor(executor, get_analysis_data)
    result = await _analyze(logs, metrics)
    return {
        "ok": True,
        "analysis": result,
    }
