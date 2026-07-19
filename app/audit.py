"""Audit trail — every mutation across the procurement lifecycle.

Two views build on this:

  - Progress tracking: per-entity timeline ("what's happened to BOM HYD-CV-001?")
  - Company audit:    global filterable feed + export

In-memory ring buffer (default 10,000 events). On boot the buffer is empty;
subsequent mutations call audit.emit(...) which appends. The buffer is the
single source of truth for the audit log; the underlying entity stores carry
their own data shape for fast querying, this just records the deltas.

Lineage is captured via the optional bom_item_id / pr_no / rfq_no / award_id /
po_no fields on every event. The traceability walker uses those + the entity
stores to assemble a forward chain from any starting point.
"""

from __future__ import annotations

import csv
import logging
import io
import uuid
from collections import deque
from datetime import datetime, timezone
from threading import Lock
from typing import Deque, Dict, List, Optional

from .schemas import (
    AuditAction,
    AuditEntityKind,
    AuditEvent,
    AuditPage,
    AuditSource,
    TraceStage,
    TraceabilityChain,
)


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


log = logging.getLogger("ct.audit")

_MAX_EVENTS = 10_000
_events: Deque[AuditEvent] = deque(maxlen=_MAX_EVENTS)
_lock = Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _next_id() -> str:
    return f"AUD-{uuid.uuid4().hex[:12].upper()}"


# ---------------------------------------------------------------------------
# Emit
# ---------------------------------------------------------------------------


def emit(
    *,
    action: AuditAction,
    entity_kind: AuditEntityKind,
    entity_id: str,
    subject: str,
    summary: str,
    actor: str = "system",
    source: AuditSource = "system",
    tenant_id: str = "",
    bom_item_id: Optional[str] = None,
    bom_code: Optional[str] = None,
    project_id: Optional[str] = None,
    pr_no: Optional[str] = None,
    rfq_no: Optional[str] = None,
    quote_id: Optional[str] = None,
    award_id: Optional[str] = None,
    po_no: Optional[str] = None,
    vendor: Optional[str] = None,
    sap_doc_no: Optional[str] = None,
    before: Optional[dict] = None,
    after: Optional[dict] = None,
    metadata: Optional[dict] = None,
) -> AuditEvent:
    """Record one audit event. Lightweight — no I/O, no validation beyond the schema."""

    event = AuditEvent(
        event_id=_next_id(),
        occurred_at=_now(),
        actor=actor,
        action=action,
        entity_kind=entity_kind,
        entity_id=entity_id,
        subject=subject,
        summary=summary,
        source=source,
        tenant_id=tenant_id,
        bom_item_id=bom_item_id,
        bom_code=bom_code,
        project_id=project_id,
        pr_no=pr_no,
        rfq_no=rfq_no,
        quote_id=quote_id,
        award_id=award_id,
        po_no=po_no,
        vendor=vendor,
        sap_doc_no=sap_doc_no,
        before=before,
        after=after,
        metadata=metadata,
    )
    with _lock:
        _events.append(event)
    try:
        from .persistence import flush_critical

        flush_critical()
    except Exception:  # noqa: BLE001
        log.exception("flush_critical failed after audit emit")
    return event


# ---------------------------------------------------------------------------
# Query / filter
# ---------------------------------------------------------------------------


