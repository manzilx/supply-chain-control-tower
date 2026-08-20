"""Risk simulations.

What-if simulators that reuse scorecards, BOMs, and sourcing state:

- vendor_slip_2w  : what if `<vendor>` slips every open order by ~14 days?
- customs_hold    : what if `<po_no>` gets held in customs for ~21 days?
- alt_vendor      : what if we replaced `<vendor>` with `<alternate_vendor>`?
- need_by_move    : what if a milestone / PR / BOM need-by moves ±N days?

Returns a uniform SimulationResult so the UI can render any scenario with the
same component.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Set, Tuple

from .planning import get_bom, list_projects
from .sample_data import build_demo_request
from .schemas import (
    AffectedItem,
    MilestoneImpact,
    ParseSimulationReply,
    SimulationBrief,
    SimulationPrimaryAction,
    SimulationRequest,
    SimulationResult,
    SourcingPO,
    SupplierRecord,
)
from .sourcing import list_pos as _list_sourcing_pos
from .vendor_intel import get_vendor_scorecard


DEFAULT_SLIP_DAYS = 14
CUSTOMS_HOLD_DAYS = 21
LD_RATE = 0.02
EXPEDITE_RATE = 0.03
HOLDING_COST_RATE = 0.015
SWITCHING_COST_USD = 12_000.0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _demo(tenant_id: Optional[str] = None):
    return build_demo_request(tenant_id or "arcforge")


def _suppliers(tenant_id: Optional[str] = None) -> Dict[str, SupplierRecord]:
    return {s.name: s for s in _demo(tenant_id).suppliers}


def _project_name(pid: str, tenant_id: Optional[str] = None) -> str:
    for p in list_projects(tenant_id=tenant_id):
        if p.project_id == pid:
            return p.name
    return pid


def _severity_from_cost_and_days(cost: float, days: int) -> str:
    score = cost / 5000 + days * 4
    if score >= 40:
        return "critical"
    if score >= 22:
        return "high"
    if score >= 10:
        return "medium"
    return "low"


def _milestone_slip_for_bom(
    bom_item_id: str,
    project_id: str,
    slip_days: int,
    tenant_id: Optional[str] = None,
) -> Optional[MilestoneImpact]:
    items = get_bom(project_id, tenant_id=tenant_id)
    item = next((i for i in items if i.bom_item_id == bom_item_id), None)
    if not item or not item.milestone_code:
        return None
    for p in list_projects(tenant_id=tenant_id):
        if p.project_id == project_id:
            for m in p.milestones:
                if m.code == item.milestone_code:
                    return MilestoneImpact(
                        project_id=project_id,
                        project_name=p.name,
                        milestone_code=m.code,
                        milestone_name=m.name,
                        original_date=m.required_on_site_date,
                        new_date=m.required_on_site_date + timedelta(days=slip_days),
                        slip_days=slip_days,
                    )
    return None


# --- Vendor slip simulation --------------------------------------------------


def _simulate_vendor_slip(
    vendor: str, slip_days: int, tenant_id: Optional[str] = None
) -> SimulationResult:
    scenario = _demo(tenant_id)
    sourcing_pos = _list_sourcing_pos(tenant_id)
    affected: List[AffectedItem] = []
    milestone_impacts: List[MilestoneImpact] = []
    total_value = 0.0

    # Scenario POs by this vendor
    for po in scenario.purchase_orders:
        if po.supplier_name != vendor or po.status == "received":
            continue
        inv = next((i for i in scenario.inventory if i.sku == po.sku), None)
        description = inv.description if inv else po.sku
        today = date.today()
        original_need = today + timedelta(days=po.due_in_days)
        new_expected = original_need + timedelta(days=slip_days)
        affected.append(
            AffectedItem(
                ref_id=po.po_number,
                code=po.sku,
                description=description,
                impact=f"Delivery pushes from {original_need} to {new_expected}.",
                original_need_date=original_need,
                new_expected_date=new_expected,
            )
        )
        total_value += po.value_usd

    # Sourcing POs by this vendor
    for spo in sourcing_pos:
        if spo.vendor != vendor or spo.status == "delivered":
            continue
        original = spo.need_by
        new_expected = original + timedelta(days=slip_days) if original else None
        affected.append(
            AffectedItem(
                ref_id=spo.po_no,
                code=spo.code,
                description=spo.description,
                impact=(
                    f"Sourcing order slides from {original} to {new_expected}."
                    if original
                    else "Sourcing order slides by the slip window."
                ),
                original_need_date=original,
                new_expected_date=new_expected,
            )
        )
        total_value += spo.value_usd
        # milestone lookup via PR→BOM link
        from .sourcing import get_pr  # local import to avoid cycle
        pr = get_pr(spo.pr_no, tenant_id=tenant_id)
        if pr and pr.bom_item_id:
            impact = _milestone_slip_for_bom(
                pr.bom_item_id, spo.project_id, slip_days, tenant_id
            )
            if impact:
                milestone_impacts.append(impact)

    cost_delta = round(total_value * (LD_RATE + EXPEDITE_RATE), 2)

    if not affected:
        headline = f"No open orders for {vendor} — simulation has no impact."
        severity = "low"
    else:
        headline = (
            f"{len(affected)} order(s) from {vendor} slide by {slip_days} days; "
            f"value at risk ${total_value:,.0f}."
        )
        severity = _severity_from_cost_and_days(cost_delta, slip_days)

    mitigations = [
        f"Issue expedite request with {vendor} and confirm a recovery plan within 48h.",
        "Shift freight mode to air for critical long-lead orders on this vendor.",
        "Activate approved alternates from scorecard for next award cycles.",
    ]
    assumptions = [
        f"Assumed slip of {slip_days} days applied uniformly across {vendor}'s open orders.",
        f"Cost delta modelled as LD ({LD_RATE * 100:.1f}%) plus expediting ({EXPEDITE_RATE * 100:.1f}%).",
    ]

    return SimulationResult(
        scenario="vendor_slip_2w",
        target=vendor,
        generated_at=_now(),
        headline=headline,
        severity=severity,  # type: ignore[arg-type]
        cost_delta_usd=cost_delta,
        schedule_delta_days=slip_days,
        affected_items=affected,
        milestone_impacts=milestone_impacts,
        mitigations=mitigations,
        assumptions=assumptions,
    )


# --- Customs hold simulation -------------------------------------------------


def _simulate_customs_hold(
    po_ref: str, tenant_id: Optional[str] = None
) -> SimulationResult:
    scenario = _demo(tenant_id)
    affected: List[AffectedItem] = []
    milestone_impacts: List[MilestoneImpact] = []
    value = 0.0
    vendor_or_ref = po_ref
    today = date.today()

    scenario_po = next((p for p in scenario.purchase_orders if p.po_number == po_ref), None)
    sourcing_po: Optional[SourcingPO] = next(
        (p for p in _list_sourcing_pos(tenant_id) if p.po_no == po_ref), None
    )

    if scenario_po:
        vendor_or_ref = scenario_po.supplier_name
        value = scenario_po.value_usd
        inv = next((i for i in scenario.inventory if i.sku == scenario_po.sku), None)
        description = inv.description if inv else scenario_po.sku
        original_need = today + timedelta(days=scenario_po.due_in_days)
        new_expected = original_need + timedelta(days=CUSTOMS_HOLD_DAYS)
        affected.append(
            AffectedItem(
                ref_id=scenario_po.po_number,
                code=scenario_po.sku,
                description=description,
                impact=f"Held {CUSTOMS_HOLD_DAYS} days in customs; arrival slips to {new_expected}.",
                original_need_date=original_need,
                new_expected_date=new_expected,
            )
        )

    if sourcing_po:
        vendor_or_ref = sourcing_po.vendor
        value = sourcing_po.value_usd
        original = sourcing_po.need_by
        new_expected = (
            original + timedelta(days=CUSTOMS_HOLD_DAYS) if original else None
        )
        affected.append(
            AffectedItem(
                ref_id=sourcing_po.po_no,
                code=sourcing_po.code,
                description=sourcing_po.description,
                impact=(
                    f"Customs hold extends arrival to {new_expected}."
                    if original
                    else "Customs hold extends arrival."
                ),
                original_need_date=original,
                new_expected_date=new_expected,
            )
        )
        from .sourcing import get_pr
        pr = get_pr(sourcing_po.pr_no, tenant_id=tenant_id)
        if pr and pr.bom_item_id:
            impact = _milestone_slip_for_bom(
                pr.bom_item_id, sourcing_po.project_id, CUSTOMS_HOLD_DAYS, tenant_id
            )
            if impact:
                milestone_impacts.append(impact)

    if not affected:
        return SimulationResult(
            scenario="customs_hold",
            target=po_ref,
            generated_at=_now(),
            headline=f"No shipment found for {po_ref}.",
            severity="low",
            cost_delta_usd=0,
            schedule_delta_days=0,
            affected_items=[],
            milestone_impacts=[],
            mitigations=[],
            assumptions=[],
        )

    cost_delta = round(value * HOLDING_COST_RATE + 4500, 2)
    severity = _severity_from_cost_and_days(cost_delta, CUSTOMS_HOLD_DAYS)
    headline = (
        f"{po_ref} ({vendor_or_ref}) held {CUSTOMS_HOLD_DAYS} days in customs; "
        f"value at risk ${value:,.0f}."
    )
    mitigations = [
        "Pre-file customs documentation and HS codes with the broker.",
        "Stage critical spares at site to de-risk commissioning slip.",
        "Split shipment so a partial dispatch clears ahead of the held lot.",
    ]
    assumptions = [
        f"{CUSTOMS_HOLD_DAYS}-day customs hold applied to this single PO.",
        f"Cost impact estimated as holding ({HOLDING_COST_RATE * 100:.1f}%) + flat broker/demurrage fee.",
    ]

    return SimulationResult(
        scenario="customs_hold",
        target=po_ref,
        generated_at=_now(),
        headline=headline,
        severity=severity,  # type: ignore[arg-type]
        cost_delta_usd=cost_delta,
        schedule_delta_days=CUSTOMS_HOLD_DAYS,
        affected_items=affected,
        milestone_impacts=milestone_impacts,
        mitigations=mitigations,
        assumptions=assumptions,
    )


# --- Alternate vendor simulation --------------------------------------------


def _simulate_alt_vendor(
    current: str, alternate: str, tenant_id: Optional[str] = None
) -> SimulationResult:
    sc_current = get_vendor_scorecard(current, tenant_id=tenant_id)
    sc_alt = get_vendor_scorecard(alternate, tenant_id=tenant_id)
    suppliers = _suppliers(tenant_id)
    current_supplier = suppliers.get(current)
    alt_supplier = suppliers.get(alternate)

    if not sc_current or not sc_alt or not current_supplier or not alt_supplier:
        missing = current if not sc_current or not current_supplier else alternate
        return SimulationResult(
            scenario="alt_vendor",
            target=current,
            generated_at=_now(),
            headline=f"Vendor scorecard for '{missing}' not found.",
            severity="low",
            cost_delta_usd=0,
            schedule_delta_days=0,
            affected_items=[],
            milestone_impacts=[],
            mitigations=[],
            assumptions=[],
        )

    if sc_current.category.lower() != sc_alt.category.lower():
        return SimulationResult(
            scenario="alt_vendor",
            target=current,
            generated_at=_now(),
            headline=f"{alternate} is not in the same category as {current} — alternate invalid.",
            severity="medium",
            cost_delta_usd=0,
            schedule_delta_days=0,
            affected_items=[],
            milestone_impacts=[],
            mitigations=[
                "Run a category gap analysis before qualifying cross-category substitutes."
            ],
            assumptions=["Simulation requires both vendors to be in the same category."],
        )

    # Orders currently with `current` vendor
    scenario = _demo(tenant_id)
    affected: List[AffectedItem] = []
    total_value = 0.0
    for po in scenario.purchase_orders:
        if po.supplier_name != current or po.status == "received":
            continue
        total_value += po.value_usd
        affected.append(
            AffectedItem(
                ref_id=po.po_number,
                code=po.sku,
                description=po.sku,
                impact=(
                    f"Switch {current} → {alternate}; "
                    f"lead time change {sc_current.lead_time_days}d → {sc_alt.lead_time_days}d."
                ),
            )
        )

    lead_delta = sc_alt.lead_time_days - sc_current.lead_time_days
    score_delta = sc_alt.composite_score - sc_current.composite_score

    # Price heuristic: spend per unit of OTD as proxy
    current_rate = current_supplier.annual_spend_usd / max(current_supplier.on_time_delivery_pct, 1)
    alt_rate = alt_supplier.annual_spend_usd / max(alt_supplier.on_time_delivery_pct, 1)
    relative_price = alt_rate / current_rate if current_rate else 1
    price_delta_pct = round((relative_price - 1) * 100, 1)
    cost_delta = round(total_value * (relative_price - 1) + SWITCHING_COST_USD, 2)

    severity_inputs = abs(cost_delta) + abs(lead_delta) * 500
    severity = (
        "critical" if severity_inputs >= 80_000
        else "high" if severity_inputs >= 40_000
        else "medium" if severity_inputs >= 15_000
        else "low"
    )

    if score_delta >= 0 and lead_delta <= 0 and cost_delta <= 0:
        headline = (
            f"{alternate} looks strictly better — score +{score_delta}, "
            f"lead {lead_delta:+d}d, price change {price_delta_pct:+.1f}%."
        )
    else:
        headline = (
            f"Switching to {alternate}: score {score_delta:+d}, "
            f"lead {lead_delta:+d}d, price {price_delta_pct:+.1f}%, "
            f"one-time switch cost ${SWITCHING_COST_USD:,.0f}."
        )

    mitigations = [
        f"Run a trial batch with {alternate} at low risk quantity before full switchover.",
        "Lock a rate contract now while negotiation leverage is strong.",
        f"Keep {current} as secondary source to protect against future shocks.",
    ]
    assumptions = [
        "Price delta approximated from spend-vs-OTD proxy — replace with quote history when available.",
        f"One-time switching cost estimated at ${SWITCHING_COST_USD:,.0f} (requalification + first-article inspection).",
    ]

    return SimulationResult(
        scenario="alt_vendor",
        target=current,
        generated_at=_now(),
        headline=headline,
        severity=severity,  # type: ignore[arg-type]
        cost_delta_usd=cost_delta,
        schedule_delta_days=max(0, lead_delta),
        affected_items=affected,
        milestone_impacts=[],
        mitigations=mitigations,
        assumptions=assumptions,
    )


# --- Need-by / milestone move ------------------------------------------------


def _resolve_need_by_target(target: str, tenant_id: Optional[str]):
    from .sourcing import get_pr

    raw = (target or "").strip()
    if not raw:
        return None
    for prefix in ("milestone:", "pr:", "bom:"):
        if raw.lower().startswith(prefix):
            raw = raw[len(prefix):]
            break

    pr = get_pr(raw, tenant_id=tenant_id)
    if pr:
        return ("pr", pr, None)

    if ":" in raw:
        pid, code = raw.split(":", 1)
        for p in list_projects(tenant_id=tenant_id):
            if p.project_id != pid:
                continue
            milestone = next((m for m in p.milestones if m.code == code), None)
            if milestone:
                return ("milestone", p, milestone)

    for p in list_projects(tenant_id=tenant_id):
        milestone = next((m for m in p.milestones if m.code == raw), None)
        if milestone:
            return ("milestone", p, milestone)
        item = next(
            (i for i in get_bom(p.project_id, tenant_id=tenant_id) if i.bom_item_id == raw),
            None,
        )
        if item:
            return ("bom", item, None)
    return None


def _simulate_need_by_move(
    target: str, slip_days: int, tenant_id: Optional[str] = None
) -> SimulationResult:
    from .sourcing import get_pr, list_pos, list_prs

    resolved = _resolve_need_by_target(target, tenant_id)
    if resolved is None:
        return SimulationResult(
            scenario="need_by_move",
            target=target,
            generated_at=_now(),
            headline=f"Need-by target '{target}' not found.",
            severity="low",
            cost_delta_usd=0,
            schedule_delta_days=0,
            affected_items=[],
            milestone_impacts=[],
            mitigations=[],
            assumptions=[],
        )

    kind, primary, extra = resolved
    delta = timedelta(days=slip_days)
    affected: List[AffectedItem] = []
    milestone_impacts: List[MilestoneImpact] = []
    total_value = 0.0
    label = target

    prs = []
    if kind == "milestone":
        project, milestone = primary, extra
        label = f"{project.project_id}:{milestone.code}"
        bom_ids = {
            b.bom_item_id
            for b in get_bom(project.project_id, tenant_id=tenant_id)
            if b.milestone_code == milestone.code and b.status != "delivered"
        }
        prs = [
            p for p in list_prs(tenant_id=tenant_id)
            if p.project_id == project.project_id
            and (
                p.milestone_code == milestone.code
                or (p.bom_item_id and p.bom_item_id in bom_ids)
            )
        ]
        original = milestone.required_on_site_date
        new_date = original + delta
        affected.append(
            AffectedItem(
                ref_id=f"{project.project_id}:{milestone.code}",
                code=milestone.code,
                description=milestone.name,
                impact=f"Required-on-site moves from {original} to {new_date}.",
                original_need_date=original,
                new_expected_date=new_date,
            )
        )
        milestone_impacts.append(
            MilestoneImpact(
                project_id=project.project_id,
                project_name=project.name,
                milestone_code=milestone.code,
                milestone_name=milestone.name,
                original_date=original,
                new_date=new_date,
                slip_days=slip_days,
            )
        )
    elif kind == "pr":
        pr = primary
        prs = [pr]
        label = pr.pr_no
        original = pr.need_by
        new_expected = original + delta if original else None
        affected.append(
            AffectedItem(
                ref_id=pr.pr_no,
                code=pr.code,
                description=pr.description,
                impact=(
                    f"PR need-by moves from {original} to {new_expected}."
                    if original
                    else f"PR need-by shifts by {slip_days} days."
                ),
                original_need_date=original,
                new_expected_date=new_expected,
            )
        )
        if pr.bom_item_id:
            impact = _milestone_slip_for_bom(
                pr.bom_item_id, pr.project_id, slip_days, tenant_id
            )
            if impact:
                milestone_impacts.append(impact)
    else:
        item = primary
        label = item.bom_item_id
        original = item.planned_need_date
        new_expected = original + delta if original else None
        affected.append(
            AffectedItem(
                ref_id=item.bom_item_id,
                code=item.code,
                description=item.description,
                impact=(
                    f"BOM need date moves from {original} to {new_expected}."
                    if original
                    else f"BOM need date shifts by {slip_days} days."
                ),
                original_need_date=original,
                new_expected_date=new_expected,
            )
        )
        prs = [
            p for p in list_prs(tenant_id=tenant_id)
            if p.bom_item_id == item.bom_item_id
        ]
        impact = _milestone_slip_for_bom(
            item.bom_item_id, item.project_id, slip_days, tenant_id
        )
        if impact:
            milestone_impacts.append(impact)

    pr_nos = {p.pr_no for p in prs}
    for spo in list_pos(tenant_id=tenant_id):
        if spo.pr_no not in pr_nos or spo.status == "delivered":
            continue
        original = spo.need_by
        new_expected = original + delta if original else None
        affected.append(
            AffectedItem(
                ref_id=spo.po_no,
                code=spo.code,
                description=spo.description,
                impact=(
                    f"Linked PO slides from {original} to {new_expected}."
                    if original
                    else f"Linked PO slides by {slip_days} days."
                ),
                original_need_date=original,
                new_expected_date=new_expected,
            )
        )
        total_value += spo.value_usd
        if not milestone_impacts:
            pr = get_pr(spo.pr_no, tenant_id=tenant_id)
            if pr and pr.bom_item_id:
                impact = _milestone_slip_for_bom(
                    pr.bom_item_id, spo.project_id, slip_days, tenant_id
                )
                if impact:
                    milestone_impacts.append(impact)

    sign = 1 if slip_days >= 0 else -1
    cost_delta = round(total_value * (LD_RATE + EXPEDITE_RATE) * sign, 2)
    direction = "slips" if slip_days >= 0 else "pulls in"
    headline = (
        f"{label} {direction} by {abs(slip_days)} days; "
        f"{len(affected)} line(s) move"
        + (f", ${total_value:,.0f} on linked POs." if total_value else ".")
    )
    severity = _severity_from_cost_and_days(abs(cost_delta), abs(slip_days))
    mitigations = [
        "Re-sequence downstream awards and freight so the new need-by stays protected.",
        "Confirm the date change with engineering / construction before locking POs.",
        "Expedite or defer the linked open orders that now sit on the critical path.",
    ]
    assumptions = [
        f"Need-by / required-on-site shifted by {slip_days:+d} days on {label}.",
        f"Cost delta modelled as LD ({LD_RATE * 100:.1f}%) plus expediting ({EXPEDITE_RATE * 100:.1f}%) on linked open POs.",
    ]
    return SimulationResult(
        scenario="need_by_move",
        target=target,
        generated_at=_now(),
        headline=headline,
        severity=severity,  # type: ignore[arg-type]
        cost_delta_usd=cost_delta,
        schedule_delta_days=slip_days,
        affected_items=affected,
        milestone_impacts=milestone_impacts,
        mitigations=mitigations,
        assumptions=assumptions,
    )


# --- Dispatcher --------------------------------------------------------------


def run_simulation(
    request: SimulationRequest,
    tenant_id: Optional[str] = None,
) -> SimulationResult:
    if request.scenario == "vendor_slip_2w":
        result = _simulate_vendor_slip(
            request.target,
            request.custom_slip_days or DEFAULT_SLIP_DAYS,
            tenant_id,
        )
    elif request.scenario == "customs_hold":
        result = _simulate_customs_hold(request.target, tenant_id)
    elif request.scenario == "need_by_move":
        result = _simulate_need_by_move(
            request.target,
            request.custom_slip_days if request.custom_slip_days is not None else DEFAULT_SLIP_DAYS,
            tenant_id,
        )
    elif request.scenario == "alt_vendor":
        if not request.alternate_vendor:
            return SimulationResult(
                scenario="alt_vendor",
                target=request.target,
                generated_at=_now(),
                headline="Alternate vendor is required for this simulation.",
                severity="low",
                cost_delta_usd=0,
                schedule_delta_days=0,
                affected_items=[],
                milestone_impacts=[],
                mitigations=[],
                assumptions=[],
            )
        result = _simulate_alt_vendor(
            request.target, request.alternate_vendor, tenant_id
        )
    else:
        raise ValueError(f"Unknown scenario: {request.scenario}")

    return result


_ALLOWED_ACTIONS: Set[str] = {
    "followup", "expedite", "open_po", "open_vendor", "open_project",
}
_PO_RE = re.compile(r"\b((?:PO|SPO)-[A-Z0-9-]+)\b", re.I)
_PR_RE = re.compile(r"\b(PR-[A-Z0-9-]+)\b", re.I)
_MS_RE = re.compile(r"\b(PRJ-[A-Z0-9-]+[:/]M\w+)\b", re.I)
_DAYS_RE = re.compile(r"(\d+)\s*(?:day|days|d)\b", re.I)
_WEEKS_RE = re.compile(r"(\d+)\s*(?:week|weeks|w)\b", re.I)


def _first_po_ref(result: SimulationResult) -> Optional[str]:
    for item in result.affected_items:
        if _PO_RE.match(item.ref_id or ""):
            return item.ref_id
    if result.scenario == "customs_hold" and _PO_RE.match(result.target or ""):
        return result.target
    return None


def _deterministic_brief(result: SimulationResult) -> SimulationBrief:
    po = _first_po_ref(result)
    project_id = result.milestone_impacts[0].project_id if result.milestone_impacts else None
    action: SimulationPrimaryAction = "expedite"
    ref: Optional[str] = po
    if result.scenario in {"vendor_slip_2w", "customs_hold"} and po:
        action = "followup"
    elif result.scenario == "alt_vendor":
        action = "open_vendor"
        ref = result.target
    elif result.scenario == "need_by_move":
        action = "open_project"
        ref = project_id or result.target.split(":")[0]
    watch = list(result.mitigations[:2])
    return SimulationBrief(
        why=result.headline,
        primary_action=action,
        action_ref=ref,
        watch=watch,
        source="deterministic",
    )


def build_simulation_brief(result: SimulationResult) -> SimulationBrief:
    """Decision brief. DeepSeek when enabled; always falls back to the headline."""
    fallback = _deterministic_brief(result)
    from .llm import llm_json, is_enabled, llm_source

    if not is_enabled():
        return fallback

    import json as _json
    allowed_refs = [i.ref_id for i in result.affected_items] + [result.target]
    allowed_refs += [m.project_id for m in result.milestone_impacts]
    context = {
        "scenario": result.scenario,
        "target": result.target,
        "headline": result.headline,
        "severity": result.severity,
        "cost_delta_usd": result.cost_delta_usd,
        "schedule_delta_days": result.schedule_delta_days,
        "affected_items": [
            {"ref_id": i.ref_id, "code": i.code, "impact": i.impact}
            for i in result.affected_items[:12]
        ],
        "milestone_impacts": [
            {"milestone": m.milestone_name, "code": m.milestone_code, "slip_days": m.slip_days}
            for m in result.milestone_impacts
        ],
        "mitigations": result.mitigations,
        "allowed_refs": allowed_refs,
        "allowed_actions": sorted(_ALLOWED_ACTIONS),
    }
    system = (
        "You are an EPC procurement head. Given a deterministic what-if result, "
        "write a decision brief. Do not invent cost, days, or refs. "
        "Return JSON: {\"why\": 2-3 sentences citing the given cost/days/milestones, "
        "\"primary_action\": one of the allowed_actions, "
        "\"action_ref\": one of allowed_refs or null, "
        "\"watch\": 1-2 short strings}."
    )
    parsed = llm_json(system, _json.dumps(context, default=str), max_tokens=500, timeout=20)
    if not parsed or not parsed.get("why"):
        return fallback
    action = parsed.get("primary_action")
    if action not in _ALLOWED_ACTIONS:
        action = fallback.primary_action
    ref = parsed.get("action_ref") or fallback.action_ref
    if ref and ref not in allowed_refs:
        ref = fallback.action_ref
    watch = parsed.get("watch") if isinstance(parsed.get("watch"), list) else fallback.watch
    return SimulationBrief(
        why=str(parsed["why"]).strip(),
        primary_action=action,  # type: ignore[arg-type]
        action_ref=ref,
        watch=[str(w) for w in watch][:3],
        source=llm_source(),
    )


def _catalog(tenant_id: Optional[str]) -> Tuple[List[str], List[str], List[str], List[str]]:
    from .sourcing import list_pos, list_prs
    from .vendor_intel import list_vendor_summaries

    vendors = [v.vendor for v in list_vendor_summaries(tenant_id=tenant_id)]
    pos = [p.po_no for p in list_pos(tenant_id)]
    demo = _demo(tenant_id)
    pos.extend(p.po_number for p in demo.purchase_orders)
    vendors.extend(p.supplier_name for p in demo.purchase_orders)
    vendors.extend(s.name for s in demo.suppliers)
    prs = [p.pr_no for p in list_prs(tenant_id=tenant_id)]
    milestones: List[str] = []
    for project in list_projects(tenant_id=tenant_id):
        for m in project.milestones:
            milestones.append(f"{project.project_id}:{m.code}")
    return (
        _uniq_cap(vendors, 40),
        _uniq_cap(pos, 40),
        _uniq_cap(prs, 40),
        _uniq_cap(milestones, 40),
    )


def _uniq_cap(items: List[str], n: int) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
        if len(out) >= n:
            break
    return out


def _match_vendor(ask: str, vendors: List[str]) -> Optional[str]:
    low = ask.lower()
    best: Optional[str] = None
    for vendor in vendors:
        if vendor.lower() in low and (best is None or len(vendor) > len(best)):
            best = vendor
    if best:
        return best
    tokens = set(re.findall(r"[a-z0-9&]+", low))
    for vendor in vendors:
        first = vendor.lower().split()[0]
        if len(first) > 3 and first in tokens:
            return vendor
    return None


def _extract_days(ask: str) -> Optional[int]:
    weeks = _WEEKS_RE.search(ask)
    if weeks:
        return int(weeks.group(1)) * 7
    days = _DAYS_RE.search(ask)
    if days:
        return int(days.group(1))
    return None


def _rule_parse(
    ask: str,
    vendors: List[str],
    pos: List[str],
    prs: List[str],
    milestones: List[str],
) -> ParseSimulationReply:
    low = ask.lower()
    days = _extract_days(ask)
    po_hit = _PO_RE.search(ask)
    pr_hit = _PR_RE.search(ask)
    ms_hit = _MS_RE.search(ask)
    vendor = _match_vendor(ask, vendors)

    if "hold" in low or "customs" in low:
        target = po_hit.group(1).upper() if po_hit else None
        if target:
            return ParseSimulationReply(ok=True, scenario="customs_hold", target=target)
    if any(w in low for w in ("alternate", "alternative", "switch vendor", "swap")):
        alt = None
        if vendor:
            others = [v for v in vendors if v != vendor]
            alt = others[0] if others else None
        if vendor:
            return ParseSimulationReply(
                ok=True, scenario="alt_vendor", target=vendor, alternate_vendor=alt, custom_slip_days=days,
            )
    if any(w in low for w in ("need-by", "need by", "milestone", "ros", "required on site")):
        target = None
        if ms_hit:
            target = ms_hit.group(1).replace("/", ":")
        elif pr_hit:
            target = pr_hit.group(1).upper()
        elif milestones:
            target = milestones[0]
        if target:
            return ParseSimulationReply(
                ok=True, scenario="need_by_move", target=target, custom_slip_days=days,
            )
    if any(w in low for w in ("slip", "delay", "late", "slides")) or vendor:
        if vendor:
            return ParseSimulationReply(
                ok=True, scenario="vendor_slip_2w", target=vendor, custom_slip_days=days,
            )
    return ParseSimulationReply(ok=False, reason="Could not parse — use the cards.")


def _target_allowed(
    reply: ParseSimulationReply,
    vendors: List[str],
    pos: List[str],
    prs: List[str],
    milestones: List[str],
) -> bool:
    if not reply.target:
        return False
    t = reply.target
    if reply.scenario == "vendor_slip_2w":
        return t in vendors
    if reply.scenario == "customs_hold":
        return t in pos or any(p.upper() == t.upper() for p in pos)
    if reply.scenario == "alt_vendor":
        return t in vendors
    if reply.scenario == "need_by_move":
        return t in milestones or t in prs
    return False


def parse_simulation_ask(ask: str, tenant_id: Optional[str] = None) -> ParseSimulationReply:
    text = (ask or "").strip()
    if not text:
        return ParseSimulationReply(ok=False, reason="Empty question.")

    vendors, pos, prs, milestones = _catalog(tenant_id)
    parsed: Optional[ParseSimulationReply] = None

    from .llm import llm_json, is_enabled
    if is_enabled():
        import json as _json
        system = (
            "Map a buyer what-if question to a simulation request. "
            "Use ONLY names/ids from the catalog. Do not invent POs or vendors. "
            "Return JSON: {\"ok\": bool, \"scenario\": one of "
            "vendor_slip_2w|customs_hold|alt_vendor|need_by_move or null, "
            "\"target\": string or null, \"alternate_vendor\": string or null, "
            "\"custom_slip_days\": int or null, \"reason\": string or null}."
        )
        user = _json.dumps({
            "ask": text,
            "vendors": vendors,
            "pos": pos,
            "prs": prs,
            "milestones": milestones,
        })
        raw = llm_json(system, user, max_tokens=300, timeout=15)
        if raw and raw.get("ok") and raw.get("scenario") and raw.get("target"):
            parsed = ParseSimulationReply(
                ok=True,
                scenario=raw.get("scenario"),
                target=raw.get("target"),
                alternate_vendor=raw.get("alternate_vendor"),
                custom_slip_days=raw.get("custom_slip_days"),
            )

    if parsed is None:
        parsed = _rule_parse(text, vendors, pos, prs, milestones)

    if not parsed.ok:
        return parsed
    if not _target_allowed(parsed, vendors, pos, prs, milestones):
        return ParseSimulationReply(
            ok=False, reason="Target is not in this tenant's book. Use the cards.",
        )
    if parsed.scenario == "customs_hold" and parsed.target:
        parsed.target = next((p for p in pos if p.upper() == parsed.target.upper()), parsed.target)
    return parsed
