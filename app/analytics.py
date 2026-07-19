from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from .schemas import (
    AgentRequest,
    AgentResponse,
    RecommendedAction,
    RiskRecord,
    WatchMetric,
)


SEVERITY_WEIGHT = {"low": 30, "medium": 55, "high": 78, "critical": 92}
CRITICALITY_BONUS = {"low": 0, "medium": 5, "high": 12, "mission-critical": 20}


def _severity_from_score(score: int) -> str:
    if score >= 85:
        return "critical"
    if score >= 70:
        return "high"
    if score >= 45:
        return "medium"
    return "low"


def _rank_actions(risks: List[RiskRecord]) -> List[RecommendedAction]:
    actions: List[RecommendedAction] = []
    for risk in risks[:6]:
        if risk.risk_type == "inventory_gap":
            actions.append(
                RecommendedAction(
                    title=f"Expedite supply plan for {risk.sku}",
                    priority="P1" if risk.score >= 80 else "P2",
                    owner="Procurement",
                    due_in_days=2,
                    rationale="Projected demand exceeds available supply before replenishment arrives.",
                )
            )
        elif risk.risk_type == "supplier_reliability":
            actions.append(
                RecommendedAction(
                    title=f"Run supplier recovery review with {risk.supplier_name}",
                    priority="P1" if risk.score >= 80 else "P2",
                    owner="Supplier Quality",
                    due_in_days=3,
                    rationale="Delivery or quality performance is below the operating threshold for critical projects.",
                )
            )
        elif risk.risk_type == "single_source":
            actions.append(
                RecommendedAction(
                    title=f"Qualify alternate source for {risk.supplier_name}",
                    priority="P1",
                    owner="Strategic Sourcing",
                    due_in_days=10,
                    rationale="A sole-source dependency is carrying too much schedule and commercial risk.",
                )
            )
        elif risk.risk_type == "incident":
            actions.append(
                RecommendedAction(
                    title=f"Escalate incident closure for {risk.title}",
                    priority="P1" if risk.score >= 80 else "P2",
                    owner="Operations",
                    due_in_days=1,
                    rationale="Open incidents are affecting continuity and need named ownership with a closure date.",
                )
            )
        elif risk.risk_type == "po_slip":
            actions.append(
                RecommendedAction(
                    title=f"Create PO recovery plan for {risk.sku}",
                    priority="P2",
                    owner="Expediting",
                    due_in_days=2,
                    rationale="The order is already slipping against the required arrival window.",
                )
            )

    deduped: List[RecommendedAction] = []
    seen: set[Tuple[str, str]] = set()
    for action in actions:
        key = (action.title, action.owner)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(action)
    return deduped[:5]