def query(
    *,
    actor: Optional[str] = None,
    action: Optional[str] = None,
    entity_kind: Optional[str] = None,
    entity_id: Optional[str] = None,
    project_id: Optional[str] = None,
    bom_item_id: Optional[str] = None,
    bom_code: Optional[str] = None,
    pr_no: Optional[str] = None,
    rfq_no: Optional[str] = None,
    po_no: Optional[str] = None,
    vendor: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    search: Optional[str] = None,
    tenant_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> AuditPage:
    """Filter events. Newest-first."""

    with _lock:
        all_events = list(_events)
    # newest-first
    all_events.reverse()

    def match(e: AuditEvent) -> bool:
        if tenant_id is not None and e.tenant_id != tenant_id:
            return False
        if actor and e.actor != actor:
            return False
        if action and e.action != action:
            return False
        if entity_kind and e.entity_kind != entity_kind:
            return False
        if entity_id and e.entity_id != entity_id:
            return False
        if project_id and e.project_id != project_id:
            return False
        if bom_item_id and e.bom_item_id != bom_item_id:
            return False
        if bom_code and e.bom_code != bom_code:
            return False
        if pr_no and e.pr_no != pr_no:
            return False
        if rfq_no and e.rfq_no != rfq_no:
            return False
        if po_no and e.po_no != po_no:
            return False
        if vendor and e.vendor != vendor:
            return False
        if since and e.occurred_at < since:
            return False
        if until and e.occurred_at > until:
            return False
        if search:
            s = search.lower()
            if s not in (e.subject + " " + e.summary).lower():
                return False
        return True

    filtered = [e for e in all_events if match(e)]
    total = len(filtered)
    page = filtered[offset : offset + limit]
    return AuditPage(
        events=page,
        total=total,
        has_more=(offset + limit) < total,
        next_offset=(offset + limit) if (offset + limit) < total else None,
    )


def events_for_entity(
    kind: str,
    eid: str,
    tenant_id: Optional[str] = None,
) -> List[AuditEvent]:
    """All events that name this entity in any lineage slot."""

    with _lock:
        all_events = list(_events)
    out: List[AuditEvent] = []
    for e in all_events:
        if tenant_id is not None and e.tenant_id != tenant_id:
            continue
        if e.entity_kind == kind and e.entity_id == eid:
            out.append(e)
            continue
        if kind == "bom_item" and e.bom_item_id == eid:
            out.append(e)
        elif kind == "pr" and e.pr_no == eid:
            out.append(e)
        elif kind == "rfq" and e.rfq_no == eid:
            out.append(e)
        elif kind == "po" and e.po_no == eid:
            out.append(e)
        elif kind == "award" and e.award_id == eid:
            out.append(e)
    out.sort(key=lambda x: x.occurred_at)
    return out


# ---------------------------------------------------------------------------
# Traceability — walk forward through entity stores from any root
# ---------------------------------------------------------------------------


def trace_from_bom(
    bom_item_id: str,
    tenant_id: Optional[str] = None,
) -> Optional[TraceabilityChain]:
    """Build the BOM → ... → Delivery chain by walking entity stores."""

    from .planning import get_bom, list_projects
    from .sourcing import _prs, _rfqs, _quotes_by_rfq, _awards, _pos  # type: ignore[attr-defined]
    from .logistics import get_shipment

    # Find the BOM item within the tenant's projects
    bom_item = None
    project = None
    for p in list_projects(tenant_id=tenant_id):
        for i in get_bom(p.project_id, tenant_id=tenant_id):
            if i.bom_item_id == bom_item_id:
                bom_item = i
                project = p
                break
        if bom_item:
            break
    if not bom_item:
        return None

    stages: List[TraceStage] = []

    # Stage: BOM
    stages.append(TraceStage(
        stage="bom_item",
        label=f"BOM line · {bom_item.code}",
        entity_id=bom_item.bom_item_id,
        status=bom_item.status,
        occurred_at=None,
        detail=bom_item.description,
        payload={
            "quantity": bom_item.quantity,
            "uom": bom_item.uom,
            "supplier": bom_item.supplier_name,
            "need_by": str(bom_item.planned_need_date) if bom_item.planned_need_date else None,
            "long_lead_days": bom_item.long_lead_days,
        },
        complete=True,
    ))

    # Stage: Spec
    stages.append(TraceStage(
        stage="spec",
        label="Spec released" if bom_item.spec_doc_id else "Spec not released",
        entity_id=bom_item.spec_doc_id,
        status="released" if bom_item.spec_doc_id else "missing",
        detail=bom_item.spec_doc_id or "Engineering must release a spec before PR",
        complete=bool(bom_item.spec_doc_id),
    ))

    # Stage: PR
    matching_prs = [
        pr for pr in _prs.values()
        if pr.bom_item_id == bom_item.bom_item_id
        and (tenant_id is None or pr.tenant_id == tenant_id)
    ]
    if matching_prs:
        for pr in matching_prs:
            stages.append(TraceStage(
                stage="pr",
                label=f"PR {pr.pr_no}",
                entity_id=pr.pr_no,
                status=pr.status,
                occurred_at=pr.created_at,
                actor=pr.buyer,
                detail=f"Strategy: {pr.strategy}",
                payload={
                    "budget_value_usd": pr.budget_value_usd,
                    "sap_pr_no": pr.sap_pr_no,
                    "sap_status": pr.sap_status,
                },
                complete=pr.status not in {"draft", "cancelled"},
            ))
            # RFQs from this PR
            for rfq in _rfqs.values():
                if rfq.pr_no != pr.pr_no:
                    continue
                if tenant_id is not None and rfq.tenant_id != tenant_id:
                    continue
                stages.append(TraceStage(
                    stage="rfq",
                    label=f"RFQ {rfq.rfq_no}",
                    entity_id=rfq.rfq_no,
                    status=rfq.status,
                    occurred_at=rfq.issued_at,
                    detail=f"{len(rfq.vendors)} vendor(s) invited",
                    payload={"vendors": rfq.vendors, "due_at": str(rfq.due_at)},
                    complete=rfq.status in {"awarded", "evaluated"},
                ))
                # Quotes
                quotes = _quotes_by_rfq.get(rfq.rfq_no, [])
                if quotes:
                    stages.append(TraceStage(
                        stage="quotes",
                        label=f"Quotes received ({len(quotes)})",
                        entity_id=rfq.rfq_no,
                        status=f"{len(quotes)}/{len(rfq.vendors)} responded",
                        occurred_at=max(q.received_at for q in quotes),
                        detail=", ".join(f"{q.vendor}: ${q.total_usd:,.0f}" for q in quotes[:3]),
                        payload={"quote_count": len(quotes)},
                        complete=len(quotes) >= 2,
                    ))
                # Award + PO
                award = next(
                    (a for a in _awards.values()
                     if a.rfq_no == rfq.rfq_no
                     and (tenant_id is None or a.tenant_id == tenant_id)),
                    None,
                )
                if award:
                    stages.append(TraceStage(
                        stage="award",
                        label=f"Award {award.award_id}",
                        entity_id=award.award_id,
                        status="awarded",
                        occurred_at=award.awarded_at,
                        actor=award.awarded_by,
                        detail=f"To {award.vendor} · ${award.awarded_value_usd:,.0f}",
                        payload={"rationale": award.rationale[:200] + ("..." if len(award.rationale) > 200 else "")},
                        complete=True,
                    ))
                    # PO from this award
                    po = next(
                        (p for p in _pos.values()
                         if p.award_id == award.award_id
                         and (tenant_id is None or p.tenant_id == tenant_id)),
                        None,
                    )
                    if po:
                        stages.append(TraceStage(
                            stage="po",
                            label=f"PO {po.po_no}",
                            entity_id=po.po_no,
                            status=po.status,
                            occurred_at=po.created_at,
                            detail=f"{po.vendor} · {po.quantity} {po.uom} · ${po.value_usd:,.0f}",
                            payload={
                                "incoterm": po.incoterm,
                                "need_by": str(po.need_by) if po.need_by else None,
                                "lead_time_days": po.lead_time_days,
                            },
                            complete=po.status in {"in_transit", "delivered", "released"},
                        ))
                        # SAP
                        if po.sap_po_no or po.sap_status != "draft":
                            stages.append(TraceStage(
                                stage="sap",
                                label=f"SAP {po.sap_po_no or '(submission pending)'}",
                                entity_id=po.sap_po_no,
                                status=po.sap_status,
                                occurred_at=po.sap_last_synced_at,
                                actor="sap_cpi",
                                detail=po.sap_error or "Synced to SAP",
                                payload={
                                    "gr_qty": po.sap_gr_qty,
                                    "ir_value_usd": po.sap_ir_value_usd,
                                },
                                complete=po.sap_status == "synced",
                            ))
                        # Shipment
                        shipment = get_shipment(po.po_no, tenant_id=tenant_id)
                        if shipment:
                            stages.append(TraceStage(
                                stage="shipment",
                                label=f"Shipment ({shipment.current_stage})",
                                entity_id=shipment.po_ref,
                                status=shipment.current_stage,
                                occurred_at=shipment.events[-1].at if shipment.events else None,
                                detail=f"Mode {shipment.mode} · {len(shipment.events)} event(s)",
                                payload={
                                    "origin": shipment.origin_country,
                                    "destination": shipment.destination_site,
                                    "mode": shipment.mode,
                                    "events": [
                                        {"stage": e.stage, "at": str(e.at), "location": e.location}
                                        for e in shipment.events[-3:]
                                    ],
                                },
                                complete=shipment.current_stage in {"last_mile", "delivered"},
                            ))
                            if shipment.current_stage == "delivered":
                                stages.append(TraceStage(
                                    stage="delivery",
                                    label="Delivered to site",
                                    status="delivered",
                                    occurred_at=shipment.events[-1].at if shipment.events else None,
                                    detail=shipment.destination_site,
                                    complete=True,
                                ))
                        if po.sap_ir_value_usd:
                            stages.append(TraceStage(
                                stage="invoice",
                                label=f"Invoice posted in SAP",
                                status="ir_posted",
                                detail=f"USD {po.sap_ir_value_usd:,.0f}",
                                complete=True,
                            ))
    else:
        stages.append(TraceStage(
            stage="pr",
            label="No PR raised yet",
            status="pending",
            detail="Use 'Create PR' on the BOM line",
            complete=False,
        ))

    # Events count for this chain (BOM + descendants)
    related_events = events_for_entity("bom_item", bom_item.bom_item_id, tenant_id=tenant_id)

    return TraceabilityChain(
        root_kind="bom_item",
        root_id=bom_item.bom_item_id,
        project_id=project.project_id if project else None,
        stages=stages,
        generated_at=_now(),
        events_count=len(related_events),
    )


def trace_from_pr(
    pr_no: str,
    tenant_id: Optional[str] = None,
) -> Optional[TraceabilityChain]:
    from .sourcing import get_pr
    pr = get_pr(pr_no, tenant_id=tenant_id)
    if not pr or not pr.bom_item_id:
        return None
    return trace_from_bom(pr.bom_item_id, tenant_id=tenant_id)


def trace_from_po(
    po_no: str,
    tenant_id: Optional[str] = None,
) -> Optional[TraceabilityChain]:
    from .sourcing import get_po, get_pr
    po = get_po(po_no, tenant_id=tenant_id)
    if not po:
        return None
    pr = get_pr(po.pr_no, tenant_id=tenant_id)
    if pr and pr.bom_item_id:
        return trace_from_bom(pr.bom_item_id, tenant_id=tenant_id)
    return None


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------


def export_csv(events: List[AuditEvent]) -> str:
    """Render an event list as a CSV string (for download)."""

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "event_id", "occurred_at", "actor", "source", "action",
        "entity_kind", "entity_id", "subject", "summary", "tenant_id",
        "bom_item_id", "project_id", "pr_no", "rfq_no", "quote_id",
        "award_id", "po_no", "sap_doc_no",
    ])
    for e in events:
        w.writerow([
            e.event_id, e.occurred_at.isoformat(), e.actor, e.source, e.action,
            e.entity_kind, e.entity_id, e.subject, e.summary, e.tenant_id or "",
            e.bom_item_id or "", e.project_id or "", e.pr_no or "", e.rfq_no or "",
            e.quote_id or "", e.award_id or "", e.po_no or "", e.sap_doc_no or "",
        ])
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


