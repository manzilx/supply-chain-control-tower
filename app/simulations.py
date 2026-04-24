"""Risk simulations.

Three what-if simulators that reuse scorecards, BOMs, and sourcing state:

- vendor_slip_2w  : what if `<vendor>` slips every open order by ~14 days?
- customs_hold    : what if `<po_no>` gets held in customs for ~21 days?
- alt_vendor      : what if we replaced `<vendor>` with `<alternate_vendor>`?

Returns a uniform SimulationResult so the UI can render any scenario with the
same component.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

from .planning import get_bom, list_projects
from .sample_data import build_demo_request
from .schemas import (
    AffectedItem,
    MilestoneImpact,
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


def _suppliers() -> Dict[str, SupplierRecord]:
    return {s.name: s for s in build_demo_request().suppliers}


def _project_name(pid: str) -> str:
    for p in list_projects():
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
) -> Optional[MilestoneImpact]:
    items = get_bom(project_id)
    item = next((i for i in items if i.bom_item_id == bom_item_id), None)
    if not item or not item.milestone_code:
        return None
    for p in list_projects():
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


def _simulate_vendor_slip(vendor: str, slip_days: int) -> SimulationResult:
    scenario = build_demo_request()
    sourcing_pos = _list_sourcing_pos()
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
        pr = get_pr(spo.pr_no)
        if pr and pr.bom_item_id:
            impact = _milestone_slip_for_bom(pr.bom_item_id, spo.project_id, slip_days)
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


def _simulate_customs_hold(po_ref: str) -> SimulationResult:
    scenario = build_demo_request()
    affected: List[AffectedItem] = []
    milestone_impacts: List[MilestoneImpact] = []
    value = 0.0
    vendor_or_ref = po_ref
    today = date.today()

    scenario_po = next((p for p in scenario.purchase_orders if p.po_number == po_ref), None)
    sourcing_po: Optional[SourcingPO] = next(
        (p for p in _list_sourcing_pos() if p.po_no == po_ref), None
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
        pr = get_pr(sourcing_po.pr_no)
        if pr and pr.bom_item_id:
            impact = _milestone_slip_for_bom(pr.bom_item_id, sourcing_po.project_id, CUSTOMS_HOLD_DAYS)
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


def _simulate_alt_vendor(current: str, alternate: str) -> SimulationResult:
    sc_current = get_vendor_scorecard(current)
    sc_alt = get_vendor_scorecard(alternate)
    suppliers = _suppliers()
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
    scenario = build_demo_request()
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


# --- Dispatcher --------------------------------------------------------------


def run_simulation(request: SimulationRequest) -> SimulationResult:
    if request.scenario == "vendor_slip_2w":
        return _simulate_vendor_slip(
            request.target, request.custom_slip_days or DEFAULT_SLIP_DAYS
        )
    if request.scenario == "customs_hold":
        return _simulate_customs_hold(request.target)
    if request.scenario == "alt_vendor":
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
        return _simulate_alt_vendor(request.target, request.alternate_vendor)
    raise ValueError(f"Unknown scenario: {request.scenario}")