def analyze_supply_chain(request: AgentRequest, ai_response: str) -> AgentResponse:
    suppliers = {supplier.name: supplier for supplier in request.suppliers}
    demand = {signal.sku: signal for signal in request.demand_signals}
    po_by_sku: Dict[str, List] = defaultdict(list)
    for po in request.purchase_orders:
        po_by_sku[po.sku].append(po)

    risks: List[RiskRecord] = []

    for item in request.inventory:
        signal = demand.get(item.sku)
        open_qty = sum(
            po.quantity
            for po in po_by_sku.get(item.sku, [])
            if po.status != "received"
        )
        days_of_cover = item.on_hand_qty / max(item.daily_demand_qty, 0.1)
        projected_30_day_supply = item.on_hand_qty + open_qty
        forecast_30 = signal.next_30_day_demand_qty if signal else item.daily_demand_qty * 30

        shortage_qty = forecast_30 - projected_30_day_supply
        if shortage_qty > 0:
            score = min(
                100,
                60
                + int(shortage_qty * 0.9)
                + CRITICALITY_BONUS.get(item.criticality, 0)
                + (12 if days_of_cover < item.lead_time_days else 0),
            )
            risks.append(
                RiskRecord(
                    title=f"30-day supply gap on {item.sku}",
                    risk_type="inventory_gap",
                    severity=_severity_from_score(score),
                    score=score,
                    summary=(
                        f"{item.description} is short by about {shortage_qty:.0f} units over the next 30 days. "
                        f"Current cover is {days_of_cover:.0f} days versus a {item.lead_time_days}-day lead time."
                    ),
                    supplier_name=item.supplier_name,
                    sku=item.sku,
                    owner="Planning",
                )
            )

        if item.on_hand_qty <= item.reorder_point_qty or days_of_cover < item.lead_time_days:
            score = min(
                100,
                52
                + int((item.lead_time_days - min(days_of_cover, item.lead_time_days)) * 1.2)
                + CRITICALITY_BONUS.get(item.criticality, 0),
            )
            risks.append(
                RiskRecord(
                    title=f"Low coverage on {item.sku}",
                    risk_type="inventory_gap",
                    severity=_severity_from_score(score),
                    score=score,
                    summary=(
                        f"Inventory has dropped to {item.on_hand_qty:.0f} units with reorder at {item.reorder_point_qty:.0f}. "
                        f"This item protects project continuity and should be actively monitored."
                    ),
                    supplier_name=item.supplier_name,
                    sku=item.sku,
                    owner="Planning",
                )
            )

    for supplier in request.suppliers:
        score = 0
        if supplier.on_time_delivery_pct < 92:
            score += int((92 - supplier.on_time_delivery_pct) * 2.5)
        if supplier.quality_ppm > 1000:
            score += min(25, int((supplier.quality_ppm - 1000) / 80))
        if supplier.approved_alternatives == 0:
            score += 16
        score += len(supplier.risk_flags) * 5
        if supplier.annual_spend_usd > 1000000:
            score += 8
        score = min(100, score + 28)

        if score >= 50:
            risks.append(
                RiskRecord(
                    title=f"Supplier reliability pressure at {supplier.name}",
                    risk_type="supplier_reliability",
                    severity=_severity_from_score(score),
                    score=score,
                    summary=(
                        f"{supplier.name} is running at {supplier.on_time_delivery_pct:.0f}% OTD with "
                        f"{supplier.quality_ppm} PPM quality escapes. Alternatives approved: {supplier.approved_alternatives}."
                    ),
                    supplier_name=supplier.name,
                    owner="Supplier Quality",
                )
            )

        if supplier.approved_alternatives == 0 and supplier.annual_spend_usd >= 500000:
            single_source_score = min(100, 58 + len(supplier.risk_flags) * 6 + int(supplier.annual_spend_usd / 250000))
            risks.append(
                RiskRecord(
                    title=f"Single-source exposure on {supplier.name}",
                    risk_type="single_source",
                    severity=_severity_from_score(single_source_score),
                    score=single_source_score,
                    summary=(
                        f"{supplier.category} depends on a single approved supplier with annual spend near "
                        f"${supplier.annual_spend_usd:,.0f}. Any disruption will hit engineering schedules directly."
                    ),
                    supplier_name=supplier.name,
                    owner="Strategic Sourcing",
                )
            )

    for po in request.purchase_orders:
        supplier = suppliers.get(po.supplier_name)
        if po.status == "delayed" or (po.due_in_days <= 14 and po.status in {"planned", "released"}):
            score = 60
            if po.status == "delayed":
                score += 18
            if not po.expedite_possible:
                score += 10
            if supplier and supplier.on_time_delivery_pct < 92:
                score += 8
            score = min(100, score)
            risks.append(
                RiskRecord(
                    title=f"PO schedule risk on {po.po_number}",
                    risk_type="po_slip",
                    severity=_severity_from_score(score),
                    score=score,
                    summary=(
                        f"{po.po_number} for {po.sku} is due in {po.due_in_days} days and is currently {po.status}. "
                        f"Value at risk is ${po.value_usd:,.0f}."
                    ),
                    supplier_name=po.supplier_name,
                    sku=po.sku,
                    owner="Expediting",
                )
            )

    for incident in request.incidents:
        base = SEVERITY_WEIGHT.get(incident.severity, 50)
        score = min(100, base + min(incident.days_open * 2, 18))
        risks.append(
            RiskRecord(
                title=incident.title,
                risk_type="incident",
                severity=_severity_from_score(score),
                score=score,
                summary=(
                    f"{incident.description} The issue has remained open for {incident.days_open} days "
                    f"and needs visible closure ownership."
                ),
                supplier_name=incident.supplier_name,
                sku=incident.sku,
                owner="Operations",
            )
        )

    # Sort by score, then diversify the top slice by type so the register
    # always surfaces a breadth of signals (inventory, supplier, single-source,
    # PO slip, incident) rather than letting one type dominate.
    ranked_risks = sorted(risks, key=lambda risk: risk.score, reverse=True)
    by_type: dict[str, list] = {}
    for r in ranked_risks:
        by_type.setdefault(r.risk_type, []).append(r)
    top_risks: list = []
    PER_TYPE_FIRST_PASS = 5  # show up to 5 of each type before any seconds
    for t in ["po_slip", "single_source", "supplier_reliability", "incident", "inventory_gap"]:
        top_risks.extend(by_type.get(t, [])[:PER_TYPE_FIRST_PASS])
    # Then top up to 20 with leftovers ordered by score
    used = set(id(r) for r in top_risks)
    for r in ranked_risks:
        if len(top_risks) >= 20:
            break
        if id(r) not in used:
            top_risks.append(r)
    # Re-sort the chosen 20 by score for display order
    top_risks = sorted(top_risks, key=lambda r: r.score, reverse=True)
    overall_risk_score = round(sum(risk.score for risk in top_risks) / max(len(top_risks), 1))

    shortage_value = 0.0
    critical_low_cover = 0
    for item in request.inventory:
        signal = demand.get(item.sku)
        forecast_30 = signal.next_30_day_demand_qty if signal else item.daily_demand_qty * 30
        open_qty = sum(po.quantity for po in po_by_sku.get(item.sku, []) if po.status != "received")
        shortage_qty = max(0.0, forecast_30 - (item.on_hand_qty + open_qty))
        shortage_value += shortage_qty * item.unit_cost_usd
        if item.criticality in {"high", "mission-critical"} and item.on_hand_qty <= item.reorder_point_qty:
            critical_low_cover += 1

    watch_metrics = [
        WatchMetric(
            label="Overall Risk",
            value=f"{overall_risk_score}/100",
            direction="up" if overall_risk_score >= 70 else "steady",
        ),
        WatchMetric(
            label="Critical Items Below Reorder",
            value=str(critical_low_cover),
            direction="up" if critical_low_cover else "steady",
        ),
        WatchMetric(
            label="Shortage Exposure",
            value=f"${shortage_value:,.0f}",
            direction="up" if shortage_value > 0 else "steady",
        ),
        WatchMetric(
            label="Open Incidents",
            value=str(len(request.incidents)),
            direction="up" if request.incidents else "steady",
        ),
    ]

    recommended_actions = _rank_actions(top_risks)
    executive_summary = (
        f"{request.company.company_name} has an elevated supply-chain risk posture at {overall_risk_score}/100. "
        f"The most immediate threats are material availability gaps, supplier performance pressure, and unresolved incidents "
        f"that can disrupt active engineering projects over the next {request.company.planner_horizon_days} days."
    )

    assumptions = [
        "Open purchase orders were treated as available supply unless marked received.",
        "Demand coverage was evaluated primarily over the next 30 days because that is where expediting decisions are most actionable.",
        "The AI assistant response uses a deterministic fallback when no external model credentials are configured.",
    ]

    return AgentResponse(
        generated_at=datetime.now(timezone.utc),
        overall_risk_score=overall_risk_score,
        executive_summary=executive_summary,
        ai_assistant_response=ai_response,
        top_risks=top_risks,
        recommended_actions=recommended_actions,
        watch_metrics=watch_metrics,
        assumptions=assumptions,
    )