def pivot_materials(tenant_id: Optional[str] = None) -> List["PivotCount"]:
    """List materials (BOM codes) with event counts + context.

    Walks the planning store for the full BOM catalogue, then enriches each
    row with the number of audit events that touched it.
    """

    from .schemas import PivotCount
    from .planning import get_bom, list_projects

    # Index events by bom_code
    with _lock:
        all_events = list(_events)
    counts: Dict[str, int] = {}
    last_at: Dict[str, datetime] = {}
    pos_per_code: Dict[str, set] = {}
    rfqs_per_code: Dict[str, set] = {}
    vendors_per_code: Dict[str, set] = {}
    for e in all_events:
        if tenant_id is not None and e.tenant_id != tenant_id:
            continue
        code = e.bom_code
        if not code:
            continue
        counts[code] = counts.get(code, 0) + 1
        if code not in last_at or e.occurred_at > last_at[code]:
            last_at[code] = e.occurred_at
        if e.po_no:
            pos_per_code.setdefault(code, set()).add(e.po_no)
        if e.rfq_no:
            rfqs_per_code.setdefault(code, set()).add(e.rfq_no)
        if e.vendor:
            vendors_per_code.setdefault(code, set()).add(e.vendor)

    out: List[PivotCount] = []
    seen_codes: set = set()
    for project in list_projects(tenant_id=tenant_id):
        for item in get_bom(project.project_id, tenant_id=tenant_id):
            if item.code in seen_codes:
                continue
            seen_codes.add(item.code)
            out.append(PivotCount(
                key=item.code,
                label=item.code,
                event_count=counts.get(item.code, 0),
                last_at=last_at.get(item.code),
                description=item.description,
                project_id=project.project_id,
                category=item.category,
                status=item.status,
                value_usd=(item.unit_cost_usd or 0) * item.quantity if item.unit_cost_usd else None,
                related_pos=len(pos_per_code.get(item.code, set())),
                related_rfqs=len(rfqs_per_code.get(item.code, set())),
                related_vendors=len(vendors_per_code.get(item.code, set())),
            ))
    out.sort(key=lambda p: (-(p.event_count or 0), p.label))
    return out


