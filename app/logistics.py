"""Logistics module.

Tracks shipments for open orders (scenario POs + sourcing POs), records events
per stage, and recommends freight mode based on urgency / value.

Events are kept in a module-level store so the UI can append them. Seed
demo events make the tracker non-empty on first boot.
"""

from __future__ import annotations

from ._cache import invalidates_cache

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

from .sample_data import build_demo_request
from .schemas import (
    AddShipmentEventRequest,
    FreightMode,
    LogisticsQueue,
    LogisticsSummary,
    ModeRecommendation,
    PurchaseOrder,
    Shipment,
    ShipmentEvent,
    ShipmentStage,
    SourcingPO,
    SupplierRecord,
)
from .planning import get_project, list_projects
from .sourcing import list_pos as _list_sourcing_pos


# --- Event store -------------------------------------------------------------


_events: Dict[str, List[ShipmentEvent]] = defaultdict(list)
_event_counter = {"n": 0}
_seeded = False


def _next_event_id() -> str:
    _event_counter["n"] += 1
    return f"EV-{_event_counter['n']:05d}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- Mode heuristics ---------------------------------------------------------


_BASELINE_TRANSIT: Dict[FreightMode, int] = {
    "sea": 35,
    "air": 5,
    "road": 10,
    "rail": 18,
    "local": 2,
}

_MODE_COST_MULTIPLIER: Dict[FreightMode, float] = {
    "sea": 1.0,
    "air": 5.0,
    "road": 1.4,
    "rail": 1.2,
    "local": 1.1,
}


def _infer_default_mode(origin_country: Optional[str], destination_country: str = "India") -> FreightMode:
    if not origin_country:
        return "sea"
    if origin_country.lower() in {"india"} and destination_country.lower() == "india":
        return "road"
    return "sea"


def _supplier_map(tenant_id: Optional[str] = None) -> Dict[str, SupplierRecord]:
    return {s.name: s for s in build_demo_request(tenant_id or "arcforge").suppliers}


def _inventory_sku_map() -> Dict[str, object]:
    return {i.sku: i for i in build_demo_request().inventory}


# --- Stage progression -------------------------------------------------------


_STAGE_ORDER: List[ShipmentStage] = [
    "manufacturing",
    "ready_to_dispatch",
    "dispatched",
    "in_transit",
    "at_port",
    "at_customs",
    "last_mile",
    "delivered",
]


def _current_stage(po_ref: str, fallback: ShipmentStage) -> ShipmentStage:
    events = _events.get(po_ref)
    if not events:
        return fallback
    # latest event wins
    return sorted(events, key=lambda e: e.at)[-1].stage


def _bottleneck_hint(stage: ShipmentStage, origin: Optional[str], flags: List[str]) -> Optional[str]:
    if stage == "at_customs":
        return "Customs clearance — flag to broker and prepare documentation."
    if stage == "at_port" and any("port" in f.lower() for f in flags):
        return "Port congestion — monitor berth allocation daily."
    if stage == "manufacturing" and any("capacity" in f.lower() for f in flags):
        return "Supplier manufacturing constraint — confirm slot and inputs."
    return None


# --- Seeding -----------------------------------------------------------------


def _seed_events_if_needed() -> None:
    global _seeded
    if _seeded:
        return
    _seeded = True

    scenario = build_demo_request()
    base = _now() - timedelta(days=18)

    # PO-24017 (Helios, delayed) — stuck in manufacturing
    for po in scenario.purchase_orders:
        if po.po_number == "PO-24017":
            _append_event(po.po_number, ShipmentEvent(
                event_id=_next_event_id(),
                po_ref=po.po_number,
                stage="manufacturing",
                at=base,
                location="Coimbatore, India",
                note="Casting machining started; heat treatment pending.",
            ))
            _append_event(po.po_number, ShipmentEvent(
                event_id=_next_event_id(),
                po_ref=po.po_number,
                stage="manufacturing",
                at=base + timedelta(days=14),
                location="Coimbatore, India",
                note="Dimensional NCR under review; delay confirmed.",
            ))
        if po.po_number == "PO-24028":
            _append_event(po.po_number, ShipmentEvent(
                event_id=_next_event_id(),
                po_ref=po.po_number,
                stage="dispatched",
                at=base + timedelta(days=3),
                location="Frankfurt, Germany",
                note="Packed and collected by forwarder.",
            ))
            _append_event(po.po_number, ShipmentEvent(
                event_id=_next_event_id(),
                po_ref=po.po_number,
                stage="in_transit",
                at=base + timedelta(days=7),
                location="Mediterranean",
                note="Aboard MSC Fortuna.",
            ))
            _append_event(po.po_number, ShipmentEvent(
                event_id=_next_event_id(),
                po_ref=po.po_number,
                stage="at_port",
                at=base + timedelta(days=16),
                location="Hamburg, Germany",
                note="Port congestion — vessel waiting on berth.",
            ))
        if po.po_number == "PO-24044":
            _append_event(po.po_number, ShipmentEvent(
                event_id=_next_event_id(),
                po_ref=po.po_number,
                stage="ready_to_dispatch",
                at=base + timedelta(days=12),
                location="Klang, Malaysia",
                note="Export docs complete; pickup scheduled.",
            ))