# --- LLM-generated mitigations for a single risk -----------------------------


def generate_risk_mitigations(risk: RiskRecord):
    """Return 3 concrete mitigations for the given risk record.

    Tries Grok; falls back to type-keyed templates. Always returns a
    RiskMitigationsReply with `source` indicating which path produced it.
    """

    from datetime import datetime as _dt, timezone as _tz
    from .schemas import RiskMitigationsReply
    from .llm import grok_json, is_enabled

    if is_enabled():
        import json as _json
        context = {
            "title": risk.title,
            "type": risk.risk_type,
            "severity": risk.severity,
            "score": risk.score,
            "summary": risk.summary,
            "supplier": risk.supplier_name,
            "sku": risk.sku,
            "owner": risk.owner,
        }
        system = (
            "You are a supply-chain risk strategist. Given a single risk record, "
            "return THREE concrete, actionable mitigations. Each is one sentence, "
            "specific, names what to do and who would own it. Order: quick-win first, "
            "structural last. Return JSON: {\"mitigations\": [str, str, str]}."
        )
        user = "Risk:\n" + _json.dumps(context, default=str, indent=2)
        parsed = grok_json(system, user, max_tokens=400)
        if parsed:
            mits = parsed.get("mitigations") or []
            if isinstance(mits, list) and mits:
                return RiskMitigationsReply(
                    risk_title=risk.title,
                    mitigations=[str(m) for m in mits][:5],
                    source="grok",
                    generated_at=_dt.now(_tz.utc),
                )

    # Deterministic fallback by risk type
    by_type = {
        "inventory_gap": [
            "Place a top-up PR sized to lead time × forecast within 24h; assign to the category buyer.",
            "Negotiate emergency expediting with the primary supplier and flag this SKU for daily watch.",
            "Add a safety-stock buffer of 1.5× lead-time demand and revisit the reorder point monthly.",
        ],
        "supplier_reliability": [
            "Schedule a supplier review with QA + buyer this week; require a written 30-day recovery plan.",
            "Re-allocate next 30 days of orders to the approved alternate to relieve pressure.",
            "Move this supplier to monthly business reviews until OTD/PPM recovers to target.",
        ],
        "single_source": [
            "Identify and onboard a qualified second source for the category within the quarter.",
            "Build a 60-day strategic buffer of the most critical SKUs from this vendor.",
            "Renegotiate the master agreement to include capacity guarantees and a force-majeure step-down.",
        ],
        "po_slip": [
            "Issue a formal expediting notice today and request a daily status update from the vendor.",
            "Pre-stage logistics (air-freight quote, customs broker) so we can switch mode if the slip widens.",
            "Inform the project planner so downstream milestones can be re-baselined if needed.",
        ],
        "incident": [
            "Assign a single accountable owner and a closure date; daily standup until resolved.",
            "Document containment + corrective + preventive actions in the audit log.",
            "Trigger a watchlist alert if open beyond agreed SLA.",
        ],
    }
    mits = by_type.get(risk.risk_type, [
        "Assign a clear owner and a 5-day plan with milestones.",
        "Quantify the downside and decide whether to mitigate or accept.",
        "Track in the weekly review until closed.",
    ])
    return RiskMitigationsReply(
        risk_title=risk.title,
        mitigations=mits,
        source="deterministic",
        generated_at=_dt.now(_tz.utc),
    )
