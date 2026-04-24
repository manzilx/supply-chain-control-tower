"""Agent engine.

Three modes:
1. Deterministic router (default, always works, no API key) — keyword match
   the user message to tools, run them, format a response.
2. Claude tool-calling (opt-in via ANTHROPIC_API_KEY) — Claude plans tool
   calls, we execute, loop until it returns a final message.
3. OpenAI tool-calling is not implemented here to keep the module small;
   the deterministic path is the production-grade fallback.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from urllib import error, request

from .agent_tools import TOOLS, invoke
from .sample_data import build_demo_request
from .schemas import (
    AgentPersona,
    ChatReply,
    ChatTurn,
    ToolCallRecord,
)


MAX_CLAUDE_TURNS = 6  # tool-use loops before we force a final reply
CLAUDE_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
CLAUDE_BASE = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1").rstrip("/")


# --- Deterministic router ---------------------------------------------------


_PERSONA_KEYWORDS: List[Tuple[AgentPersona, List[str]]] = [
    ("expediting", ["expedit", "slip", "delay", "at risk", "red item", "nudge", "escalat", "follow up", "followup", "follow-up"]),
    ("logistics", ["shipment", "logistic", "transit", "customs", "port", "freight", "mode", "air freight"]),
    ("vendor_risk", ["vendor", "supplier", "scorecard", "alternate", "alternative", "single source", "single-source", "concentration"]),
    ("commercial", ["budget", "commercial", "saving", "spend", "cost", "overrun", "variance", "margin"]),
    ("planning", ["bom", "long-lead", "long lead", "long-lead", "procurement plan", "spec", "milestone", "project plan"]),
    ("sourcing", ["rfq", "quote", "award", "pr ", "requisition", "sourcing"]),
    ("reporting", ["weekly plan", "action plan", "this week", "priorities", "briefing", "daily brief"]),
]


def _detect_persona(message: str) -> AgentPersona:
    msg = message.lower()
    for persona, kws in _PERSONA_KEYWORDS:
        if any(kw in msg for kw in kws):
            return persona
    return "general"


def _extract_po_number(message: str) -> Optional[str]:
    match = re.search(r"\b([PS]?PO-\d{3,6}|SPO-\d{3,6})\b", message, re.IGNORECASE)
    if match:
        return match.group(0).upper()
    match = re.search(r"\bPR-\d{3,6}\b", message, re.IGNORECASE)
    return match.group(0).upper() if match else None


def _extract_vendor(message: str) -> Optional[str]:
    suppliers = [s.name for s in build_demo_request().suppliers]
    msg = message.lower()
    for name in suppliers:
        if name.lower() in msg:
            return name
    # Try partial first-word match
    for name in suppliers:
        first = name.split()[0].lower()
        if first in msg and len(first) > 3:
            return name
    return None


def _extract_project(message: str) -> Optional[str]:
    match = re.search(r"\bPRJ-[A-Z0-9-]+\b", message, re.IGNORECASE)
    return match.group(0).upper() if match else None


def _detect_tone(message: str) -> str:
    msg = message.lower()
    if any(k in msg for k in ["urgent", "critical", "asap", "48"]):
        return "urgent"
    if any(k in msg for k in ["firm", "strict", "recovery plan"]):
        return "firm"
    return "standard"


def _plan_tools(message: str, persona: AgentPersona) -> List[Tuple[str, dict]]:
    msg = message.lower()
    plan: List[Tuple[str, dict]] = []
    po = _extract_po_number(message)
    vendor = _extract_vendor(message)
    project = _extract_project(message)

    # Reporting
    if persona == "reporting" or any(k in msg for k in ["weekly plan", "action plan", "this week", "briefing"]):
        plan.append(("build_weekly_plan", {}))
        return plan

    # Expediting
    if persona == "expediting":
        plan.append(("get_expedite_queue", {}))
        if po:
            plan.append(("predict_slip", {"po_number": po}))
            if any(k in msg for k in ["email", "draft", "follow", "nudge", "escalat"]):
                plan.append(("draft_followup_email", {"po_number": po, "tone": _detect_tone(message)}))
        return plan

    # Vendor risk
    if persona == "vendor_risk":
        if vendor:
            plan.append(("get_vendor_scorecard", {"name": vendor}))
        else:
            plan.append(("list_vendors", {}))
        if any(k in msg for k in ["concentration", "single source", "single-source", "category"]):
            plan.append(("get_category_concentration", {}))
        return plan

    # Commercial
    if persona == "commercial":
        plan.append(("get_commercial_summary", {}))
        return plan

    # Logistics
    if persona == "logistics":
        plan.append(("get_logistics_queue", {}))
        if po and any(k in msg for k in ["mode", "freight", "air", "sea", "road"]):
            plan.append(("recommend_mode", {"po_ref": po}))
        return plan

    # Planning
    if persona == "planning":
        if project:
            plan.append(("get_procurement_plan", {"project_id": project}))
        else:
            plan.append(("list_projects", {}))
            plan.append(("get_procurement_plan", {}))
        return plan

    # Sourcing
    if persona == "sourcing":
        plan.append(("get_open_prs", {}))
        plan.append(("get_open_rfqs", {}))
        return plan

    # General — top risks + weekly plan excerpt
    plan.append(("get_top_risks", {}))
    plan.append(("build_weekly_plan", {}))
    return plan


def _format_reply(message: str, persona: AgentPersona, calls: List[ToolCallRecord]) -> str:
    if not calls:
        return "I couldn't match that to any of my tools. Try asking about the weekly plan, vendor scorecards, expediting, commercial savings, or logistics."

    lines: List[str] = []
    # Headline based on persona
    persona_blurb = {
        "expediting": "Expediting view:",
        "logistics": "Logistics view:",
        "vendor_risk": "Vendor intelligence:",
        "commercial": "Commercial:",
        "planning": "Planning:",
        "sourcing": "Sourcing:",
        "reporting": "This week's plan:",
        "general": "Here's what I'm seeing:",
    }
    lines.append(persona_blurb[persona])
    lines.append("")

    for c in calls:
        lines.append(f"• {c.output_summary}")

    # Drill-down hints
    hints: List[str] = []
    if persona == "expediting":
        hints.append("Open `/expediting` for the full queue and to draft emails in-line.")
    elif persona == "logistics":
        hints.append("Open `/logistics` for stage-by-stage tracking and mode recommendations.")
    elif persona == "vendor_risk":
        hints.append("Open `/vendors` for scorecards, alternates, and concentration analysis.")
    elif persona == "commercial":
        hints.append("Open `/commercial` for the project-level budget vs awarded rollup.")
    elif persona == "planning":
        hints.append("Open `/projects` for BOMs and procurement plans.")
    elif persona == "sourcing":
        hints.append("Open `/sourcing` to issue RFQs, compare quotes, and award.")
    elif persona == "reporting":
        hints.append("Open `/overview` for the weekly plan cards and KPI snapshot.")

    # If a weekly plan was invoked, include top items inline
    for c in calls:
        if c.tool == "build_weekly_plan" and c.output_preview and isinstance(c.output_preview, dict):
            plan_dict = c.output_preview
            items = plan_dict.get("items") or []
            if items:
                lines.append("")
                lines.append("Top actions:")
                for i in items[:4]:
                    lines.append(
                        f"  [{i.get('priority')}] {i.get('title')} — {i.get('why')[:120]}"
                    )

    if hints:
        lines.append("")
        lines.extend(hints)

    return "\n".join(lines)


def dispatch_deterministic(message: str) -> ChatReply:
    persona = _detect_persona(message)
    plan = _plan_tools(message, persona)
    calls: List[ToolCallRecord] = []
    for name, args in plan:
        try:
            calls.append(invoke(name, args))
        except Exception as e:  # noqa: BLE001
            calls.append(
                ToolCallRecord(
                    tool=name,
                    input=args,
                    output_summary=f"Tool errored: {e}",
                    output_preview=None,
                )
            )

    reply_text = _format_reply(message, persona, calls)
    return ChatReply(
        reply=reply_text,
        tool_calls=calls,
        persona=persona,
        source="deterministic",
        generated_at=datetime.now(timezone.utc),
    )


# --- Claude path ------------------------------------------------------------


_SYSTEM_PROMPT = (
    "You are the AI Command Center for an engineering / EPC supply chain control tower. "
    "You have tool access to procurement, vendor intelligence, expediting, logistics, "
    "commercial rollups, procurement plans, and what-if simulations. "
    "Use tools to answer factually — don't guess figures. "
    "When you return a recommendation, include: why, expected impact, confidence, and which data you used. "
    "Be concise, operational, and specific. If the user asks for an email, draft it using the tool."
)


def _claude_tools_schema() -> list:
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.input_schema,
        }
        for t in TOOLS.values()
    ]


def _claude_call(messages: list, tools: list) -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY missing")
    body = {
        "model": CLAUDE_MODEL,
        "max_tokens": 1500,
        "system": _SYSTEM_PROMPT,
        "tools": tools,
        "messages": messages,
    }
    req = request.Request(
        url=f"{CLAUDE_BASE}/messages",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def dispatch_claude(message: str, history: List[ChatTurn]) -> ChatReply:
    tools_schema = _claude_tools_schema()
    messages: list = []
    for turn in history[-6:]:  # last 6 turns for context
        if turn.role == "user":
            messages.append({"role": "user", "content": turn.content})
        else:
            messages.append({"role": "assistant", "content": turn.content})
    messages.append({"role": "user", "content": message})

    tool_records: List[ToolCallRecord] = []
    final_text = ""

    for _ in range(MAX_CLAUDE_TURNS):
        response = _claude_call(messages, tools_schema)
        stop_reason = response.get("stop_reason")
        content_blocks = response.get("content", [])

        assistant_content_blocks: list = []
        tool_results: list = []

        for block in content_blocks:
            btype = block.get("type")
            if btype == "text":
                final_text += block.get("text", "")
                assistant_content_blocks.append(block)
            elif btype == "tool_use":
                assistant_content_blocks.append(block)
                tool_name = block.get("name", "")
                tool_input = block.get("input", {}) or {}
                tool_id = block.get("id")
                try:
                    record = invoke(tool_name, tool_input)
                    tool_records.append(record)
                    result_text = json.dumps(
                        {
                            "summary": record.output_summary,
                            "data": record.output_preview,
                        },
                        default=str,
                    )
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": result_text,
                    })
                except Exception as e:  # noqa: BLE001
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "is_error": True,
                        "content": str(e),
                    })

        messages.append({"role": "assistant", "content": assistant_content_blocks})
        if tool_results:
            messages.append({"role": "user", "content": tool_results})

        if stop_reason != "tool_use":
            break

    persona = _detect_persona(message)
    return ChatReply(
        reply=final_text.strip() or "(no text response)",
        tool_calls=tool_records,
        persona=persona,
        source="claude",
        generated_at=datetime.now(timezone.utc),
    )


# --- Entry point ------------------------------------------------------------


def dispatch(message: str, history: List[ChatTurn]) -> ChatReply:
    if os.getenv("ANTHROPIC_API_KEY", "").strip():
        try:
            return dispatch_claude(message, history)
        except (error.URLError, TimeoutError, json.JSONDecodeError, KeyError, RuntimeError):
            # Fall through to deterministic on any LLM hiccup
            pass
    return dispatch_deterministic(message)
