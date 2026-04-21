"""
Gemini API wrapper.
Handles initialization, prompt templates, and async execution.
"""
import asyncio
import logging
from typing import Optional

import google.generativeai as genai

from config import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Prompt templates
# ----------------------------------------------------------------------

_ANALYSIS_PROMPT = """\
You are an expert DevOps and SRE Engineer.
Analyze the provided AmneziaWG logs and system metrics.

1. Identify critical errors, handshake issues, or resource bottlenecks.
2. Evaluate system health and stability.
3. Provide technical recommendations for fixes or optimizations.

Be concise and technical. Respond in English only.

DATA:
{metrics}

LOGS:
{logs}
"""

_CHAT_PROMPT = """\
You are a helpful DevOps assistant.
Answer technical questions concisely. Respond in English only.

User: {user_text}
Assistant:"""

# ----------------------------------------------------------------------
# Initialization
# ----------------------------------------------------------------------

_model: Optional[genai.GenerativeModel] = None


def init() -> None:
    """
    Initialize Gemini. Called once at startup from main.py.
    Raises on missing API key.
    """
    global _model
    if not GEMINI_API_KEY:
        raise EnvironmentError("GEMINI_API_KEY is not set")

    genai.configure(api_key=GEMINI_API_KEY)
    _model = genai.GenerativeModel(GEMINI_MODEL)
    logger.info("Gemini initialized | model=%s", GEMINI_MODEL)


def _get_model() -> genai.GenerativeModel:
    if _model is None:
        raise RuntimeError("Gemini is not initialized. Call init() first.")
    return _model


# ----------------------------------------------------------------------
# Core async runner
# ----------------------------------------------------------------------

async def _generate(
    prompt: str,
    max_tokens: int = 1000,
    temperature: float = 0.2,
    timeout: float = 30.0,
) -> str:
    """
    Run Gemini generation in a thread pool (SDK is synchronous).
    Returns the response text or an error message.
    """
    model = _get_model()
    loop = asyncio.get_event_loop()

    try:
        response = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: model.generate_content(
                    prompt,
                    generation_config={
                        "max_output_tokens": max_tokens,
                        "temperature": temperature,
                    },
                ),
            ),
            timeout=timeout,
        )
        return response.text

    except asyncio.TimeoutError:
        logger.warning("Gemini timeout after %.1fs", timeout)
        return "⚠️ AI did not respond (timeout). Try again later."

    except Exception as e:
        logger.error("Gemini error: %s", e)
        return f"⚠️ AI error: {str(e)[:120]}"


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------

async def analyze_logs(logs: str, metrics: str) -> str:
    """
    Analyze VPN logs and system metrics.
    Used by /analyze command.
    """
    prompt = _ANALYSIS_PROMPT.format(logs=logs, metrics=metrics)
    return await _generate(prompt, max_tokens=600, temperature=0.2)


async def chat(user_text: str) -> str:
    """
    Answer a free-form DevOps question.
    Used by the message handler.
    """
    prompt = _CHAT_PROMPT.format(user_text=user_text)
    return await _generate(prompt, max_tokens=1000, temperature=0.5)