"""Agent tool registry.

Every tool is a thin wrapper around an existing module. The agent layer (both
deterministic and LLM-driven) calls these and records a `ToolCallRecord` per
invocation so the UI can show transparency into what was done.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from .analytics import analyze_supply_chain
from .commercial import build_commercial_summary
from .expediting import build_expedite_queue, draft_followup_email, get_expedite_item
from .logistics import list_shipments, recommend_mode
from .planning import build_procurement_plan, get_project, list_projects
from .sample_data import build_demo_request
from .schemas import (
    DraftFollowupRequest,
    EmailTone,
    SimulationRequest,
    SimulationScenario,
    ToolCallRecord,
)
from .simulations import run_simulation
from .sourcing import list_prs, list_rfqs, list_pos as list_sourcing_pos
from .vendor_intel import (
    get_vendor_scorecard,
    list_category_concentration,
    list_vendor_summaries,
)
from .weekly_plan import build_weekly_plan


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    persona: str
    run: Callable[[dict], Any]
    summarize: Callable[[Any], str]


def _to_dict(obj: Any) -> Any:
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, list):
        return [_to_dict(x) for x in obj]
    return obj


def _record(tool: Tool, args: dict, result: Any) -> ToolCallRecord:
    return ToolCallRecord(
        tool=tool.name,
        input=args,
        output_summary=tool.summarize(result),
        output_preview=_to_dict(result) if not isinstance(result, (int, float, str, bool)) else {"value": result},
    )


# --- Tool implementations ---------------------------------------------------


def _tool_weekly_plan(_: dict) -> Any:
    return build_weekly_plan()


def _summarize_weekly_plan(plan: Any) -> str:
    p1 = sum(1 for i in plan.items if i.priority == "P1")
    return f"Weekly plan: {len(plan.items)} items ({p1} P1). {plan.headline}"


def _tool_top_risks(_: dict) -> Any:
    scenario = build_demo_request()
    return analyze_supply_chain(scenario, ai_response="").top_risks


def _summarize_risks(risks: List[Any]) -> str:
    if not risks:
        return "No risks found."
    top = risks[0]
    return f"{len(risks)} risks, top is '{top.title}' (score {top.score})."


def _tool_expedite_queue(_: dict) -> Any:
    return build_expedite_queue()


def _summarize_expedite(q: Any) -> str:
    return (
        f"{q.summary.total} open orders, {q.summary.escalate} escalate, "
        f"{q.summary.nudge} nudge. ${q.summary.value_at_risk_usd:,.0f} at risk."
    )


def _tool_predict_slip(args: dict) -> Any:
    return get_expedite_item(args.get("po_number", ""))


def _summarize_slip(item: Any) -> str:
    if not item:
        return "PO not found in queue."
    return (
        f"{item.po_number} ({item.supplier_name}): "
        f"{item.slip_probability_pct}% slip probability, "
        f"{item.predicted_slip_days}d expected slip, urgency {item.urgency}."
    )


def _tool_draft_followup(args: dict) -> Any:
    tone = args.get("tone", "standard")
    if tone not in {"standard", "firm", "urgent"}:
        tone = "standard"
    req = DraftFollowupRequest(tone=tone, request_documents=True)  # type: ignore[arg-type]
    return draft_followup_email(args.get("po_number", ""), req)


def _summarize_email(email: Any) -> str:
    if not email:
        return "PO not found."
    return f"Drafted {email.tone} email to {email.vendor} ({email.to_placeholder}); subject: {email.subject}"


def _tool_vendor_scorecard(args: dict) -> Any:
    return get_vendor_scorecard(args.get("name", ""))


def _summarize_vendor(sc: Any) -> str:
    if not sc:
        return "Vendor not found."
    return (
        f"{sc.vendor}: composite {sc.composite_score} ({sc.composite_grade}), "
        f"{len(sc.alternates)} alternates"
        f"{', single-source' if sc.single_source_exposure else ''}."
    )


def _tool_all_vendors(_: dict) -> Any:
    return list_vendor_summaries()


def _summarize_vendors(vs: List[Any]) -> str:
    return f"{len(vs)} vendors; top-ranked: {vs[0].vendor} ({vs[0].composite_score})." if vs else "No vendors."


def _tool_concentration(_: dict) -> Any:
    return list_category_concentration()


def _summarize_concentration(cats: List[Any]) -> str:
    single = [c.category for c in cats if c.single_source]
    if single:
        return f"{len(cats)} categories; {len(single)} are single-source: {', '.join(single)}."
    return f"{len(cats)} categories; all diversified."


def _tool_commercial(_: dict) -> Any:
    return build_commercial_summary()


def _summarize_commercial(c: Any) -> str:
    return (
        f"Budget ${c.total_budget_usd:,.0f}, awarded ${c.total_awarded_usd:,.0f}, "
        f"savings ${c.total_savings_usd:,.0f} ({c.savings_pct}%)."
    )


def _tool_logistics(_: dict) -> Any:
    return list_shipments()


def _summarize_logistics(q: Any) -> str:
    return (
        f"{q.summary.total} shipments; {q.summary.at_bottleneck} at bottleneck, "
        f"{q.summary.in_motion} in motion. ${q.summary.value_in_motion_usd:,.0f} in motion."
    )


def _tool_procurement_plan(args: dict) -> Any:
    pid = args.get("project_id", "")
    if not pid:
        projects = list_projects()
        if projects:
            pid = projects[0].project_id
    return build_procurement_plan(pid)


def _summarize_plan(plan: Any) -> str:
    if not plan:
        return "Project not found."
    return (
        f"{plan.project_name}: {plan.summary.bom_item_count} BOM items across "
        f"{plan.summary.packages_count} packages; "
        f"{plan.summary.long_lead_count} long-lead, "
        f"{plan.summary.missing_spec_count} missing-spec flags."
    )


def _tool_projects(_: dict) -> Any:
    return list_projects()


def _summarize_projects(ps: List[Any]) -> str:
    return ", ".join(f"{p.project_id} ({p.name})" for p in ps) if ps else "No projects."


def _tool_open_rfqs(_: dict) -> Any:
    return [r for r in list_rfqs() if r.status in {"open", "quotes_received"}]


def _summarize_rfqs(rs: List[Any]) -> str:
    if not rs:
        return "No open RFQs."
    return f"{len(rs)} open RFQ(s): {', '.join(r.rfq_no for r in rs)}."


def _tool_open_prs(_: dict) -> Any:
    return [p for p in list_prs() if p.status in {"draft", "rfq_issued", "quoted"}]


def _summarize_prs(ps: List[Any]) -> str:
    if not ps:
        return "No open PRs."
    return f"{len(ps)} PR(s) in flight."


def _tool_simulate(args: dict) -> Any:
    scenario_value = args.get("scenario")
    if scenario_value not in {"vendor_slip_2w", "customs_hold", "alt_vendor"}:
        return None
    req = SimulationRequest(
        scenario=scenario_value,  # type: ignore[arg-type]
        target=args.get("target", ""),
        alternate_vendor=args.get("alternate_vendor"),
        custom_slip_days=args.get("custom_slip_days"),
    )
    return run_simulation(req)


def _summarize_simulation(r: Any) -> str:
    if not r:
        return "Simulation inputs invalid."
    return (
        f"{r.scenario} on {r.target}: {r.severity}, "
        f"cost ${r.cost_delta_usd:,.0f}, schedule {r.schedule_delta_days}d."
    )


def _tool_recommend_mode(args: dict) -> Any:
    return recommend_mode(args.get("po_ref", ""))


def _summarize_mode(rec: Any) -> str:
    if not rec:
        return "Shipment not found."
    return f"{rec.current_mode} → {rec.recommended_mode} (×{rec.cost_multiplier:.1f}, ~{rec.transit_days_estimate}d)."


# --- Registry ---------------------------------------------------------------


TOOLS: Dict[str, Tool] = {
    "build_weekly_plan": Tool(
        name="build_weekly_plan",
        description="Build the consolidated this-week action plan across every module.",
        input_schema={"type": "object", "properties": {}, "required": []},
        persona="reporting",
        run=_tool_weekly_plan,
        summarize=_summarize_weekly_plan,
    ),
    "get_top_risks": Tool(
        name="get_top_risks",
        description="Return the most severe risks from the current scenario.",
        input_schema={"type": "object", "properties": {}, "required": []},
        persona="general",
        run=_tool_top_risks,
        summarize=_summarize_risks,
    ),
    "get_expedite_queue": Tool(
        name="get_expedite_queue",
        description="List every open order with slip probability and urgency bucket.",
        input_schema={"type": "object", "properties": {}, "required": []},
        persona="expediting",
        run=_tool_expedite_queue,
        summarize=_summarize_expedite,
    ),
    "predict_slip": Tool(
        name="predict_slip",
        description="Return slip prediction for a specific PO number.",
        input_schema={
            "type": "object",
            "properties": {"po_number": {"type": "string"}},
            "required": ["po_number"],
        },
        persona="expediting",
        run=_tool_predict_slip,
        summarize=_summarize_slip,
    ),
    "draft_followup_email": Tool(
        name="draft_followup_email",
        description="Draft a follow-up email for a PO. Tone: standard | firm | urgent.",
        input_schema={
            "type": "object",
            "properties": {
                "po_number": {"type": "string"},
                "tone": {"type": "string", "enum": ["standard", "firm", "urgent"]},
            },
            "required": ["po_number"],
        },
        persona="expediting",
        run=_tool_draft_followup,
        summarize=_summarize_email,
    ),
    "get_vendor_scorecard": Tool(
        name="get_vendor_scorecard",
        description="Full scorecard for a vendor: components, flags, alternates, concentration.",
        input_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        persona="vendor_risk",
        run=_tool_vendor_scorecard,
        summarize=_summarize_vendor,
    ),
    "list_vendors": Tool(
        name="list_vendors",
        description="List all approved vendors with composite score and grade.",
        input_schema={"type": "object", "properties": {}, "required": []},
        persona="vendor_risk",
        run=_tool_all_vendors,
        summarize=_summarize_vendors,
    ),
    "get_category_concentration": Tool(
        name="get_category_concentration",
        description="Category-level vendor concentration with single-source flags.",
        input_schema={"type": "object", "properties": {}, "required": []},
        persona="vendor_risk",
        run=_tool_concentration,
        summarize=_summarize_concentration,
    ),
    "get_commercial_summary": Tool(
        name="get_commercial_summary",
        description="Budget vs awarded vs savings rollup across all projects.",
        input_schema={"type": "object", "properties": {}, "required": []},
        persona="commercial",
        run=_tool_commercial,
        summarize=_summarize_commercial,
    ),
    "get_logistics_queue": Tool(
        name="get_logistics_queue",
        description="Current shipments with stage, mode, and bottleneck flags.",
        input_schema={"type": "object", "properties": {}, "required": []},
        persona="logistics",
        run=_tool_logistics,
        summarize=_summarize_logistics,
    ),
    "recommend_mode": Tool(
        name="recommend_mode",
        description="Recommend a freight mode for a shipment given urgency and value.",
        input_schema={
            "type": "object",
            "properties": {"po_ref": {"type": "string"}},
            "required": ["po_ref"],
        },
        persona="logistics",
        run=_tool_recommend_mode,
        summarize=_summarize_mode,
    ),
    "get_procurement_plan": Tool(
        name="get_procurement_plan",
        description="Procurement plan for a project (long-lead + missing-spec flags).",
        input_schema={
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": [],
        },
        persona="planning",
        run=_tool_procurement_plan,
        summarize=_summarize_plan,
    ),
    "list_projects": Tool(
        name="list_projects",
        description="List all engineering projects with milestones.",
        input_schema={"type": "object", "properties": {}, "required": []},
        persona="planning",
        run=_tool_projects,
        summarize=_summarize_projects,
    ),
    "get_open_rfqs": Tool(
        name="get_open_rfqs",
        description="List RFQs awaiting quotes or award.",
        input_schema={"type": "object", "properties": {}, "required": []},
        persona="sourcing",
        run=_tool_open_rfqs,
        summarize=_summarize_rfqs,
    ),
    "get_open_prs": Tool(
        name="get_open_prs",
        description="List purchase requisitions still in flight.",
        input_schema={"type": "object", "properties": {}, "required": []},
        persona="sourcing",
        run=_tool_open_prs,
        summarize=_summarize_prs,
    ),
    "run_simulation": Tool(
        name="run_simulation",
        description="Run a what-if simulation: vendor_slip_2w | customs_hold | alt_vendor.",
        input_schema={
            "type": "object",
            "properties": {
                "scenario": {"type": "string", "enum": ["vendor_slip_2w", "customs_hold", "alt_vendor"]},
                "target": {"type": "string"},
                "alternate_vendor": {"type": "string"},
                "custom_slip_days": {"type": "integer"},
            },
            "required": ["scenario", "target"],
        },
        persona="general",
        run=_tool_simulate,
        summarize=_summarize_simulation,
    ),
}


def invoke(name: str, args: Optional[dict] = None) -> ToolCallRecord:
    """Run a tool and return a transparent call record. Unknown tools raise."""
    args = args or {}
    if name not in TOOLS:
        raise ValueError(f"Unknown tool: {name}")
    tool = TOOLS[name]
    result = tool.run(args)
    return _record(tool, args, result)