def _append_event(po_ref: str, event: ShipmentEvent) -> None:
    _events[po_ref].append(event)


# --- Public API: shipments ---------------------------------------------------


def _origin_destination(
    supplier: Optional[SupplierRecord],
    project_id: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    origin = supplier.country if supplier else None
    destination = None
    if project_id:
        project = get_project(project_id)
        if project:
            destination = project.site
    return origin, destination


def _shipment_from_scenario(po: PurchaseOrder, suppliers: Dict[str, SupplierRecord]) -> Shipment:
    inv_map = _inventory_sku_map()
    inv = inv_map.get(po.sku)
    description = getattr(inv, "description", None) if inv else None
    supplier = suppliers.get(po.supplier_name)
    origin, destination = _origin_destination(supplier, None)

    fallback_stage: ShipmentStage = {
        "planned": "manufacturing",
        "released": "manufacturing",
        "in_transit": "in_transit",
        "delayed": "manufacturing",
        "received": "delivered",
    }.get(po.status, "manufacturing")
    stage = _current_stage(po.po_number, fallback_stage)
    mode = _infer_default_mode(origin)

    required = None
    estimated = None
    if po.due_in_days is not None:
        required = date.today() + timedelta(days=po.due_in_days)
        estimated = required
        if po.status == "delayed":
            estimated = required + timedelta(days=14)

    flags = supplier.risk_flags if supplier else []
    bottleneck = _bottleneck_hint(stage, origin, flags)
    if po.status == "delayed" and not bottleneck:
        bottleneck = "PO already flagged delayed — confirm recovery plan."

    slack = None
    if required and estimated:
        slack = (required - estimated).days

    return Shipment(
        po_ref=po.po_number,
        source="scenario",
        vendor=po.supplier_name,
        code=po.sku,
        description=description,
        origin_country=origin,
        destination_site=destination,
        value_usd=po.value_usd,
        quantity=po.quantity,
        mode=mode,
        current_stage=stage,
        required_on_site=required,
        estimated_arrival=estimated,
        bottleneck=bottleneck,
        slack_days=slack,
        events=list(_events.get(po.po_number, [])),
    )


def _shipment_from_sourcing(po: SourcingPO, suppliers: Dict[str, SupplierRecord]) -> Shipment:
    supplier = suppliers.get(po.vendor)
    origin, destination = _origin_destination(supplier, po.project_id)

    fallback_stage: ShipmentStage = {
        "draft": "manufacturing",
        "released": "manufacturing",
        "in_transit": "in_transit",
        "delivered": "delivered",
    }.get(po.status, "manufacturing")
    stage = _current_stage(po.po_no, fallback_stage)

    mode = _infer_default_mode(origin)

    required = po.need_by
    estimated = None
    if required:
        estimated = required
    flags = supplier.risk_flags if supplier else []
    bottleneck = _bottleneck_hint(stage, origin, flags)

    slack = None
    if required and estimated:
        slack = (required - estimated).days

    return Shipment(
        po_ref=po.po_no,
        source="sourcing",
        vendor=po.vendor,
        code=po.code,
        description=po.description,
        origin_country=origin,
        destination_site=destination,
        value_usd=po.value_usd,
        quantity=po.quantity,
        mode=mode,
        current_stage=stage,
        required_on_site=required,
        estimated_arrival=estimated,
        bottleneck=bottleneck,
        slack_days=slack,
        events=list(_events.get(po.po_no, [])),
    )


from ._cache import ttl_cache


@ttl_cache(ttl_seconds=10.0)
def list_shipments(tenant_id: Optional[str] = None) -> LogisticsQueue:
    _seed_events_if_needed()
    suppliers = _supplier_map(tenant_id=tenant_id)
    scenario = build_demo_request(tenant_id or "arcforge")

    shipments: List[Shipment] = []
    for po in scenario.purchase_orders:
        if po.status == "received":
            continue
        shipments.append(_shipment_from_scenario(po, suppliers))

    for spo in _list_sourcing_pos(tenant_id=tenant_id):
        if spo.status == "delivered":
            continue
        shipments.append(_shipment_from_sourcing(spo, suppliers))

    shipments.sort(
        key=lambda s: (
            0 if s.bottleneck else 1,
            s.slack_days if s.slack_days is not None else 999,
        )
    )

    in_motion = sum(
        1
        for s in shipments
        if s.current_stage in {"dispatched", "in_transit", "at_port", "at_customs", "last_mile"}
    )
    bottleneck = sum(1 for s in shipments if s.bottleneck)
    delivered = sum(1 for s in shipments if s.current_stage == "delivered")
    value_in_motion = sum(
        s.value_usd
        for s in shipments
        if s.current_stage not in {"delivered"}
    )

    summary = LogisticsSummary(
        total=len(shipments),
        in_motion=in_motion,
        at_bottleneck=bottleneck,
        delivered=delivered,
        value_in_motion_usd=round(value_in_motion, 2),
    )

    return LogisticsQueue(
        generated_at=_now(),
        shipments=shipments,
        summary=summary,
    )


def get_shipment(po_ref: str, tenant_id: Optional[str] = None) -> Optional[Shipment]:
    for s in list_shipments(tenant_id=tenant_id).shipments:
        if s.po_ref == po_ref:
            return s
    return None


@invalidates_cache
def add_event(
    po_ref: str,
    request: AddShipmentEventRequest,
    tenant_id: Optional[str] = None,
) -> Optional[ShipmentEvent]:
    shipment = get_shipment(po_ref, tenant_id=tenant_id)
    if not shipment:
        return None
    event = ShipmentEvent(
        event_id=_next_event_id(),
        po_ref=po_ref,
        stage=request.stage,
        at=_now(),
        location=request.location,
        note=request.note,
    )
    _append_event(po_ref, event)

    # Audit trail (enrich with vendor + bom_code from linked PO if available)
    from .audit import emit
    from .sourcing import _pos as _sourcing_pos, _prs  # type: ignore[attr-defined]
    is_delivery = request.stage == "delivered"
    vendor = shipment.vendor
    bom_code = None
    bom_item_id = None
    project_id = None
    po = _sourcing_pos.get(po_ref)
    if po:
        bom_code = po.code
        project_id = po.project_id
        pr_for_po = _prs.get(po.pr_no)
        if pr_for_po:
            bom_item_id = pr_for_po.bom_item_id
    emit(
        action="delivered" if is_delivery else "stage_advanced",
        entity_kind="shipment_event",
        entity_id=event.event_id,
        subject=f"{po_ref} → {request.stage}",
        summary=(
            f"Shipment {po_ref} advanced to {request.stage}"
            + (f" at {request.location}" if request.location else "")
            + (f" · {request.note}" if request.note else "")
        ),
        source="api",
        tenant_id=po.tenant_id if po else (tenant_id or ""),
        project_id=project_id,
        bom_item_id=bom_item_id,
        bom_code=bom_code,
        po_no=po_ref,
        vendor=vendor,
        metadata={
            "stage": request.stage,
            "location": request.location,
            "note": request.note,
        },
    )
    return event


# --- Mode recommender --------------------------------------------------------


def recommend_mode(po_ref: str, tenant_id: Optional[str] = None) -> Optional[ModeRecommendation]:
    shipment = get_shipment(po_ref, tenant_id=tenant_id)
    if not shipment:
        return None

    required = shipment.required_on_site
    days_until_need = (required - date.today()).days if required else None

    candidate: FreightMode = shipment.mode
    rationale_parts: List[str] = []

    if days_until_need is not None and days_until_need < _BASELINE_TRANSIT[shipment.mode]:
        if days_until_need < 7:
            candidate = "air"
            rationale_parts.append(f"Only {days_until_need} days to need; baseline {shipment.mode} lead time is {_BASELINE_TRANSIT[shipment.mode]} days.")
        elif days_until_need < 14 and shipment.mode != "air":
            candidate = "air"
            rationale_parts.append("Tight schedule — air freight recovers the slip at ~5x cost.")
    elif days_until_need is not None and days_until_need > _BASELINE_TRANSIT["sea"] + 21:
        candidate = "sea"
        rationale_parts.append("Generous schedule — sea freight is the lowest-cost option.")

    if not rationale_parts:
        rationale_parts.append("Current mode matches urgency and budget.")

    driver = "schedule" if candidate != shipment.mode else "budget"

    return ModeRecommendation(
        po_ref=po_ref,
        current_mode=shipment.mode,
        recommended_mode=candidate,
        transit_days_estimate=_BASELINE_TRANSIT[candidate],
        cost_multiplier=_MODE_COST_MULTIPLIER[candidate],
        rationale=" ".join(rationale_parts),
        days_until_need=days_until_need,
    )
