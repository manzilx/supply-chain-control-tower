"""Derived per-project SCM process map.

Walks BOM + sourcing + logistics stores and buckets each BOM line into the
furthest incomplete stage. No Process entity — status is always live.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Tuple

from .planning import get_bom, get_project
from .schemas import (
    BOMItem,
    ProcessBottleneck,
    ProcessLineRef,
    ProcessStageBucket,
    ProcessStageName,
    ProjectProcessMap,
    PurchaseRequisition,
    RFQ,
    Shipment,
    SourcingPO,
)
from .sourcing import get_quotes, list_pos, list_prs, list_rfqs


STAGE_ORDER: List[ProcessStageName] = [
    "spec",
    "pr",
    "rfq",
    "quotes",
    "technical_eval",
    "award",
    "po",
    "shipment",
    "site_grn",
    "delivery",
]

STAGE_LABEL: Dict[ProcessStageName, str] = {
    "spec": "Spec",
    "pr": "PR",
    "rfq": "RFQ",
    "quotes": "Quotes",
    "technical_eval": "TBE",
    "award": "Award",
    "po": "PO",
    "shipment": "Shipment",
    "site_grn": "Site GRN",
    "delivery": "Delivery",
}

_MOVING_SHIPMENT = {"dispatched", "in_transit", "at_port", "at_customs", "last_mile"}
_INDEX = {s: i for i, s in enumerate(STAGE_ORDER)}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _href(stage: ProcessStageName, project_id: str, pr: Optional[PurchaseRequisition],
          rfq: Optional[RFQ], po: Optional[SourcingPO]) -> Tuple[str, Optional[str]]:
    if stage in {"rfq", "quotes", "technical_eval"} and rfq:
        return f"/sourcing/rfqs/{rfq.rfq_no}", rfq.rfq_no
    if stage in {"pr", "award"} and pr:
        return f"/sourcing/prs/{pr.pr_no}", pr.pr_no
    if stage in {"po", "shipment", "site_grn"} and po:
        if stage == "shipment":
            return "/logistics", po.po_no
        return "/pos", po.po_no
    return f"/projects/{project_id}/bom", None


def _classify(
    item: BOMItem,
    pr: Optional[PurchaseRequisition],
    rfq: Optional[RFQ],
    po: Optional[SourcingPO],
    shipment: Optional[Shipment],
    tbe_done: bool,
    quotes_n: int,
    expedite_urgency: Optional[str],
) -> Tuple[ProcessStageName, bool, bool, Optional[str]]:
    """Return (stage, blocked, at_risk, status_label)."""

    if item.status == "spec_missing":
        return "spec", True, False, "spec_missing"

    if item.status == "delivered" or (po and po.status == "delivered"):
        return "delivery", False, False, "delivered"

    if po and (po.ct_gr_qty or 0) > 0 and po.status != "delivered":
        return "site_grn", False, False, "grn"

    ship_stage = shipment.current_stage if shipment else None
    if po and (po.status == "in_transit" or ship_stage in _MOVING_SHIPMENT):
        blocked = bool(shipment and shipment.bottleneck) or expedite_urgency == "escalate"
        at_risk = (not blocked) and (
            expedite_urgency in {"nudge", "watch"}
            or (shipment is not None and shipment.slack_days is not None and shipment.slack_days < 0)
            or bool(shipment and shipment.bottleneck)
        )
        return "shipment", blocked, at_risk, ship_stage or po.status

    if po:
        return "po", False, expedite_urgency in {"nudge", "escalate", "watch"}, po.status

    if pr and pr.status == "awarded" and not po:
        return "award", False, False, "awarded"

    if rfq:
        overdue = rfq.status == "open" and rfq.due_at.date() < date.today()
        if rfq.status == "evaluated" or (tbe_done and rfq.status != "awarded"):
            return "technical_eval", overdue, overdue, rfq.status
        if rfq.status == "quotes_received" or quotes_n > 0:
            return "quotes", overdue, overdue, rfq.status
        if rfq.status == "open":
            return "rfq", overdue, overdue, "open"
        if rfq.status == "awarded" and not po:
            return "award", False, False, "awarded"

    if pr:
        if pr.status == "quoted":
            return "quotes", False, False, "quoted"
        if pr.status == "rfq_issued":
            return "rfq", False, False, "rfq_issued"
        if pr.status == "po_created" and not po:
            return "po", False, False, "po_created"
        return "pr", False, False, pr.status

    if item.status == "ordered":
        return "po", False, False, "ordered"
    if item.status == "requisitioned":
        return "pr", False, False, "requisitioned"

    need_soon = (
        item.planned_need_date is not None
        and 0 <= (item.planned_need_date - date.today()).days <= 30
    )
    return "pr", False, need_soon, item.status


def build_process_map(project_id: str, tenant_id: str) -> Optional[ProjectProcessMap]:
    project = get_project(project_id, tenant_id=tenant_id)
    if project is None:
        return None

    bom = get_bom(project_id, tenant_id=tenant_id)
    prs = [p for p in list_prs(tenant_id=tenant_id) if p.project_id == project_id]
    rfqs = [r for r in list_rfqs(tenant_id=tenant_id) if r.project_id == project_id]
    pos = [p for p in list_pos(tenant_id=tenant_id) if p.project_id == project_id]

    pr_by_bom: Dict[str, PurchaseRequisition] = {}
    for pr in sorted(prs, key=lambda p: p.created_at):
        if pr.bom_item_id:
            pr_by_bom[pr.bom_item_id] = pr

    rfq_by_pr = {r.pr_no: r for r in rfqs}
    po_by_pr = {p.pr_no: p for p in pos}

    from .logistics import list_shipments
    ship_by_po = {
        s.po_ref: s
        for s in list_shipments(tenant_id=tenant_id).shipments
        if s.source == "sourcing"
    }

    from .expediting import build_expedite_queue
    urgency_by_po = {
        i.po_number: i.urgency
        for i in build_expedite_queue(tenant_id=tenant_id).items
        if i.project_id == project_id and i.source == "sourcing"
    }

    from .tbe import list_evaluations

    buckets: Dict[ProcessStageName, List[ProcessLineRef]] = {s: [] for s in STAGE_ORDER}
    current_idx: Dict[str, int] = {}

    for item in bom:
        pr = pr_by_bom.get(item.bom_item_id)
        rfq = rfq_by_pr.get(pr.pr_no) if pr else None
        po = po_by_pr.get(pr.pr_no) if pr else None
        shipment = ship_by_po.get(po.po_no) if po else None
        tbe_done = bool(rfq and list_evaluations(rfq.rfq_no))
        quotes_n = len(get_quotes(rfq.rfq_no, tenant_id=tenant_id)) if rfq else 0
        stage, blocked, at_risk, status = _classify(
            item, pr, rfq, po, shipment, tbe_done, quotes_n,
            urgency_by_po.get(po.po_no) if po else None,
        )
        href, entity_id = _href(stage, project_id, pr, rfq, po)
        ref = ProcessLineRef(
            bom_item_id=item.bom_item_id,
            code=item.code,
            description=item.description,
            status=status,
            href=href,
            blocked=blocked,
            at_risk=at_risk,
            entity_id=entity_id,
        )
        buckets[stage].append(ref)
        current_idx[item.bom_item_id] = _INDEX[stage]

    n = len(bom)
    stages: List[ProcessStageBucket] = []
    bottlenecks: List[ProcessBottleneck] = []
    blocked_total = 0
    at_risk_total = 0

    for stage in STAGE_ORDER:
        items = buckets[stage]
        idx = _INDEX[stage]
        done = sum(1 for i in current_idx.values() if i > idx)
        blocked = sum(1 for x in items if x.blocked)
        at_risk = sum(1 for x in items if x.at_risk)
        blocked_total += blocked
        at_risk_total += at_risk
        stages.append(
            ProcessStageBucket(
                stage=stage,
                label=STAGE_LABEL[stage],
                current=len(items),
                done=done,
                blocked=blocked,
                at_risk=at_risk,
                items=items,
            )
        )
        if blocked:
            bottlenecks.append(ProcessBottleneck(
                stage=stage, count=blocked,
                reason=f"{blocked} line(s) blocked at {STAGE_LABEL[stage]}",
            ))
        elif at_risk >= 2:
            bottlenecks.append(ProcessBottleneck(
                stage=stage, count=at_risk,
                reason=f"{at_risk} line(s) at risk at {STAGE_LABEL[stage]}",
            ))

    from .risk_register import list_project_risks, seed_project

    seed_project(project_id, tenant_id)
    risks = list_project_risks(project_id, tenant_id)
    open_risks = sum(1 for r in risks if r.status in {"open", "mitigating"})

    return ProjectProcessMap(
        project_id=project_id,
        project_name=project.name,
        generated_at=_now(),
        bom_total=n,
        blocked_total=blocked_total,
        at_risk_total=at_risk_total,
        open_risks=open_risks,
        stages=stages,
        bottlenecks=bottlenecks,
        risks=risks,
    )
