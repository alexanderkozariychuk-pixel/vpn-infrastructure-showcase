import logging
from typing import Optional
from openai import AsyncOpenAI
from config import OPENROUTER_API_KEY, LLM_MODEL

logger = logging.getLogger(__name__)

_ANALYSIS_PROMPT = """
You are a Senior SRE. Analyze the data and provide a concise summary.
STRICT RULES:
1. DO NOT use markdown headers (# or ##) or bold blocks.
2. Use plain text and simple bullet points.
3. Keep it under 200 words.
4. Structure:
- STATS: (metrics summary)
- ISSUES: (what is broken)
- FIX: (exact commands)

Metrics: {metrics}
Logs: {logs}
Respond in English.
"""

_CHAT_PROMPT = "You are a DevOps assistant. Answer briefly, no markdown, no fluff. User: {user_text}"

# Глобальная переменная клиента
client: Optional[AsyncOpenAI] = None

def init() -> None:
    """
    Инициализация глобального клиента OpenAI.
    """
    global client
    if not OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY is not set")
        raise EnvironmentError("OPENROUTER_API_KEY is not set")

    try:
        # Убрали self, используем прямое присваивание в global client
        client = AsyncOpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
            timeout=60.0  # Тот самый важный таймаут
        )
        logger.info(f"LLM Engine initialized | model={LLM_MODEL}")
    except Exception as e:
        logger.error(f"Failed to initialize LLM client: {e}")
        raise

async def _generate(prompt: str, max_tokens: int, temperature: float) -> str:
    """
    Внутренняя функция для генерации ответа.
    """
    global client
    if client is None:
        logger.error("LLM Engine not initialized: client is None")
        return "⚠️ AI Error: Engine not initialized"
    
    try:
        response = await client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
            extra_headers={
                "HTTP-Referer": "http://localhost",
                "X-Title": "VPN SRE Bot"
            }
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"LLM Error during generation: {e}")
        return f"⚠️ AI Error: {str(e)[:100]}"

async def analyze_logs(logs: str, metrics: str) -> str:
    return await _generate(_ANALYSIS_PROMPT.format(logs=logs, metrics=metrics), 600, 0.2)

async def chat(user_text: str) -> str:
    return await _generate(_CHAT_PROMPT.format(user_text=user_text), 1000, 0.5)