"""Sourcing module: PR → RFQ → Quote → Award → PO lifecycle.

Keeps an in-memory store for MVP. Every mutating function returns the updated
record so the caller can push it to the UI directly.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

from .planning import get_bom, get_project, list_projects
from .sample_data import build_demo_request
from .schemas import (
    Award,
    AwardRFQRequest,
    BOMItem,
    CreatePRRequest,
    CreateQuoteRequest,
    CreateRFQRequest,
    PurchaseRequisition,
    Quote,
    QuoteComparison,
    QuoteEvaluation,
    RFQ,
    SourcingPO,
    SourcingStrategy,
    SourcingTimeline,
    SourcingTimelineEvent,
    SupplierRecord,
)


# --- Store -------------------------------------------------------------------


_prs: Dict[str, PurchaseRequisition] = {}
_rfqs: Dict[str, RFQ] = {}
_quotes_by_rfq: Dict[str, List[Quote]] = {}
_awards: Dict[str, Award] = {}
_pos: Dict[str, SourcingPO] = {}
_counter = {"pr": 0, "rfq": 0, "quote": 0, "award": 0, "po": 0}


def _next(kind: str, prefix: str, width: int = 4) -> str:
    _counter[kind] += 1
    return f"{prefix}-{_counter[kind]:0{width}d}"


def _suppliers_lookup() -> Dict[str, SupplierRecord]:
    return {s.name: s for s in build_demo_request().suppliers}


def _bom_item(project_id: str, bom_item_id: Optional[str]) -> Optional[BOMItem]:
    if not bom_item_id:
        return None
    for item in get_bom(project_id):
        if item.bom_item_id == bom_item_id:
            return item
    return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- Seed a couple of demo PRs so the screens aren't empty on first boot -----


_seeded = False


def _seed() -> None:
    global _seeded
    if _seeded:
        return
    _seeded = True

    projects = list_projects()
    if not projects:
        return

    rb = next((p for p in projects if p.project_id == "PRJ-RB-660"), None)
    if rb:
        valve = next((i for i in get_bom(rb.project_id) if i.code == "VALVE-16-A105"), None)
        if valve:
            pr = _create_pr_record(
                project_id=rb.project_id,
                item=valve,
                buyer="K. Menon",
                strategy="multi_source",
            )
            # Issue an RFQ with quotes already received so the compare screen has content
            rfq = _issue_rfq_record(
                pr=pr,
                vendors=["Helios Cast & Forge", "BluePeak Controls", "Copperline Metals"],
                due_in_days=7,
                notes="Tight need-date; confirm heat treatment + NDE per spec SPEC-RB-002.",
            )
            _add_quote_record(
                rfq, CreateQuoteRequest(
                    vendor="Helios Cast & Forge",
                    unit_price_usd=3780.0,
                    lead_time_days=44,
                    incoterm="CIP",
                    validity_days=30,
                    notes="Existing supplier, honoring last year's rate minus 2%.",
                )
            )
            _add_quote_record(
                rfq, CreateQuoteRequest(
                    vendor="BluePeak Controls",
                    unit_price_usd=3950.0,
                    lead_time_days=38,
                    incoterm="CIP",
                    validity_days=21,
                    notes="New category for them; offering faster lead.",
                )
            )
            _add_quote_record(
                rfq, CreateQuoteRequest(
                    vendor="Copperline Metals",
                    unit_price_usd=4120.0,
                    lead_time_days=50,
                    incoterm="FOB",
                    validity_days=30,
                    notes="Includes packing for sea freight only.",
                )
            )


def _create_pr_record(
    *,
    project_id: str,
    item: Optional[BOMItem],
    code: Optional[str] = None,
    description: Optional[str] = None,
    quantity: Optional[float] = None,
    uom: Optional[str] = None,
    need_by: Optional[date] = None,
    milestone_code: Optional[str] = None,
    budget_value_usd: Optional[float] = None,
    buyer: Optional[str] = None,
    strategy: Optional[SourcingStrategy] = None,
) -> PurchaseRequisition:
    pr_no = _next("pr", "PR", width=5)
    resolved_code = code or (item.code if item else None) or "UNKNOWN"
    resolved_desc = description or (item.description if item else None) or "Unspecified"
    resolved_qty = quantity if quantity is not None else (item.quantity if item else 1.0)
    resolved_uom = uom or (item.uom if item else "EA")
    resolved_need_by = need_by or (item.planned_need_date if item else None)
    resolved_milestone = milestone_code or (item.milestone_code if item else None)
    resolved_budget = budget_value_usd
    if resolved_budget is None and item and item.unit_cost_usd is not None:
        resolved_budget = round(item.unit_cost_usd * resolved_qty, 2)

    pr = PurchaseRequisition(
        pr_no=pr_no,
        project_id=project_id,
        bom_item_id=item.bom_item_id if item else None,
        code=resolved_code,
        description=resolved_desc,
        quantity=resolved_qty,
        uom=resolved_uom,
        need_by=resolved_need_by,
        milestone_code=resolved_milestone,
        budget_value_usd=resolved_budget,
        buyer=buyer or "Unassigned",
        strategy=strategy or "multi_source",
        status="draft",
        created_at=_now(),
    )
    _prs[pr_no] = pr
    return pr


# --- Public API: PRs ---------------------------------------------------------


def list_prs() -> List[PurchaseRequisition]:
    _seed()
    return sorted(_prs.values(), key=lambda p: p.created_at, reverse=True)


def get_pr(pr_no: str) -> Optional[PurchaseRequisition]:
    _seed()
    return _prs.get(pr_no)


def create_pr(request: CreatePRRequest) -> PurchaseRequisition:
    _seed()
    item = _bom_item(request.project_id, request.bom_item_id)
    return _create_pr_record(
        project_id=request.project_id,
        item=item,
        code=request.code,
        description=request.description,
        quantity=request.quantity,
        uom=request.uom,
        need_by=request.need_by,
        milestone_code=request.milestone_code,
        budget_value_usd=request.budget_value_usd,
        buyer=request.buyer,
        strategy=request.strategy,
    )


def suggest_vendors(project_id: str, bom_item_id: Optional[str]) -> List[str]:
    """Suggest vendors for an RFQ based on the BOM item + known suppliers."""
    _seed()
    suggestions: List[str] = []
    item = _bom_item(project_id, bom_item_id)
    suppliers = _suppliers_lookup()

    def add(name: Optional[str]) -> None:
        if name and name in suppliers and name not in suggestions:
            suggestions.append(name)

    if item and item.supplier_name:
        add(item.supplier_name)
    if item and item.category:
        for name, supplier in suppliers.items():
            if supplier.category.lower() == item.category.lower():
                add(name)
    # Top up with the broader vendor list so the user has options.
    for name in suppliers:
        add(name)
    return suggestions[:8]


# --- Public API: RFQs --------------------------------------------------------


def list_rfqs() -> List[RFQ]:
    _seed()
    return sorted(_rfqs.values(), key=lambda r: r.issued_at, reverse=True)


def get_rfq(rfq_no: str) -> Optional[RFQ]:
    _seed()
    return _rfqs.get(rfq_no)


def get_quotes(rfq_no: str) -> List[Quote]:
    _seed()
    return list(_quotes_by_rfq.get(rfq_no, []))


def _issue_rfq_record(
    *,
    pr: PurchaseRequisition,
    vendors: List[str],
    due_in_days: int,
    notes: Optional[str],
) -> RFQ:
    rfq_no = _next("rfq", "RFQ", width=5)
    issued = _now()
    rfq = RFQ(
        rfq_no=rfq_no,
        pr_no=pr.pr_no,
        project_id=pr.project_id,
        code=pr.code,
        description=pr.description,
        quantity=pr.quantity,
        uom=pr.uom,
        vendors=list(dict.fromkeys(v.strip() for v in vendors if v.strip())),
        issued_at=issued,
        due_at=issued + timedelta(days=max(1, int(due_in_days))),
        status="open",
        notes=notes,
    )
    _rfqs[rfq_no] = rfq
    _quotes_by_rfq.setdefault(rfq_no, [])
    pr.status = "rfq_issued"
    pr.rfq_no = rfq_no
    _prs[pr.pr_no] = pr
    return rfq


def issue_rfq(request: CreateRFQRequest) -> Optional[RFQ]:
    _seed()
    pr = _prs.get(request.pr_no)
    if not pr:
        return None
    if pr.status not in {"draft", "rfq_issued"}:
        # Still allow re-issuing if in draft/rfq_issued state
        return None
    return _issue_rfq_record(
        pr=pr,
        vendors=request.vendors,
        due_in_days=request.due_in_days,
        notes=request.notes,
    )


def _add_quote_record(rfq: RFQ, request: CreateQuoteRequest) -> Quote:
    quote = Quote(
        quote_id=_next("quote", "Q", width=5),
        rfq_no=rfq.rfq_no,
        vendor=request.vendor.strip(),
        unit_price_usd=float(request.unit_price_usd),
        quantity=float(request.quantity or rfq.quantity),
        total_usd=round(float(request.unit_price_usd) * float(request.quantity or rfq.quantity), 2),
        lead_time_days=int(request.lead_time_days),
        incoterm=request.incoterm,
        validity_days=int(request.validity_days),
        received_at=_now(),
        notes=request.notes,
    )
    _quotes_by_rfq.setdefault(rfq.rfq_no, []).append(quote)
    if rfq.status == "open":
        rfq.status = "quotes_received"
        _rfqs[rfq.rfq_no] = rfq
    pr = _prs.get(rfq.pr_no)
    if pr and pr.status == "rfq_issued":
        pr.status = "quoted"
        _prs[pr.pr_no] = pr
    return quote


def add_quote(rfq_no: str, request: CreateQuoteRequest) -> Optional[Quote]:
    _seed()
    rfq = _rfqs.get(rfq_no)
    if not rfq:
        return None
    return _add_quote_record(rfq, request)


# --- Quote comparison + award -----------------------------------------------


def compare_quotes(rfq_no: str) -> Optional[QuoteComparison]:
    _seed()
    rfq = _rfqs.get(rfq_no)
    if not rfq:
        return None
    quotes = list(_quotes_by_rfq.get(rfq_no, []))
    if not quotes:
        return QuoteComparison(rfq_no=rfq_no, generated_at=_now(), evaluations=[], notes=["No quotes received yet."])

    suppliers = _suppliers_lookup()
    lowest_total = min(q.total_usd for q in quotes)
    shortest_lead = min(q.lead_time_days for q in quotes)

    evaluations: List[QuoteEvaluation] = []
    for q in quotes:
        price_index = lowest_total / q.total_usd if q.total_usd else 0
        lead_time_index = shortest_lead / q.lead_time_days if q.lead_time_days else 0
        supplier = suppliers.get(q.vendor)
        otd = supplier.on_time_delivery_pct if supplier else None
        ppm = supplier.quality_ppm if supplier else None
        reliability = 55.0
        if supplier is not None:
            reliability = min(
                100.0,
                max(
                    0.0,
                    0.6 * supplier.on_time_delivery_pct
                    + (20 if supplier.approved_alternatives >= 1 else 0)
                    + max(0, 25 - supplier.quality_ppm / 80),
                ),
            )
        composite = round(
            0.45 * (price_index * 100)
            + 0.30 * (lead_time_index * 100)
            + 0.25 * reliability,
            1,
        )
        evaluations.append(
            QuoteEvaluation(
                vendor=q.vendor,
                quote_id=q.quote_id,
                total_usd=q.total_usd,
                lead_time_days=q.lead_time_days,
                price_index=round(price_index, 3),
                lead_time_index=round(lead_time_index, 3),
                otd_pct=otd,
                quality_ppm=ppm,
                reliability_score=round(reliability, 1),
                composite_score=composite,
                rank=0,
            )
        )

    evaluations.sort(key=lambda e: e.composite_score, reverse=True)
    for idx, ev in enumerate(evaluations, start=1):
        ev.rank = idx

    winner = evaluations[0]
    notes: List[str] = []
    if any(ev.otd_pct is None for ev in evaluations):
        notes.append("Some vendors are not in the approved supplier list; reliability scores used a neutral baseline.")

    savings = lowest_total * 0  # placeholder if we want to compare vs budget later
    rationale = (
        f"{winner.vendor} ranks #{winner.rank} with a composite score of {winner.composite_score}. "
        f"Total ${winner.total_usd:,.0f} is "
        f"{'the lowest' if winner.price_index == 1.0 else f'{(1 - winner.price_index) * 100:.0f}% above the lowest'}; "
        f"lead time {winner.lead_time_days} days is "
        f"{'the shortest' if winner.lead_time_index == 1.0 else f'{(1 - winner.lead_time_index) * 100:.0f}% longer than the shortest'}. "
        f"Reliability baseline {winner.reliability_score}/100"
        f"{' (OTD ' + str(int(winner.otd_pct)) + '%)' if winner.otd_pct is not None else ''}."
    )

    return QuoteComparison(
        rfq_no=rfq_no,
        generated_at=_now(),
        evaluations=evaluations,
        recommended_vendor=winner.vendor,
        recommendation_rationale=rationale,
        notes=notes,
    )


def award_rfq(rfq_no: str, request: AwardRFQRequest) -> Optional[Award]:
    _seed()
    rfq = _rfqs.get(rfq_no)
    if not rfq:
        return None
    quotes = _quotes_by_rfq.get(rfq_no, [])
    quote = next((q for q in quotes if q.quote_id == request.quote_id), None)
    if not quote:
        return None

    award_id = _next("award", "AWD", width=4)
    rationale = request.rationale
    if not rationale:
        comparison = compare_quotes(rfq_no)
        rationale = (
            comparison.recommendation_rationale
            if comparison and comparison.recommendation_rationale
            else f"Awarded to {quote.vendor}."
        )

    award = Award(
        award_id=award_id,
        rfq_no=rfq_no,
        pr_no=rfq.pr_no,
        vendor=quote.vendor,
        quote_id=quote.quote_id,
        awarded_value_usd=quote.total_usd,
        rationale=rationale,
        awarded_at=_now(),
        awarded_by=request.awarded_by or "Control Tower",
    )
    _awards[award_id] = award
    rfq.status = "awarded"
    _rfqs[rfq_no] = rfq
    pr = _prs.get(rfq.pr_no)
    if pr:
        pr.status = "awarded"
        pr.award_id = award_id
        _prs[rfq.pr_no] = pr

    po = _create_po_from_award(award=award, rfq=rfq, quote=quote, pr=pr)
    if pr:
        pr.status = "po_created"
        pr.po_no = po.po_no
        _prs[rfq.pr_no] = pr
    return award


def _create_po_from_award(
    *,
    award: Award,
    rfq: RFQ,
    quote: Quote,
    pr: Optional[PurchaseRequisition],
) -> SourcingPO:
    po_no = _next("po", "SPO", width=5)
    po = SourcingPO(
        po_no=po_no,
        pr_no=award.pr_no,
        rfq_no=rfq.rfq_no,
        award_id=award.award_id,
        project_id=rfq.project_id,
        vendor=quote.vendor,
        code=rfq.code,
        description=rfq.description,
        quantity=quote.quantity,
        uom=rfq.uom,
        unit_price_usd=quote.unit_price_usd,
        value_usd=quote.total_usd,
        incoterm=quote.incoterm,
        need_by=pr.need_by if pr else None,
        lead_time_days=quote.lead_time_days,
        created_at=_now(),
        status="draft",
    )
    _pos[po_no] = po
    return po


# --- Public API: Awards + POs ------------------------------------------------


def list_awards() -> List[Award]:
    _seed()
    return sorted(_awards.values(), key=lambda a: a.awarded_at, reverse=True)


def list_pos() -> List[SourcingPO]:
    _seed()
    return sorted(_pos.values(), key=lambda p: p.created_at, reverse=True)


def get_po(po_no: str) -> Optional[SourcingPO]:
    _seed()
    return _pos.get(po_no)


def build_timeline(po_no: str) -> Optional[SourcingTimeline]:
    _seed()
    po = _pos.get(po_no)
    if not po:
        return None
    pr = _prs.get(po.pr_no)
    rfq = _rfqs.get(po.rfq_no)
    award = _awards.get(po.award_id)
    quotes = _quotes_by_rfq.get(po.rfq_no, [])

    events: List[SourcingTimelineEvent] = []
    if pr:
        events.append(
            SourcingTimelineEvent(
                kind="pr_created",
                at=pr.created_at,
                ref_id=pr.pr_no,
                title=f"PR {pr.pr_no} created",
                detail=f"{pr.code} · qty {pr.quantity} {pr.uom} · buyer {pr.buyer}",
            )
        )
    if rfq:
        events.append(
            SourcingTimelineEvent(
                kind="rfq_issued",
                at=rfq.issued_at,
                ref_id=rfq.rfq_no,
                title=f"RFQ {rfq.rfq_no} issued to {len(rfq.vendors)} vendors",
                detail=", ".join(rfq.vendors) or "—",
            )
        )
    for q in sorted(quotes, key=lambda q: q.received_at):
        events.append(
            SourcingTimelineEvent(
                kind="quote_received",
                at=q.received_at,
                ref_id=q.quote_id,
                title=f"Quote from {q.vendor}",
                detail=f"${q.total_usd:,.0f} · {q.lead_time_days}d · {q.incoterm}",
            )
        )
    if award:
        events.append(
            SourcingTimelineEvent(
                kind="awarded",
                at=award.awarded_at,
                ref_id=award.award_id,
                title=f"Awarded to {award.vendor}",
                detail=award.rationale,
            )
        )
    events.append(
        SourcingTimelineEvent(
            kind="po_created",
            at=po.created_at,
            ref_id=po.po_no,
            title=f"PO {po.po_no} drafted",
            detail=f"${po.value_usd:,.0f} · {po.incoterm} · need by {po.need_by.isoformat() if po.need_by else 'TBD'}",
        )
    )

    events.sort(key=lambda e: e.at)
    return SourcingTimeline(po_no=po_no, events=events)