def pivot_pos(tenant_id: Optional[str] = None) -> List["PivotCount"]:
    """All POs (sourcing + legacy) with event counts."""

    from .schemas import PivotCount
    from .sourcing import _pos as _sourcing_pos  # type: ignore[attr-defined]
    from .sample_data import build_demo_request

    with _lock:
        all_events = list(_events)
    counts: Dict[str, int] = {}
    last_at: Dict[str, datetime] = {}
    for e in all_events:
        if tenant_id is not None and e.tenant_id != tenant_id:
            continue
        if not e.po_no:
            continue
        counts[e.po_no] = counts.get(e.po_no, 0) + 1
        if e.po_no not in last_at or e.occurred_at > last_at[e.po_no]:
            last_at[e.po_no] = e.occurred_at

    out: List[PivotCount] = []
    seen: set = set()
    # Sourcing POs first
    for po in _sourcing_pos.values():
        if tenant_id is not None and po.tenant_id != tenant_id:
            continue
        seen.add(po.po_no)
        out.append(PivotCount(
            key=po.po_no,
            label=po.po_no,
            event_count=counts.get(po.po_no, 0),
            last_at=last_at.get(po.po_no),
            description=f"{po.vendor} · {po.code}",
            project_id=po.project_id,
            status=po.status,
            value_usd=po.value_usd,
        ))
    # Legacy scenario POs that haven't been touched yet (unscoped admin view only)
    if tenant_id is None:
        for po in build_demo_request().purchase_orders:
            if po.po_number in seen:
                continue
            out.append(PivotCount(
                key=po.po_number,
                label=po.po_number,
                event_count=counts.get(po.po_number, 0),
                last_at=last_at.get(po.po_number),
                description=f"{po.supplier_name} · {po.sku}",
                status=po.status,
                value_usd=po.value_usd,
            ))
    out.sort(key=lambda p: (-(p.event_count or 0), p.label))
    return out


