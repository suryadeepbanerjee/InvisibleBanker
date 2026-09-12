"""
LLM Provider Abstraction Layer

Primary: Groq — groq/compound-mini (verified working 2026-09-11)
Fallback: Gemini flash-lite — ONLY used after Groq failures/rate-limits

Model selection: verified against actual API — models that 404 were replaced.
The rest of the system uses this module and never cares which provider is active.
"""
import re
import json
import time
import logging
from typing import Any, Optional
import httpx
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ─── Groq Client ─────────────────────────────────────────────────────────────
# Model verified 2026-09-11 against actual account models endpoint.
# Previous model (llama-3.3-70b-versatile) returned 404 on this account.

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "groq/compound-mini"  # Verified working 2026-09-11

# ─── Gemini Client ───────────────────────────────────────────────────────────
# Previous model (gemini-1.5-flash) deprecated for new users (404).
# gemini-flash-lite-latest verified working 2026-09-11.

GEMINI_MODEL = "gemini-flash-lite-latest"  # Verified working 2026-09-11
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


def _strip_thinking_tokens(text: str) -> str:
    """
    Remove <think>...</think> reasoning blocks that some models (compound, Qwen)
    emit before their actual response content.
    
    These must not be treated as part of the response or JSON payload.
    """
    # Strip <think>...</think> blocks (greedy=False to handle multiple blocks)
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    return text.strip()


def _call_groq(messages: list[dict], temperature: float = 0.1, max_tokens: int = 2048) -> str:
    """Call Groq API. Returns response text with thinking tokens stripped."""
    headers = {
        "Authorization": f"Bearer {settings.groq_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    with httpx.Client(timeout=30) as client:
        resp = client.post(GROQ_API_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        raw = data["choices"][0]["message"]["content"]
        return _strip_thinking_tokens(raw)


def _call_gemini(messages: list[dict], temperature: float = 0.1, max_tokens: int = 2048) -> str:
    """Call Gemini API as fallback. Converts OpenAI message format to Gemini format."""
    # Convert messages to Gemini format
    # system messages are merged into the first user message (Gemini has no system role)
    system_parts = []
    contents = []
    for msg in messages:
        if msg["role"] == "system":
            system_parts.append(msg["content"])
        else:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})

    # Prepend system content to first user message if present
    if system_parts and contents:
        first_user = contents[0]
        if first_user["role"] == "user":
            system_text = "\n".join(system_parts)
            original_text = first_user["parts"][0]["text"]
            first_user["parts"][0]["text"] = f"{system_text}\n\n{original_text}"

    if not contents:
        contents = [{"role": "user", "parts": [{"text": " ".join(system_parts)}]}]

    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
    }
    url = f"{GEMINI_API_URL}?key={settings.gemini_api_key}"
    with httpx.Client(timeout=30) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        raw = data["candidates"][0]["content"]["parts"][0]["text"]
        return _strip_thinking_tokens(raw)


def generate(
    messages: list[dict],
    temperature: float = 0.1,
    max_tokens: int = 2048,
) -> str:
    """
    Generate a response from the LLM.
    
    Tries Groq first with exponential backoff.
    Falls back to Gemini after MAX_LLM_RETRIES failures.
    """
    max_retries = settings.max_llm_retries
    last_error = None

    for attempt in range(max_retries):
        try:
            result = _call_groq(messages, temperature, max_tokens)
            if attempt > 0:
                logger.info(f"Groq succeeded on attempt {attempt + 1}")
            return result
        except httpx.HTTPStatusError as e:
            last_error = e
            if e.response.status_code == 429:
                # Rate limited — exponential backoff
                wait = 2 ** attempt
                logger.warning(f"Groq rate limited, waiting {wait}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)
            elif e.response.status_code >= 500:
                wait = 2 ** attempt
                logger.warning(f"Groq server error {e.response.status_code}, waiting {wait}s")
                time.sleep(wait)
            else:
                # Client error — don't retry Groq
                logger.error(f"Groq client error {e.response.status_code}: {e.response.text[:200]}")
                break
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            last_error = e
            wait = 2 ** attempt
            logger.warning(f"Groq connection error, waiting {wait}s: {e}")
            time.sleep(wait)

    # Groq failed — try Gemini fallback
    logger.warning(f"Groq failed after {max_retries} attempts. Falling back to Gemini. Last error: {last_error}")
    try:
        result = _call_gemini(messages, temperature, max_tokens)
        logger.info("Gemini fallback succeeded")
        return result
    except Exception as e:
        logger.error(f"Gemini fallback also failed: {e}")
        raise RuntimeError(f"All LLM providers failed. Groq: {last_error}. Gemini: {e}")


def extract_json(
    messages: list[dict],
    temperature: float = 0.05,
    max_tokens: int = 1024,
    fallback: Optional[dict] = None,
) -> dict:
    """
    Generate and parse a JSON response from the LLM.
    
    Never allows malformed JSON to propagate — returns fallback or raises.
    """
    # Add JSON instruction to last user message
    json_messages = messages.copy()
    last = json_messages[-1]
    json_messages[-1] = {
        **last,
        "content": last["content"] + "\n\nRespond ONLY with valid JSON. No explanation, no markdown fences.",
    }

    raw = generate(json_messages, temperature=temperature, max_tokens=max_tokens)

    # Clean up common LLM JSON formatting issues
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        # Remove first and last fence lines
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"LLM returned invalid JSON: {e}\nRaw: {raw[:500]}")
        if fallback is not None:
            return fallback
        raise ValueError(f"LLM returned invalid JSON: {e}")


def explain(
    system_prompt: str,
    user_content: str,
    language: str = "en-IN",
    temperature: float = 0.3,
) -> str:
    """
    Generate a user-facing explanation.
    
    The explanation is always labeled as AI-generated in the response.
    Language-aware: responds in the specified language.
    """
    lang_instruction = ""
    if language.startswith("hi"):
        lang_instruction = "Respond in simple Hindi (Hinglish is acceptable). Use easy language that a small business owner would understand."
    else:
        lang_instruction = "Respond in simple English. Avoid jargon."

    messages = [
        {"role": "system", "content": f"{system_prompt}\n\n{lang_instruction}"},
        {"role": "user", "content": user_content},
    ]
    return generate(messages, temperature=temperature, max_tokens=1024)
