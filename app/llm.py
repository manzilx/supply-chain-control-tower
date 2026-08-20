"""Shared LLM wrapper — DeepSeek only.

Every AI feature (award rationale, follow-up emails, vendor briefings,
risk mitigations, simulation brief, weekly-plan synthesis, BOM auto-fill,
spec request, /api/explain) goes through this module.

Tool-calling lives in app/agent.py.

DEEPSEEK_API_KEY enables the model. Missing key or any HTTP failure →
callers use their deterministic template. No other LLM provider is wired.

Text, JSON mode and tool-calling are live on deepseek-v4-flash. Vision is
not — the model is text-only, so GRN photo extraction stays off by default
(see vision_enabled()).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional
from urllib import error, request


DEEPSEEK_BASE = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-flash"

# In-app key (Integrations page) overrides the process env for this process.
# None = no override; fall back to DEEPSEEK_API_KEY. Persisted under STATE_DIR
# (gitignored), never returned by /api/ai/status.
_RUNTIME_KEY: Optional[str] = None


def _key_path() -> Path:
    from .persistence import STATE_DIR
    return STATE_DIR / "deepseek.key"


def load_persisted_key() -> None:
    """Restore a key saved from the Integrations page. Called on startup."""
    global _RUNTIME_KEY
    path = _key_path()
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return
    if raw:
        _RUNTIME_KEY = raw


def reset_runtime_key() -> None:
    """Test helper: drop the in-memory override. Does not delete the file."""
    global _RUNTIME_KEY
    _RUNTIME_KEY = None


def set_api_key(api_key: str) -> str:
    """Save a DeepSeek key for this process and persist it. Returns the hint."""
    global _RUNTIME_KEY
    key = (api_key or "").strip()
    if len(key) < 8:
        raise ValueError("API key is too short")
    _RUNTIME_KEY = key
    path = _key_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(key + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return key_hint() or ""


def clear_api_key() -> None:
    """Remove the in-app key. Env DEEPSEEK_API_KEY (if set) becomes active again."""
    global _RUNTIME_KEY
    _RUNTIME_KEY = None
    try:
        _key_path().unlink()
    except OSError:
        pass


def key_hint() -> Optional[str]:
    key = _deepseek_key()
    if not key:
        return None
    return f"••••{key[-4:]}"


def configured_via() -> Optional[str]:
    if _RUNTIME_KEY:
        return "runtime"
    if os.getenv("DEEPSEEK_API_KEY", "").strip():
        return "env"
    return None


def _deepseek_key() -> str:
    if _RUNTIME_KEY:
        return _RUNTIME_KEY
    return os.getenv("DEEPSEEK_API_KEY", "").strip()


def provider_info() -> Optional[dict[str, str]]:
    if not _deepseek_key():
        return None
    return {
        "name": "deepseek",
        "source": "deepseek",
        "key": _deepseek_key(),
        "base": os.getenv("DEEPSEEK_BASE_URL", DEEPSEEK_BASE).rstrip("/"),
        "model": os.getenv("DEEPSEEK_MODEL", DEEPSEEK_MODEL).strip() or DEEPSEEK_MODEL,
    }


def is_enabled() -> bool:
    return provider_info() is not None


def vision_enabled() -> bool:
    """Off by default: deepseek-v4-flash is text-only.

    An image_url content part is rejected outright — HTTP 400 "unknown variant
    `image_url`, expected `text`" — so leaving this on would burn a round-trip
    per GRN photo and park the receipt in 'failed'/triage. Off means GRN capture
    takes the 'skipped' path instead, which is a first-class working path (the
    matcher still runs against manually-keyed lines — see store/extraction.py).

    Set DEEPSEEK_VISION=1 only when DEEPSEEK_BASE_URL/DEEPSEEK_MODEL point at a
    vision-capable OpenAI-compatible endpoint.
    """
    if not is_enabled():
        return False
    return os.getenv("DEEPSEEK_VISION", "").strip().lower() in ("1", "true", "yes")


def llm_source() -> str:
    return "deepseek" if is_enabled() else "deterministic"


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


def chat_completions(
    body: dict[str, Any],
    *,
    timeout: int = 30,
    info: Optional[dict[str, str]] = None,
) -> Optional[dict]:
    """POST /chat/completions on DeepSeek. Returns parsed JSON or None."""
    info = info or provider_info()
    if not info:
        return None
    payload = dict(body)
    payload.setdefault("model", info["model"])
    if "thinking" not in payload:
        payload["thinking"] = {"type": "disabled"}

    req = request.Request(
        url=f"{info['base']}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {info['key']}",
        },
        method="POST",
    )
    import time as _time
    t0 = _time.perf_counter()
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            parsed = json.loads(resp.read().decode("utf-8"))
        record_call((_time.perf_counter() - t0) * 1000, ok=True)
        return parsed
    except (error.URLError, error.HTTPError, TimeoutError, json.JSONDecodeError, KeyError, ValueError):
        record_call((_time.perf_counter() - t0) * 1000, ok=False)
        return None


def llm_chat(
    system: str,
    user: str,
    *,
    json_mode: bool = False,
    max_tokens: int = 800,
    temperature: float = 0.3,
    timeout: int = 30,
) -> Optional[str]:
    """Single-turn DeepSeek chat. None on any failure."""
    if not is_enabled():
        return None

    if json_mode:
        system = (
            system
            + "\n\nReturn ONLY a single valid JSON object. No prose, no markdown fences."
        )

    body: dict[str, Any] = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    parsed = chat_completions(body, timeout=timeout)
    if not parsed:
        return None
    return (
        parsed.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
        or None
    )


def llm_json(system: str, user: str, *, max_tokens: int = 800, timeout: int = 30) -> Optional[dict]:
    raw = llm_chat(system, user, json_mode=True, max_tokens=max_tokens, timeout=timeout)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
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


def vision_json(
    system: str,
    user: str,
    image_path: str,
    *,
    max_tokens: int = 1600,
    timeout: int = 60,
) -> Optional[dict]:
    """Vision JSON. None unless vision_enabled() — see the note there."""
    if not vision_enabled():
        return None

    import base64

    try:
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("ascii")
    except OSError:
        return None

    system = (
        system
        + "\n\nReturn ONLY a single valid JSON object. No prose, no markdown fences."
    )
    parsed = chat_completions(
        {
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                        },
                    ],
                },
            ],
            "temperature": 0.1,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        },
        timeout=timeout,
    )
    if not parsed:
        return None
    raw = (
        parsed.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].lstrip()
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                return None
        return None