def pivot_vendors(tenant_id: Optional[str] = None) -> List["PivotCount"]:
    """All vendors with event counts + spend + relationship counts."""

    from .schemas import PivotCount
    from .sample_data import build_demo_request
    from .sourcing import _pos as _sourcing_pos, _quotes_by_rfq, _rfqs  # type: ignore[attr-defined]
    from .vendor_store import list_runtime

    with _lock:
        all_events = list(_events)
    counts: Dict[str, int] = {}
    last_at: Dict[str, datetime] = {}
    for e in all_events:
        if tenant_id is not None and e.tenant_id != tenant_id:
            continue
        if not e.vendor:
            continue
        counts[e.vendor] = counts.get(e.vendor, 0) + 1
        if e.vendor not in last_at or e.occurred_at > last_at[e.vendor]:
            last_at[e.vendor] = e.occurred_at

    # Vendor base set: from the supplier directory + anywhere they appear in quotes/awards/POs
    suppliers = {s.name: s for s in build_demo_request().suppliers} if tenant_id is None else {}
    seen: set = set(suppliers.keys())
    if tenant_id is not None:
        for s in list_runtime(tenant_id):
            seen.add(s.name)
    for rfq_no, quotes in _quotes_by_rfq.items():
        if tenant_id is not None:
            rfq = _rfqs.get(rfq_no)
            if rfq is None or rfq.tenant_id != tenant_id:
                continue
        for q in quotes:
            seen.add(q.vendor)
    for po in _sourcing_pos.values():
        if tenant_id is not None and po.tenant_id != tenant_id:
            continue
        seen.add(po.vendor)

    # PO + RFQ counts per vendor
    pos_by_vendor: Dict[str, int] = {}
    rfqs_by_vendor: Dict[str, set] = {}
    spend_by_vendor: Dict[str, float] = {}
    for po in _sourcing_pos.values():
        if tenant_id is not None and po.tenant_id != tenant_id:
            continue
        pos_by_vendor[po.vendor] = pos_by_vendor.get(po.vendor, 0) + 1
        spend_by_vendor[po.vendor] = spend_by_vendor.get(po.vendor, 0) + po.value_usd
    for rfq_no, quotes in _quotes_by_rfq.items():
        if tenant_id is not None:
            rfq = _rfqs.get(rfq_no)
            if rfq is None or rfq.tenant_id != tenant_id:
                continue
        for q in quotes:
            rfqs_by_vendor.setdefault(q.vendor, set()).add(rfq_no)

    out: List[PivotCount] = []
    for name in seen:
        s = suppliers.get(name)
        out.append(PivotCount(
            key=name,
            label=name,
            event_count=counts.get(name, 0),
            last_at=last_at.get(name),
            description=s.category if s else None,
            category=s.category if s else None,
            value_usd=spend_by_vendor.get(name) or (s.annual_spend_usd if s else None),
            related_pos=pos_by_vendor.get(name, 0),
            related_rfqs=len(rfqs_by_vendor.get(name, set())),
        ))
    out.sort(key=lambda p: (-(p.event_count or 0), -(p.value_usd or 0), p.label))
    return out


def stats(tenant_id: Optional[str] = None) -> dict:
    with _lock:
        all_events = list(_events)
    if tenant_id is not None:
        all_events = [e for e in all_events if e.tenant_id == tenant_id]
    by_action: Dict[str, int] = {}
    by_kind: Dict[str, int] = {}
    by_actor: Dict[str, int] = {}
    by_source: Dict[str, int] = {}
    for e in all_events:
        by_action[e.action] = by_action.get(e.action, 0) + 1
        by_kind[e.entity_kind] = by_kind.get(e.entity_kind, 0) + 1
        by_actor[e.actor] = by_actor.get(e.actor, 0) + 1
        by_source[e.source] = by_source.get(e.source, 0) + 1
    return {
        "total": len(all_events),
        "buffer_capacity": _MAX_EVENTS,
        "by_action": by_action,
        "by_entity_kind": by_kind,
        "by_actor": by_actor,
        "by_source": by_source,
        "newest_at": all_events[-1].occurred_at if all_events else None,
        "oldest_at": all_events[0].occurred_at if all_events else None,
    }
