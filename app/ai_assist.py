from __future__ import annotations

import json
import os
from typing import Any, Dict, List
from urllib import error, request

from .schemas import AgentRequest, RiskRecord


def _fallback_response(payload: AgentRequest, risks: List[RiskRecord]) -> str:
    if not risks:
        return (
            "No major short-term disruptions were detected in the provided scenario. "
            "Keep weekly watch on critical items, supplier OTD, and demand changes against the 90-day horizon."
        )

    top = risks[0]
    action_lines = []
    for risk in risks[:3]:
        action_lines.append(
            f"- {risk.title}: {risk.summary} Owner: {risk.owner}."
        )

    return (
        f"Priority call for {payload.company.company_name}: focus first on {top.title.lower()}. "
        f"This is the strongest near-term threat to project execution given the current inventory, supplier, and PO signals.\n\n"
        f"Recommended operating brief:\n" + "\n".join(action_lines) + "\n\n"
        f"Answer to the planner question: {payload.ask}"
    )


def _build_prompt(payload: AgentRequest, risks: List[RiskRecord]) -> str:
    concise_risks: List[Dict[str, Any]] = [
        {
            "title": risk.title,
            "severity": risk.severity,
            "score": risk.score,
            "summary": risk.summary,
            "owner": risk.owner,
        }
        for risk in risks[:6]
    ]
    return (
        "You are an AI supply-chain copilot for an engineering company. "
        "Write an executive-level response with:\n"
        "1. A short situation assessment\n"
        "2. The 3 most important actions for this week\n"
        "3. A note on where planning, procurement, and supplier quality should align\n\n"
        f"Company context:\n{json.dumps(payload.company.model_dump(), indent=2)}\n\n"
        f"Planner question:\n{payload.ask}\n\n"
        f"Top risks:\n{json.dumps(concise_risks, indent=2)}"
    )


def generate_ai_brief(payload: AgentRequest, risks: List[RiskRecord]) -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")

    if not api_key:
        return _fallback_response(payload, risks)

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a crisp, practical AI supply-chain advisor."},
            {"role": "user", "content": _build_prompt(payload, risks)},
        ],
        "temperature": 0.3,
    }

    req = request.Request(
        url=f"{base_url}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=20) as response:
            parsed = json.loads(response.read().decode("utf-8"))
        return (
            parsed.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
            or _fallback_response(payload, risks)
        )
    except (error.URLError, TimeoutError, json.JSONDecodeError, KeyError, ValueError):
        return _fallback_response(payload, risks)
