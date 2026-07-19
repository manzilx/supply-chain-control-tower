"""Shared LLM wrapper for single-turn prose generation.

Every AI feature in the app (award rationale, follow-up emails, vendor briefings,
risk mitigations, simulation narrative, weekly-plan synthesis, BOM auto-fill,
spec request, /api/explain) builds on top of this module.

Tool-calling lives in app/agent.py — this is the boring "give me prose" path.

Design:
- Reads XAI_API_KEY at call time (so env changes take effect without restart)
- Returns None on any failure → caller falls back to its template
- Optional JSON mode for features that need structured output
- All requests are stateless (no caching here; the wrapper is the seam if we
  want to add it later)
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional
from urllib import error, request


XAI_BASE = os.getenv("XAI_BASE_URL", "https://api.x.ai/v1").rstrip("/")
XAI_MODEL = os.getenv("XAI_MODEL", "grok-4-1-fast-reasoning")
XAI_REASONING_EFFORT = os.getenv("XAI_REASONING_EFFORT", "").strip()


def is_enabled() -> bool:
    return bool(os.getenv("XAI_API_KEY", "").strip())


# --- Call stats (powers /api/ai/status) --------------------------------------

_STATS: dict[str, Any] = {
    "calls": 0,
    "errors": 0,
    "last_latency_ms": None,
    "last_at": None,
}


def record_call(latency_ms: float, ok: bool) -> None:
    _STATS["calls"] += 1
    if not ok:
        _STATS["errors"] += 1
    _STATS["last_latency_ms"] = round(latency_ms, 1)
    from datetime import datetime, timezone
    _STATS["last_at"] = datetime.now(timezone.utc).isoformat()


def get_stats() -> dict:
    return dict(_STATS)


def grok_chat(
    system: str,
    user: str,
    *,
    json_mode: bool = False,
    max_tokens: int = 800,
    temperature: float = 0.3,
    timeout: int = 30,
) -> Optional[str]:
    """Single-turn Grok call. Returns text content or None on any failure.

    Set json_mode=True for features that need structured output (the wrapper
    instructs the model to return valid JSON). Callers still need to json.loads
    the result themselves and handle parse failures.
    """

    api_key = os.getenv("XAI_API_KEY", "").strip()
    if not api_key:
        return None

    if json_mode:
        system = (
            system
            + "\n\nReturn ONLY a single valid JSON object. No prose, no markdown fences."
        )

    body: dict[str, Any] = {
        "model": XAI_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if XAI_REASONING_EFFORT:
        body["reasoning_effort"] = XAI_REASONING_EFFORT

    req = request.Request(
        url=f"{XAI_BASE}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    import time as _time
    t0 = _time.perf_counter()
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            parsed = json.loads(resp.read().decode("utf-8"))
        record_call((_time.perf_counter() - t0) * 1000, ok=True)
        return (
            parsed.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
            or None
        )
    except (error.URLError, error.HTTPError, TimeoutError, json.JSONDecodeError, KeyError, ValueError):
        record_call((_time.perf_counter() - t0) * 1000, ok=False)
        return None


def grok_json(system: str, user: str, *, max_tokens: int = 800, timeout: int = 30) -> Optional[dict]:
    """Convenience: call grok_chat in JSON mode and parse the result.

    Returns None if the call failed OR if the result wasn't valid JSON.
    """

    raw = grok_chat(system, user, json_mode=True, max_tokens=max_tokens, timeout=timeout)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to salvage if model wrapped in fences despite the instruction
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].lstrip()
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                pass
        return None
