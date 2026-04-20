"""
Shared Groq client.
Provider-agnostic interface used across routers (generate_text, generate_json, generate_grounded_json).
"""

import json
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


# Standing instruction injected into every grounded call. Keeps the model from
# inventing numbers: unsupported fields must be null and listed under data_gaps.
GROUNDING_CONTRACT = """You are an analyst that answers STRICTLY from the CONTEXT block below.

Hard rules:
1. Use ONLY facts present in CONTEXT. Do NOT use outside knowledge for numeric claims.
2. If a requested field cannot be supported by CONTEXT, set its value to null and add an entry to `data_gaps` explaining what was missing.
3. Every element of any `rationale`, `pros`, `cons`, or similar list MUST be an object with keys `text` and `source`, where `source` names the CONTEXT path that backs the claim (e.g. "ratios.profitability.roe", "news[2]", "peers.median_pe"). No bare strings.
4. Include a top-level `confidence` field: "low" | "medium" | "high" — "high" only if every numeric field is directly present in CONTEXT.
5. Respond with a single JSON object. No markdown, no commentary.
"""


def is_available() -> bool:
    return _client is not None


def generate_text(
    prompt: str,
    max_tokens: int = 2048,
    system: str | None = None,
    temperature: float = 0.7,
) -> str:
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
        temperature=temperature,
    )
    return resp.choices[0].message.content or ""


def generate_json(
    prompt: str,
    max_tokens: int = 2048,
    system: str | None = None,
    temperature: float = 0.2,
) -> str:
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
        temperature=temperature,
    )
    return resp.choices[0].message.content or "{}"


def generate_grounded_json(
    task: str,
    context: dict,
    schema_description: str,
    max_tokens: int = 2048,
    temperature: float = 0.2,
) -> dict:
    """
    Run an analytical JSON task that MUST cite fields from the provided context.

    Args:
        task: what to produce, in natural language
        context: a dict of real data (ratios, news, peers, etc.) that becomes the
                 sole source of truth for the model
        schema_description: a human-readable description of required JSON keys

    Returns the parsed JSON dict. On parse failure returns {} (caller handles fallback).
    """
    if not _client:
        raise RuntimeError("GROQ_API_KEY not configured")

    context_json = json.dumps(context, indent=2, default=str)
    user_prompt = (
        f"TASK:\n{task}\n\n"
        f"REQUIRED SCHEMA:\n{schema_description}\n\n"
        f"CONTEXT (your only source of truth):\n```json\n{context_json}\n```\n"
    )

    messages = [
        {"role": "system", "content": GROUNDING_CONTRACT},
        {"role": "user", "content": user_prompt},
    ]
    resp = _client.chat.completions.create(
        model=MODEL,
        messages=messages,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
        temperature=temperature,
    )
    raw = resp.choices[0].message.content or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.error("generate_grounded_json: invalid JSON. first 500 chars=%s", raw[:500])
        return {}


def verify_claims(output: dict, context: dict, max_tokens: int = 1024) -> dict:
    """
    Second-pass verifier. Hands the output + context back to the model and asks
    it to flag/remove unsupported claims. Returns a dict:
      {"verified": <output with unsupported rationale items removed>,
       "removed": [ {text, reason}, ... ]}
    """
    if not _client:
        return {"verified": output, "removed": []}

    system = (
        "You are a strict fact-checker. You receive a CLAIM object and a CONTEXT object. "
        "Your job: for every item inside any rationale/pros/cons list in CLAIM, decide if the "
        "`text` is directly supported by the path named in `source` within CONTEXT. "
        "Return JSON: {\"verified\": <CLAIM with unsupported list items removed>, "
        "\"removed\": [{\"text\":..., \"reason\":...}, ...]}. "
        "Do not alter numeric fields; only prune unsupported list items. Preserve structure."
    )
    user = (
        f"CLAIM:\n```json\n{json.dumps(output, default=str)}\n```\n\n"
        f"CONTEXT:\n```json\n{json.dumps(context, default=str)}\n```"
    )
    try:
        resp = _client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        parsed = json.loads(resp.choices[0].message.content or "{}")
        if "verified" not in parsed:
            return {"verified": output, "removed": []}
        return parsed
    except Exception as e:
        logger.warning("verify_claims failed, returning unverified output: %s", e)
        return {"verified": output, "removed": []}
