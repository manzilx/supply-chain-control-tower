"""Agent engine.

Two modes:
1. Deterministic router (default, always works, no API key) — keyword match
   the user message to tools, run them, format a response.
2. LLM tool-calling (opt-in via DEEPSEEK_API_KEY) — DeepSeek plans tool
   calls via the OpenAI-compatible chat-completions API, we execute, loop
   until it returns a final message.

The API shape mirrors OpenAI's tool-calling, NOT Anthropic Messages — tools
are wrapped in {"type": "function", "function": {...}}, tool calls return
under message.tool_calls, and tool results go back as {"role": "tool", ...}.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from urllib import error, request

from .agent_tools import get_tool_user, invoke, tools_for
from .sample_data import build_demo_request
from .schemas import (
    AgentPersona,
    ChatReply,
    ChatTurn,
    ToolCallRecord,
)


MAX_TURNS = 6  # tool-use loops before we force a final reply



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


def _proposed_vendor_from_message(message: str) -> dict:
    """Best-effort args for propose_vendor_onboarding in deterministic mode."""
    msg = message.lower()
    category = "Forged valves" if "valve" in msg else "General supplies"
    if "plc" in msg or "control panel" in msg:
        category = "PLC and control panels"
    elif "copper" in msg or "busbar" in msg:
        category = "Copper busbars"
    name_match = re.search(
        r"(?:called|named)\s+([A-Z][\w\s&.-]{2,40})",
        message,
        re.IGNORECASE,
    )
    if name_match:
        name = name_match.group(1).strip()
    elif "backup" in msg:
        name = f"Backup {category} Supplier"
    else:
        name = f"Proposed {category} Vendor"
    return {"name": name, "category": category, "country": "Norway"}


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

    # AI propose → approval gate for new vendors
    if ("propose" in msg or "onboard" in msg) and ("vendor" in msg or "supplier" in msg):
        plan.append(("propose_vendor_onboarding", _proposed_vendor_from_message(message)))
        return plan

    # Site store — keyword-first so "GRN triage" is not swallowed by logistics/general.
    if any(k in msg for k in ["grn", "challan", "goods receipt", "site store", "unmatched receipt"]):
        plan.append(("get_grn_queue", {}))
        return plan

    # Governance queue — copilot already asks "What's awaiting approval?"
    if any(k in msg for k in ["approval", "awaiting approve", "to approve", "pending approve"]):
        plan.append(("get_pending_approvals", {}))
        return plan

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
    tool_names = {c.tool for c in calls}
    if "get_grn_queue" in tool_names:
        hints.append("Open `/store/grn-triage` to match receipts to POs. AI never auto-posts stock.")
    if "get_pending_approvals" in tool_names:
        hints.append("Open `/approvals` to decide. The agent cannot approve or reject.")
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

    # Structured tool outputs (weekly plan, expediting queue, vendors, etc.)
    # are rendered as rich React tables by the frontend (see StructuredOutputs
    # in app/agent/page.tsx). Don't duplicate them in the prose reply — keep
    # this text short.

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


# --- DeepSeek tool-calling path (OpenAI-compatible chat-completions) --------


_SYSTEM_PROMPT = (
    "You are the AI Command Center for an engineering / EPC supply chain control tower. "
    "You have tool access to procurement, vendor intelligence, expediting, logistics, "
    "commercial rollups, procurement plans, what-if simulations, pending approvals, "
    "and the site-store GRN queue. "
    "Use tools to answer factually — don't guess figures. "
    "When you return a recommendation, include: why, expected impact, confidence, and which data you used. "
    "Be concise, operational, and specific. If the user asks for an email, draft it using the tool.\n\n"
    "HARD RULES:\n"
    "- Approvals: use get_pending_approvals. Never claim you approved or rejected anything.\n"
    "- GRNs: use get_grn_queue. Never claim a receipt posted stock unless the tool shows "
    "status=confirmed. The PO matcher is deterministic; you must not invent a PO match. "
    "Photo extraction is off on the default text-only model, so unmatched/skipped extraction is expected.\n\n"
    "FORMATTING RULES (the UI renders GitHub-flavoured markdown):\n"
    "- Whenever you list more than 2 items with multiple fields (actions, POs, vendors, risks, "
    "  shipments, quotes, etc.), render them as a GFM markdown table — NOT a numbered list with "
    "  pipe-separated fields.\n"
    "- Keep prose above and below the table short. The table is the answer.\n"
    "- Pick 4-7 of the most useful columns; don't dump every field.\n"
    "- Use `**bold**` for headers/labels and `\\`monospace\\`` for IDs (PO-12345, RFQ-001, project codes).\n"
    "- Currency: `$1.2M`, `$45K`. Dates: `May 12`. Durations: `5d`.\n"
    "- Tables look like:\n"
    "    | Priority | Action | Owner | Due | Confidence |\n"
    "    |---|---|---|---|---|\n"
    "    | P1 | Release spec for PLC-S7-IO48 | Engineering | 5d | 92% |"
)


def _llm_tools_schema() -> list:
    """OpenAI-style function tool schema (DeepSeek follows the same shape)."""

    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.input_schema,
            },
        }
        # Only offer the model tools this user's role may run.
        for t in tools_for(get_tool_user())
    ]


def _llm_call(messages: list, tools: list) -> dict:
    from .llm import chat_completions, is_enabled

    if not is_enabled():
        raise RuntimeError("LLM API key missing")
    body: dict = {
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "temperature": 0.2,
    }
    parsed = chat_completions(body, timeout=60)
    if not parsed:
        raise RuntimeError("LLM chat completion failed")
    return parsed


def dispatch_llm(
    message: str,
    history: List[ChatTurn],
    page: str | None = None,
    on_event=None,
) -> ChatReply:
    tools_schema = _llm_tools_schema()

    system = _SYSTEM_PROMPT
    if page:
        system += f"\n\nThe user is currently viewing the '{page}' page of the app — bias your answer toward that context."

    messages: list = [{"role": "system", "content": system}]
    for turn in history[-6:]:  # last 6 turns of conversational context
        messages.append({"role": turn.role, "content": turn.content})
    messages.append({"role": "user", "content": message})

    tool_records: List[ToolCallRecord] = []
    final_text = ""

    def _emit(kind: str, detail: str) -> None:
        if on_event is not None:
            try:
                on_event(kind, detail)
            except Exception:  # noqa: BLE001 — UI events must never break the loop
                pass

    for _ in range(MAX_TURNS):
        _emit("status", "thinking")
        response = _llm_call(messages, tools_schema)
        choice = (response.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        finish_reason = choice.get("finish_reason")

        # Append the assistant turn to history (with any tool_calls intact).
        assistant_msg: dict = {"role": "assistant", "content": msg.get("content")}
        if msg.get("tool_calls"):
            assistant_msg["tool_calls"] = msg["tool_calls"]
        messages.append(assistant_msg)

        text = msg.get("content")
        if text:
            final_text += text

        tool_calls_raw = msg.get("tool_calls") or []
        if not tool_calls_raw:
            break

        for tc in tool_calls_raw:
            fn = tc.get("function") or {}
            tool_name = fn.get("name", "")
            _emit("tool", tool_name)
            try:
                tool_input = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                tool_input = {}
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
            except Exception as e:  # noqa: BLE001
                result_text = json.dumps({"error": str(e)})
            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id"),
                "content": result_text,
            })

        if finish_reason != "tool_calls":
            break

    from .llm import llm_source

    persona = _detect_persona(message)
    src = llm_source()
    return ChatReply(
        reply=final_text.strip() or "(no text response)",
        tool_calls=tool_records,
        persona=persona,
        source="deepseek" if src == "deepseek" else "deterministic",
        generated_at=datetime.now(timezone.utc),
    )


# --- Entry point ------------------------------------------------------------


def dispatch(
    message: str,
    history: List[ChatTurn],
    page: str | None = None,
    on_event=None,
) -> ChatReply:
    from .llm import is_enabled

    if is_enabled():
        try:
            return dispatch_llm(message, history, page=page, on_event=on_event)
        except (error.URLError, error.HTTPError, TimeoutError, json.JSONDecodeError, KeyError, RuntimeError):
            # Fall through to deterministic on any LLM hiccup.
            pass
    return dispatch_deterministic(message)
