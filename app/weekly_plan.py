"""Deterministic weekly plan builder.

Aggregates signals from every module into a prioritized action list with
`why / expected impact / owner / due / confidence / supporting refs` on each
item, matching the recommendation contract in Plan.md §7.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import List, Optional
from urllib.parse import quote

from .commercial import build_commercial_summary
from .expediting import build_expedite_queue
from .planning import build_procurement_plan, list_projects
from .sample_data import build_demo_request
from .schemas import (
    KpiSnapshot,
    WeeklyCategory,
    WeeklyPlan,
    WeeklyPlanItem,
)
from .sourcing import list_rfqs
from .vendor_intel import list_category_concentration, list_vendor_summaries


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _week_of() -> date:
    return date.today()


def _encode_vendor(name: str) -> str:
    return quote(name, safe="")


def _is_entity_ref(ref: str) -> bool:
    return ref.startswith(("vendor:", "project:", "category:", "RFQ-", "PR-", "SPO-", "PO-"))


def _extract_project_id(refs: List[str]) -> Optional[str]:
    for ref in refs:
        if ref.startswith("project:"):
            return ref.split(":", 1)[1]
    return None


def _extract_bom_item_id(refs: List[str]) -> Optional[str]:
    project_id = _extract_project_id(refs)
    if not project_id:
        return None
    for ref in refs:
        if not _is_entity_ref(ref):
            return ref
    return None


def _ref_href(ref: str, project_id: Optional[str] = None) -> Optional[str]:
    if ref.startswith("vendor:"):
        return f"/vendors/{_encode_vendor(ref.split(':', 1)[1])}"
    if ref.startswith("project:"):
        return f"/projects/{ref.split(':', 1)[1]}"
    if ref.startswith("category:"):
        return None
    if ref.startswith("RFQ-"):
        return f"/sourcing/rfqs/{ref}"
    if ref.startswith("PR-"):
        return f"/sourcing/prs/{ref}"
    if ref.startswith(("SPO-", "PO-")):
        return "/pos"
    if project_id and not _is_entity_ref(ref):
        return f"/projects/{project_id}/bom"
    return None


def _resolve_item_href(category: WeeklyCategory, refs: List[str]) -> Optional[str]:
    project_id = _extract_project_id(refs)
    bom_item_id = _extract_bom_item_id(refs)

    if category == "expediting":
        if any(ref.startswith(("SPO-", "PO-")) for ref in refs):
            return "/pos"
        return "/expediting"

    if category == "sourcing":
        for ref in refs:
            if ref.startswith("RFQ-"):
                return f"/sourcing/rfqs/{ref}"
        for ref in refs:
            if ref.startswith("PR-"):
                return f"/sourcing/prs/{ref}"
        if project_id and bom_item_id:
            return f"/projects/{project_id}/bom"
        if project_id:
            return f"/projects/{project_id}"

    if category == "vendor_risk":
        for ref in refs:
            if ref.startswith("vendor:"):
                return f"/vendors/{_encode_vendor(ref.split(':', 1)[1])}"
        return "/vendors"

    if category == "commercial":
        for ref in refs:
            if ref.startswith("PR-"):
                return f"/sourcing/prs/{ref}"
        if project_id:
            return f"/projects/{project_id}"
        return "/commercial"

    if category == "planning":
        if project_id and bom_item_id:
            return f"/projects/{project_id}/bom"
        if project_id:
            return f"/projects/{project_id}"

    if category == "logistics":
        return "/logistics"

    for ref in refs:
        href = _ref_href(ref, project_id)
        if href:
            return href
    return None


def _resolve_primary_action(
    category: WeeklyCategory, refs: List[str], href: Optional[str]
) -> Optional[str]:
    if not href:
        return None

    if category == "expediting":
        return "Open PO" if href == "/pos" else "Open expediting"
    if category == "vendor_risk":
        return "View vendor"
    if category == "logistics":
        return "Open logistics"
    if category == "commercial":
        if any(ref.startswith("PR-") for ref in refs):
            return "Open PR"
        return "Open commercial"
    if category == "planning":
        return "Open BOM" if href.endswith("/bom") else "Open project"
    if category == "sourcing":
        if any(ref.startswith("RFQ-") for ref in refs):
            return "Open RFQ"
        if any(ref.startswith("PR-") for ref in refs):
            return "Open PR"
        if href.endswith("/bom"):
            return "Open BOM"
        return "Open project"
    return "Go"


def _make_item(**kwargs) -> WeeklyPlanItem:
    refs = kwargs["supporting_refs"]
    category = kwargs["category"]
    href = _resolve_item_href(category, refs)
    return WeeklyPlanItem(
        **kwargs,
        href=href,
        primary_action=_resolve_primary_action(category, refs, href),
    )


from ._cache import ttl_cache


# 60s cache matters doubly here: the plan synthesis fans out across every
# module AND (with XAI_API_KEY set) makes an LLM call — multi-second latency
# and real cost on every /weekly-plan load without this.
@ttl_cache(ttl_seconds=60.0)
def build_weekly_plan(tenant_id: Optional[str] = None) -> WeeklyPlan:
    items: List[WeeklyPlanItem] = []
    refs_collected: List[str] = []

    # 1. Expediting — escalate/nudge items
    queue = build_expedite_queue(tenant_id=tenant_id)
    for exp in queue.items:
        if exp.urgency == "escalate":
            items.append(
                _make_item(
                    priority="P1",
                    category="expediting",
                    title=f"Escalate {exp.po_number} with {exp.supplier_name}",
                    why=(
                        f"Slip probability {exp.slip_probability_pct}% with "
                        f"{exp.predicted_slip_days}d expected slip. "
                        f"Reasons: {'; '.join(exp.reasons[:2])}."
                    ),
                    expected_impact=(
                        f"Protects ${exp.value_usd:,.0f} of value and prevents downstream milestone slip."
                    ),
                    owner="Expediting",
                    due_in_days=1,
                    confidence=88,
                    supporting_refs=[exp.po_number, f"vendor:{exp.supplier_name}"],
                )
            )
        elif exp.urgency == "nudge":
            items.append(
                _make_item(
                    priority="P2",
                    category="expediting",
                    title=f"Nudge {exp.supplier_name} on {exp.po_number}",
                    why=(
                        f"Slip probability {exp.slip_probability_pct}%; "
                        f"{'; '.join(exp.reasons[:1])}."
                    ),
                    expected_impact=f"Keeps ${exp.value_usd:,.0f} order on schedule.",
                    owner="Expediting",
                    due_in_days=3,
                    confidence=74,
                    supporting_refs=[exp.po_number],
                )
            )

    # 2. Procurement planning — missing specs and long-lead pressure
    for project in list_projects(tenant_id=tenant_id):
        plan = build_procurement_plan(project.project_id, tenant_id=tenant_id)
        if not plan:
            continue
        # Missing spec — engineering blocker
        for flag in plan.missing_spec_items[:3]:
            items.append(
                _make_item(
                    priority="P1",
                    category="planning",
                    title=f"Release spec for {flag.code} ({project.name})",
                    why=flag.reason,
                    expected_impact=(
                        f"Unblocks requisition for {flag.description}; "
                        f"every day of delay shifts milestone {flag.milestone_code or '—'}."
                    ),
                    owner="Engineering",
                    due_in_days=5,
                    confidence=92,
                    supporting_refs=[flag.bom_item_id, f"project:{project.project_id}"],
                )
            )
        # Long-lead — need to raise PR now
        for flag in plan.long_lead_items[:3]:
            if flag.days_until_need is not None and flag.long_lead_days is not None:
                slack = flag.days_until_need - flag.long_lead_days
                if slack <= 30:
                    items.append(
                        _make_item(
                            priority="P1" if slack <= 0 else "P2",
                            category="sourcing",
                            title=f"Place PR for long-lead {flag.code}",
                            why=flag.reason,
                            expected_impact=(
                                f"Ordering now keeps milestone {flag.milestone_code or '—'} achievable. "
                                f"Delay of 1 week costs ≥ one week of schedule."
                            ),
                            owner="Procurement",
                            due_in_days=7 if slack > 0 else 2,
                            confidence=80,
                            supporting_refs=[flag.bom_item_id, f"project:{project.project_id}"],
                        )
                    )

    # 3. Vendor risk — single-source with flags
    vendor_summaries = list_vendor_summaries(tenant_id=tenant_id)
    concentration = {c.category: c for c in list_category_concentration(tenant_id=tenant_id)}
    for v in vendor_summaries:
        if v.single_source_exposure and v.flags_count > 0:
            items.append(
                _make_item(
                    priority="P2",
                    category="vendor_risk",
                    title=f"Qualify alternate for {v.vendor}",
                    why=(
                        f"Single-source with {v.flags_count} active flag(s) and "
                        f"composite score {v.composite_score}. "
                        f"Category {v.category} is carried by one vendor only."
                    ),
                    expected_impact=(
                        f"Protects ${v.annual_spend_usd:,.0f} annual spend "
                        f"and removes single-point-of-failure on {v.category}."
                    ),
                    owner="Strategic Sourcing",
                    due_in_days=14,
                    confidence=75,
                    supporting_refs=[f"vendor:{v.vendor}", f"category:{v.category}"],
                )
            )

    # 4. Commercial — overruns
    commercial = build_commercial_summary(tenant_id=tenant_id)
    for line in commercial.top_overruns[:2]:
        if line.variance_pct > 5:
            items.append(
                _make_item(
                    priority="P2",
                    category="commercial",
                    title=f"Renegotiate {line.code} ({line.ref_id})",
                    why=(
                        f"Currently {line.variance_pct:.1f}% over budget. "
                        f"Vendor: {line.vendor or 'TBD'}."
                    ),
                    expected_impact=(
                        f"Recovers up to ${max(0, -line.savings_usd):,.0f} on this line."
                    ),
                    owner="Procurement",
                    due_in_days=7,
                    confidence=65,
                    supporting_refs=[line.ref_id, f"project:{line.project_id}"],
                )
            )

    # 5. Sourcing — RFQs awaiting quotes or award
    for rfq in list_rfqs():
        if rfq.status in {"open", "quotes_received"}:
            items.append(
                _make_item(
                    priority="P3",
                    category="sourcing",
                    title=f"Progress {rfq.rfq_no} ({rfq.code})",
                    why=(
                        f"RFQ status {rfq.status.replace('_', ' ')}; "
                        f"{len(rfq.vendors)} vendors invited."
                    ),
                    expected_impact="Moves the PR toward award and PO draft.",
                    owner="Procurement",
                    due_in_days=5,
                    confidence=70,
                    supporting_refs=[rfq.rfq_no, rfq.pr_no],
                )
            )

    # 6. Logistics — shipments at customs / port
    for s in queue.items:
        if s.source == "scenario":
            continue
    # Use scenario POs separately for port/customs is already captured in expediting
    # Skip a dedicated logistics loop to avoid duplication.

    # Stable sort: P1 > P2 > P3, then confidence desc
    priority_key = {"P1": 0, "P2": 1, "P3": 2}
    items.sort(key=lambda i: (priority_key[i.priority], -i.confidence))

    # Cap to 10 items
    items = items[:10]

    # Headline
    p1_count = sum(1 for i in items if i.priority == "P1")
    if p1_count > 0:
        headline = (
            f"{p1_count} P1 action(s) demand attention this week. "
            "Focus on escalations and missing specs before they shift milestones."
        )
    elif items:
        headline = "No P1 fires. Keep pushing sourcing and vendor diversification forward."
    else:
        headline = "Quiet week on the control tower."

    # KPI snapshot
    scenario = build_demo_request(tenant_id or "arcforge")
    kpi_snapshot: List[KpiSnapshot] = [
        KpiSnapshot(
            label="Overall Risk",
            value=f"{queue.summary.escalate + queue.summary.nudge} orders at risk",
            tone="bad" if queue.summary.escalate else ("warn" if queue.summary.nudge else "good"),
        ),
        KpiSnapshot(
            label="Value at Risk",
            value=f"${queue.summary.value_at_risk_usd:,.0f}",
            tone="bad" if queue.summary.value_at_risk_usd > 50_000 else "neutral",
        ),
        KpiSnapshot(
            label="Commercial Savings",
            value=f"${commercial.total_savings_usd:,.0f}",
            tone="good" if commercial.total_savings_usd > 0 else "neutral",
        ),
        KpiSnapshot(
            label="Vendor Flags",
            value=str(sum(v.flags_count for v in vendor_summaries)),
            tone="warn" if any(v.single_source_exposure for v in vendor_summaries) else "neutral",
        ),
        KpiSnapshot(
            label="Single-Source Categories",
            value=str(sum(1 for c in concentration.values() if c.single_source)),
            tone="bad" if any(c.single_source for c in concentration.values()) else "good",
        ),
        KpiSnapshot(
            label="Open Incidents",
            value=str(len(scenario.incidents)),
            tone="warn" if scenario.incidents else "good",
        ),
    ]

    plan = WeeklyPlan(
        generated_at=_now(),
        week_of=_week_of(),
        headline=headline,
        kpi_snapshot=kpi_snapshot,
        items=items,
        assumptions=[
            "Plan is rebuilt on every fetch from current scenario + sourcing + logistics state.",
            "Priorities use deterministic rules; synthesized_narrative comes from Grok when XAI_API_KEY is set.",
            "Confidence is a heuristic from signal strength, not a statistical estimate.",
        ],
    )
    # Add LLM synthesis on top of the rule-based plan (None if Grok unavailable).
    plan.synthesized_narrative = _llm_weekly_narrative(plan)
    return plan


def _llm_weekly_narrative(plan: WeeklyPlan) -> Optional[str]:
    """Compose a 2-paragraph executive narrative over the deterministic plan."""

    from .llm import grok_chat, is_enabled

    if not is_enabled():
        return None

    import json as _json
    summary = {
        "headline": plan.headline,
        "kpis": [{"label": k.label, "value": k.value, "tone": k.tone} for k in plan.kpi_snapshot],
        "items": [
            {
                "priority": i.priority,
                "category": i.category,
                "title": i.title,
                "why": i.why,
                "owner": i.owner,
                "due_in_days": i.due_in_days,
                "confidence": i.confidence,
            }
            for i in plan.items
        ],
    }
    system = (
        "You are a chief procurement officer writing a 2-paragraph briefing on "
        "this week's priorities for the project sponsor. Paragraph 1: where the "
        "biggest pressure is and why. Paragraph 2: what you're doing about it "
        "and which decisions need cover-air. Plain prose, no markdown, "
        "no headings, no lists. ≤180 words."
    )
    user = "This week's plan:\n" + _json.dumps(summary, default=str, indent=2)
    return grok_chat(system, user, max_tokens=500, temperature=0.4, timeout=25)
