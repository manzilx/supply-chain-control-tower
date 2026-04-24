"""Deterministic weekly plan builder.

Aggregates signals from every module into a prioritized action list with
`why / expected impact / owner / due / confidence / supporting refs` on each
item, matching the recommendation contract in Plan.md §7.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import List

from .commercial import build_commercial_summary
from .expediting import build_expedite_queue
from .planning import build_procurement_plan, list_projects
from .sample_data import build_demo_request
from .schemas import (
    KpiSnapshot,
    WeeklyPlan,
    WeeklyPlanItem,
)
from .sourcing import list_rfqs
from .vendor_intel import list_category_concentration, list_vendor_summaries


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _week_of() -> date:
    return date.today()


def build_weekly_plan() -> WeeklyPlan:
    items: List[WeeklyPlanItem] = []
    refs_collected: List[str] = []

    # 1. Expediting — escalate/nudge items
    queue = build_expedite_queue()
    for exp in queue.items:
        if exp.urgency == "escalate":
            items.append(
                WeeklyPlanItem(
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
                WeeklyPlanItem(
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
    for project in list_projects():
        plan = build_procurement_plan(project.project_id)
        if not plan:
            continue
        # Missing spec — engineering blocker
        for flag in plan.missing_spec_items[:3]:
            items.append(
                WeeklyPlanItem(
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
                        WeeklyPlanItem(
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
    vendor_summaries = list_vendor_summaries()
    concentration = {c.category: c for c in list_category_concentration()}
    for v in vendor_summaries:
        if v.single_source_exposure and v.flags_count > 0:
            items.append(
                WeeklyPlanItem(
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
    commercial = build_commercial_summary()
    for line in commercial.top_overruns[:2]:
        if line.variance_pct > 5:
            items.append(
                WeeklyPlanItem(
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
                WeeklyPlanItem(
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
    scenario = build_demo_request()
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

    return WeeklyPlan(
        generated_at=_now(),
        week_of=_week_of(),
        headline=headline,
        kpi_snapshot=kpi_snapshot,
        items=items,
        assumptions=[
            "Plan is rebuilt on every fetch from current scenario + sourcing + logistics state.",
            "Priorities use deterministic rules; swap in an LLM ranker by setting ANTHROPIC_API_KEY or OPENAI_API_KEY.",
            "Confidence is a heuristic from signal strength, not a statistical estimate.",
        ],
    )
