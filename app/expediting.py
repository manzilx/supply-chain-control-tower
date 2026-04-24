"""Expediting module.

Builds a unified queue of open orders (demo scenario POs + sourcing POs),
predicts slip probability / expected slip days, buckets by urgency, and drafts
follow-up emails with tone-aware templates.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Dict, List, Optional

from .sample_data import build_demo_request
from .schemas import (
    DraftFollowupRequest,
    EmailTone,
    ExpediteItem,
    ExpediteQueue,
    ExpediteSummary,
    ExpediteUrgency,
    FollowupEmail,
    PurchaseOrder,
    SourcingPO,
    SupplierRecord,
)
from .sourcing import list_pos as _list_sourcing_pos


# --- Prediction --------------------------------------------------------------


def _supplier_map() -> Dict[str, SupplierRecord]:
    return {s.name: s for s in build_demo_request().suppliers}


def _scenario_inventory_by_sku() -> Dict[str, object]:
    scenario = build_demo_request()
    return {item.sku: item for item in scenario.inventory}


def _urgency(prob: int) -> ExpediteUrgency:
    if prob >= 70:
        return "escalate"
    if prob >= 40:
        return "nudge"
    if prob >= 20:
        return "watch"
    return "ok"


def _predict_scenario_po(po: PurchaseOrder, suppliers: Dict[str, SupplierRecord]) -> ExpediteItem:
    supplier = suppliers.get(po.supplier_name)
    reasons: List[str] = []
    base = 8

    if po.status == "delayed":
        base += 55
        reasons.append("already flagged delayed")
    elif po.status == "in_transit" and po.due_in_days <= 7:
        base += 25
        reasons.append("in transit with <1 week runway")
    elif po.status in {"planned", "released"} and po.due_in_days <= 7:
        base += 35
        reasons.append("unreleased/just-released with <1 week runway")

    if supplier is not None:
        if supplier.on_time_delivery_pct < 95:
            penalty = min(30, (95 - supplier.on_time_delivery_pct) * 3)
            base += int(penalty)
            reasons.append(f"vendor OTD {supplier.on_time_delivery_pct:.0f}%")
        if supplier.quality_ppm > 1000:
            base += 6
            reasons.append(f"elevated PPM {supplier.quality_ppm}")
        if supplier.risk_flags:
            base += min(20, 5 * len(supplier.risk_flags))
            reasons.append(f"flags: {', '.join(supplier.risk_flags)}")

    if po.due_in_days <= 14 and po.status != "delayed":
        base += 10
        reasons.append("inside 14-day window")

    if not po.expedite_possible and po.status in {"planned", "released", "in_transit"}:
        base += 6
        reasons.append("no expedite lever available")

    prob = max(0, min(95, base))
    lead_buffer = max(7, int(po.due_in_days * 0.3))
    slip_days = int(round((prob / 100) * lead_buffer))

    # Find a SKU description if available
    inv = _scenario_inventory_by_sku().get(po.sku)
    description = getattr(inv, "description", None) if inv else None

    return ExpediteItem(
        po_number=po.po_number,
        supplier_name=po.supplier_name,
        sku=po.sku,
        description=description,
        quantity=po.quantity,
        value_usd=po.value_usd,
        due_in_days=po.due_in_days,
        status=po.status,
        predicted_slip_days=slip_days,
        slip_probability_pct=prob,
        urgency=_urgency(prob),
        reasons=reasons or ["no specific risk signals"],
        source="scenario",
    )


def _days_until(d: Optional[date]) -> int:
    if d is None:
        return 60
    return (d - date.today()).days


def _predict_sourcing_po(po: SourcingPO, suppliers: Dict[str, SupplierRecord]) -> ExpediteItem:
    supplier = suppliers.get(po.vendor)
    reasons: List[str] = []
    due_in_days = _days_until(po.need_by)
    base = 6

    if po.status == "in_transit" and due_in_days <= 7:
        base += 25
        reasons.append("in transit with tight runway")
    if po.status == "draft" and due_in_days <= po.lead_time_days:
        base += 40
        reasons.append("PO still in draft; lead time exceeds days-to-need")
    if supplier is not None:
        if supplier.on_time_delivery_pct < 95:
            penalty = min(28, (95 - supplier.on_time_delivery_pct) * 3)
            base += int(penalty)
            reasons.append(f"vendor OTD {supplier.on_time_delivery_pct:.0f}%")
        if supplier.risk_flags:
            base += min(18, 5 * len(supplier.risk_flags))
            reasons.append(f"flags: {', '.join(supplier.risk_flags)}")
    else:
        reasons.append("vendor not on approved list — limited history")
        base += 5

    if due_in_days <= 14:
        base += 8

    prob = max(0, min(95, base))
    lead_buffer = max(7, int(max(due_in_days, 7) * 0.3))
    slip_days = int(round((prob / 100) * lead_buffer))

    return ExpediteItem(
        po_number=po.po_no,
        supplier_name=po.vendor,
        sku=po.code,
        description=po.description,
        quantity=po.quantity,
        value_usd=po.value_usd,
        due_in_days=due_in_days,
        status=po.status,
        predicted_slip_days=slip_days,
        slip_probability_pct=prob,
        urgency=_urgency(prob),
        reasons=reasons or ["no specific risk signals"],
        source="sourcing",
        project_id=po.project_id,
    )


def build_expedite_queue() -> ExpediteQueue:
    suppliers = _supplier_map()
    scenario = build_demo_request()

    items: List[ExpediteItem] = []

    for po in scenario.purchase_orders:
        if po.status == "received":
            continue
        items.append(_predict_scenario_po(po, suppliers))

    for spo in _list_sourcing_pos():
        if spo.status == "delivered":
            continue
        items.append(_predict_sourcing_po(spo, suppliers))

    items.sort(key=lambda x: (-x.slip_probability_pct, x.due_in_days))

    summary = ExpediteSummary(
        total=len(items),
        ok=sum(1 for i in items if i.urgency == "ok"),
        watch=sum(1 for i in items if i.urgency == "watch"),
        nudge=sum(1 for i in items if i.urgency == "nudge"),
        escalate=sum(1 for i in items if i.urgency == "escalate"),
        value_at_risk_usd=round(
            sum(i.value_usd for i in items if i.urgency in {"nudge", "escalate"}),
            2,
        ),
    )

    return ExpediteQueue(
        generated_at=datetime.now(timezone.utc),
        items=items,
        summary=summary,
    )


def get_expedite_item(po_number: str) -> Optional[ExpediteItem]:
    for item in build_expedite_queue().items:
        if item.po_number == po_number:
            return item
    return None


# --- Follow-up email drafter -------------------------------------------------


_TONE_INTRO: Dict[EmailTone, str] = {
    "standard": (
        "Could you share the latest progress on this order and flag any concerns "
        "we should be aware of?"
    ),
    "firm": (
        "We have observed schedule risk on this order. Please share a written "
        "recovery plan if dispatch is at risk, including any expediting levers "
        "you can pull."
    ),
    "urgent": (
        "This order is flagged as critical to our project schedule. We need a "
        "written recovery plan within 48 hours, with daily progress updates "
        "until dispatch is confirmed."
    ),
}


def _requested_documents(item: ExpediteItem) -> List[str]:
    docs = ["current manufacturing / dispatch status", "expected dispatch date"]
    desc = (item.description or "").lower()
    sku = (item.sku or "").lower()

    if any(keyword in desc + sku for keyword in ["valve", "pump", "transformer", "switchgear", "motor"]):
        docs.extend(["GA drawing approval status", "QAP and ITP sign-off", "MDR progress"])
    if any(keyword in desc + sku for keyword in ["plc", "automation", "control"]):
        docs.extend(["FAT plan", "I/O schedule sign-off"])
    if any(keyword in desc + sku for keyword in ["cable", "busbar", "tube", "steel", "structural"]):
        docs.extend(["mill test certificates", "NDE reports"])

    docs.append("updated dispatch / packing list")
    return docs


def _tone_subject_prefix(tone: EmailTone) -> str:
    if tone == "urgent":
        return "URGENT"
    if tone == "firm":
        return "ACTION REQUIRED"
    return "Status request"


def draft_followup_email(po_number: str, request: DraftFollowupRequest) -> Optional[FollowupEmail]:
    item = get_expedite_item(po_number)
    if not item:
        return None

    docs = _requested_documents(item) if request.request_documents else [
        "current manufacturing / dispatch status",
        "expected dispatch date",
    ]

    vendor_slug = item.supplier_name.lower().replace(" ", "").replace("&", "and")
    to_placeholder = f"procurement@{vendor_slug}.com"

    prefix = _tone_subject_prefix(request.tone)
    subject = f"[{prefix}] {item.po_number} — status + recovery plan request"

    due_phrase = (
        f"due in {item.due_in_days} days"
        if item.due_in_days >= 0
        else f"overdue by {abs(item.due_in_days)} days"
    )

    requested_list = "\n".join(f"  • {d}" for d in docs)

    extra = f"\n\nAdditional context: {request.extra_notes.strip()}" if request.extra_notes else ""

    signature_lines = [
        "Best regards,",
        "Procurement — Control Tower",
        "Arcforge Engineering",
    ]

    body = (
        f"Hi {item.supplier_name} team,\n\n"
        f"I'm writing about purchase order {item.po_number} for "
        f"{item.description or item.sku or 'this line'} "
        f"(quantity {item.quantity}), currently {due_phrase} with status '{item.status}'.\n\n"
        f"{_TONE_INTRO[request.tone]}\n\n"
        f"Please confirm the following:\n{requested_list}\n\n"
        f"Key risk signals we are tracking on this order:\n"
        + "\n".join(f"  • {r}" for r in item.reasons)
        + f"\n\nThis shipment is on the critical path for the project and any "
        f"slip beyond {max(1, item.predicted_slip_days)} day(s) will directly "
        f"affect our construction schedule."
        + extra
        + "\n\n"
        + "\n".join(signature_lines)
    )

    return FollowupEmail(
        po_number=item.po_number,
        vendor=item.supplier_name,
        tone=request.tone,
        to_placeholder=to_placeholder,
        subject=subject,
        body=body,
        requested_documents=docs,
        generated_at=datetime.now(timezone.utc),
    )
