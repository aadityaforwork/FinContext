"""
Shared Groq client.
Provider-agnostic interface used across routers (generate_text, generate_json).
"""

import os
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

_client = None
if GROQ_API_KEY:
    try:
        from groq import Groq
        _client = Groq(api_key=GROQ_API_KEY)
        logger.info(f"Groq client enabled (model={MODEL}).")
    except Exception as e:
        logger.error(f"Failed to initialize Groq client: {e}")
        _client = None
else:
    logger.warning("GROQ_API_KEY not set — AI features will be disabled.")


def is_available() -> bool:
    return _client is not None


def generate_text(prompt: str, max_tokens: int = 2048, system: str | None = None) -> str:
    """Synchronous text generation."""
    if not _client:
        raise RuntimeError("GROQ_API_KEY not configured")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    resp = _client.chat.completions.create(
        model=MODEL,
        messages=messages,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content or ""


def generate_json(prompt: str, max_tokens: int = 2048, system: str | None = None) -> str:
    """Uses Groq's native JSON mode — guaranteed valid JSON string."""
    if not _client:
        raise RuntimeError("GROQ_API_KEY not configured")

    sys_msg = (system + "\n\n" if system else "") + "Respond with a single valid JSON object. No markdown, no commentary."
    messages = [
        {"role": "system", "content": sys_msg},
        {"role": "user", "content": prompt},
    ]

    resp = _client.chat.completions.create(
        model=MODEL,
        messages=messages,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content or "{}"
