"""Sourcing module: PR → RFQ → Quote → Award → PO lifecycle.

Keeps an in-memory store for MVP. Every mutating function returns the updated
record so the caller can push it to the UI directly.
"""

from __future__ import annotations

from ._cache import invalidates_cache

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
                tenant_id=rb.tenant_id,
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
    tenant_id: str,
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
        tenant_id=tenant_id,
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


def list_prs(tenant_id: Optional[str] = None) -> List[PurchaseRequisition]:
    _seed()
    prs = sorted(_prs.values(), key=lambda p: p.created_at, reverse=True)
    if tenant_id is None:
        return prs
    return [p for p in prs if p.tenant_id == tenant_id]


def get_pr(pr_no: str, tenant_id: Optional[str] = None) -> Optional[PurchaseRequisition]:
    _seed()
    pr = _prs.get(pr_no)
    if pr is None:
        return None
    if tenant_id is not None and pr.tenant_id != tenant_id:
        return None
    return pr


@invalidates_cache
def create_pr(
    request: CreatePRRequest,
    tenant_id: Optional[str] = None,
) -> Optional[PurchaseRequisition]:
    _seed()
    # Resolve tenant from the project — every PR inherits its project's
    # tenant (cannot create a PR on a project you don't own).
    from .planning import get_project
    project = get_project(request.project_id, tenant_id=tenant_id)
    if project is None:
        return None
    item = _bom_item(request.project_id, request.bom_item_id)
    pr = _create_pr_record(
        project_id=request.project_id,
        tenant_id=project.tenant_id,
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
    from .audit import emit
    emit(
        action="created",
        entity_kind="pr",
        entity_id=pr.pr_no,
        subject=pr.pr_no,
        summary=f"PR {pr.pr_no} created for {pr.code} · {pr.quantity} {pr.uom} · buyer {pr.buyer}",
        source="api",
        tenant_id=pr.tenant_id,
        project_id=pr.project_id,
        bom_item_id=pr.bom_item_id,
        bom_code=pr.code,
        pr_no=pr.pr_no,
        metadata={"strategy": pr.strategy, "budget_value_usd": pr.budget_value_usd},
    )
    return pr


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


def list_rfqs(tenant_id: Optional[str] = None) -> List[RFQ]:
    _seed()
    rfqs = sorted(_rfqs.values(), key=lambda r: r.issued_at, reverse=True)
    if tenant_id is None:
        return rfqs
    return [r for r in rfqs if r.tenant_id == tenant_id]


def get_rfq(rfq_no: str, tenant_id: Optional[str] = None) -> Optional[RFQ]:
    _seed()
    rfq = _rfqs.get(rfq_no)
    if rfq is None:
        return None
    if tenant_id is not None and rfq.tenant_id != tenant_id:
        return None
    return rfq


def get_quotes(rfq_no: str, tenant_id: Optional[str] = None) -> List[Quote]:
    _seed()
    if tenant_id is not None:
        rfq = _rfqs.get(rfq_no)
        if rfq is None or rfq.tenant_id != tenant_id:
            return []
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
        tenant_id=pr.tenant_id,
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


@invalidates_cache
def issue_rfq(
    request: CreateRFQRequest,
    tenant_id: Optional[str] = None,
) -> Optional[RFQ]:
    _seed()
    pr = _prs.get(request.pr_no)
    if not pr:
        return None
    if tenant_id is not None and pr.tenant_id != tenant_id:
        return None  # cross-tenant
    if pr.status not in {"draft", "rfq_issued"}:
        # Still allow re-issuing if in draft/rfq_issued state
        return None
    rfq = _issue_rfq_record(
        pr=pr,
        vendors=request.vendors,
        due_in_days=request.due_in_days,
        notes=request.notes,
    )
    from .audit import emit
    emit(
        action="issued",
        entity_kind="rfq",
        entity_id=rfq.rfq_no,
        subject=rfq.rfq_no,
        summary=f"RFQ {rfq.rfq_no} issued to {len(rfq.vendors)} vendors for {rfq.code}",
        source="api",
        tenant_id=rfq.tenant_id,
        project_id=rfq.project_id,
        bom_item_id=pr.bom_item_id,
        bom_code=rfq.code,
        pr_no=pr.pr_no,
        rfq_no=rfq.rfq_no,
        metadata={"vendors": list(rfq.vendors), "due_at": str(rfq.due_at)},
    )
    return rfq


def _add_quote_record(rfq: RFQ, request: CreateQuoteRequest) -> Quote:
    quote = Quote(
        quote_id=_next("quote", "Q", width=5),
        tenant_id=rfq.tenant_id,
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


@invalidates_cache
def add_quote(
    rfq_no: str,
    request: CreateQuoteRequest,
    tenant_id: Optional[str] = None,
) -> Optional[Quote]:
    _seed()
    rfq = _rfqs.get(rfq_no)
    if not rfq:
        return None
    if tenant_id is not None and rfq.tenant_id != tenant_id:
        return None
    quote = _add_quote_record(rfq, request)
    from .audit import emit
    pr = _prs.get(rfq.pr_no)
    emit(
        action="received",
        entity_kind="quote",
        entity_id=quote.quote_id,
        subject=f"{quote.vendor} → {rfq.rfq_no}",
        summary=(
            f"Quote {quote.quote_id} from {quote.vendor}: "
            f"${quote.unit_price_usd:,.2f}/u × {quote.quantity:.0f} = ${quote.total_usd:,.0f}, "
            f"lead {quote.lead_time_days}d, {quote.incoterm}"
        ),
        source="api",
        tenant_id=rfq.tenant_id,
        project_id=rfq.project_id,
        bom_item_id=pr.bom_item_id if pr else None,
        bom_code=rfq.code,
        pr_no=rfq.pr_no,
        rfq_no=rfq.rfq_no,
        quote_id=quote.quote_id,
        vendor=quote.vendor,
        metadata={
            "unit_price_usd": quote.unit_price_usd,
            "lead_time_days": quote.lead_time_days,
            "incoterm": quote.incoterm,
            "validity_days": quote.validity_days,
        },
    )
    return quote


# --- Quote comparison + award -----------------------------------------------


def compare_quotes(rfq_no: str, tenant_id: Optional[str] = None) -> Optional[QuoteComparison]:
    _seed()
    rfq = _rfqs.get(rfq_no)
    if not rfq:
        return None
    if tenant_id is not None and rfq.tenant_id != tenant_id:
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


@invalidates_cache
def award_rfq(
    rfq_no: str,
    request: AwardRFQRequest,
    tenant_id: Optional[str] = None,
) -> Optional[Award]:
    _seed()
    rfq = _rfqs.get(rfq_no)
    if not rfq:
        return None
    if tenant_id is not None and rfq.tenant_id != tenant_id:
        return None
    quotes = _quotes_by_rfq.get(rfq_no, [])
    quote = next((q for q in quotes if q.quote_id == request.quote_id), None)
    if not quote:
        return None

    award_id = _next("award", "AWD", width=4)
    rationale = request.rationale
    if not rationale:
        comparison = compare_quotes(rfq_no)
        # Try LLM-generated rationale citing actual quote diffs + vendor profile.
        # Falls back to the templated comparison rationale if LLM unavailable.
        llm_rationale = _llm_award_rationale(rfq=rfq, quotes=quotes, winner=quote, comparison=comparison)
        rationale = llm_rationale or (
            comparison.recommendation_rationale
            if comparison and comparison.recommendation_rationale
            else f"Awarded to {quote.vendor}."
        )

    award = Award(
        award_id=award_id,
        tenant_id=rfq.tenant_id,
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

    from .audit import emit
    emit(
        action="awarded",
        entity_kind="award",
        entity_id=award.award_id,
        subject=f"{award.vendor} · {rfq.code}",
        summary=f"Awarded {award.award_id} to {award.vendor} for ${award.awarded_value_usd:,.0f}",
        actor=award.awarded_by,
        source="api",
        tenant_id=award.tenant_id,
        project_id=rfq.project_id,
        bom_item_id=pr.bom_item_id if pr else None,
        bom_code=rfq.code,
        pr_no=rfq.pr_no,
        rfq_no=rfq.rfq_no,
        quote_id=quote.quote_id,
        award_id=award.award_id,
        vendor=award.vendor,
        metadata={
            "rationale": award.rationale[:300],
            "lead_time_days": quote.lead_time_days,
            "incoterm": quote.incoterm,
        },
    )
    emit(
        action="po_drafted",
        entity_kind="po",
        entity_id=po.po_no,
        subject=po.po_no,
        summary=f"PO {po.po_no} drafted to {po.vendor} · ${po.value_usd:,.0f} · need-by {po.need_by or 'TBD'}",
        actor=award.awarded_by,
        source="api",
        tenant_id=po.tenant_id,
        project_id=po.project_id,
        bom_item_id=pr.bom_item_id if pr else None,
        bom_code=po.code,
        pr_no=po.pr_no,
        rfq_no=po.rfq_no,
        award_id=po.award_id,
        po_no=po.po_no,
        vendor=po.vendor,
        metadata={
            "value_usd": po.value_usd,
            "lead_time_days": po.lead_time_days,
            "incoterm": po.incoterm,
        },
    )
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
        tenant_id=award.tenant_id,
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


def list_awards(tenant_id: Optional[str] = None) -> List[Award]:
    _seed()
    awards = sorted(_awards.values(), key=lambda a: a.awarded_at, reverse=True)
    if tenant_id is None:
        return awards
    return [a for a in awards if a.tenant_id == tenant_id]


def list_pos(tenant_id: Optional[str] = None) -> List[SourcingPO]:
    _seed()
    pos = sorted(_pos.values(), key=lambda p: p.created_at, reverse=True)
    if tenant_id is None:
        return pos
    return [p for p in pos if p.tenant_id == tenant_id]


def get_po(po_no: str, tenant_id: Optional[str] = None) -> Optional[SourcingPO]:
    _seed()
    po = _pos.get(po_no)
    if po is None:
        return None
    if tenant_id is not None and po.tenant_id != tenant_id:
        return None
    return po


def build_timeline(po_no: str, tenant_id: Optional[str] = None) -> Optional[SourcingTimeline]:
    _seed()
    po = _pos.get(po_no)
    if not po:
        return None
    if tenant_id is not None and po.tenant_id != tenant_id:
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


# --- LLM helpers (Grok-driven prose) -----------------------------------------


def _llm_award_rationale(
    *,
    rfq: RFQ,
    quotes: list,
    winner: Quote,
    comparison: Optional[QuoteComparison],
) -> Optional[str]:
    """Generate a 100-150 word award rationale via Grok.

    Cites concrete diffs (price gap, lead-time gap, OTD score) and any risk
    flags on the winner. Returns None on failure so caller can fall back to
    the templated comparison rationale.
    """

    from .llm import grok_chat, is_enabled
    from .vendor_intel import get_vendor_scorecard

    if not is_enabled():
        return None

    # Sort quotes by total_usd for clean diff narrative
    sorted_q = sorted(quotes, key=lambda q: q.total_usd)
    lowest = sorted_q[0]
    fastest = min(quotes, key=lambda q: q.lead_time_days)

    win_score = get_vendor_scorecard(winner.vendor)

    summary = {
        "rfq": {
            "code": rfq.code,
            "description": rfq.description,
            "quantity": rfq.quantity,
            "uom": rfq.uom,
        },
        "winner": {
            "vendor": winner.vendor,
            "unit_price_usd": winner.unit_price_usd,
            "total_usd": winner.total_usd,
            "lead_time_days": winner.lead_time_days,
            "notes": winner.notes,
            "scorecard": (
                {
                    "composite_score": win_score.composite_score,
                    "composite_grade": win_score.composite_grade,
                    "flags": win_score.flags,
                    "single_source_exposure": win_score.single_source_exposure,
                }
                if win_score
                else None
            ),
        },
        "alternates": [
            {
                "vendor": q.vendor,
                "total_usd": q.total_usd,
                "lead_time_days": q.lead_time_days,
                "delta_vs_winner_pct": round((q.total_usd - winner.total_usd) / winner.total_usd * 100, 1) if winner.total_usd else 0,
            }
            for q in sorted_q
            if q.quote_id != winner.quote_id
        ],
        "lowest_total": {"vendor": lowest.vendor, "total_usd": lowest.total_usd},
        "fastest_lead": {"vendor": fastest.vendor, "lead_time_days": fastest.lead_time_days},
        "engine_recommendation": comparison.recommended_vendor if comparison else None,
    }

    system = (
        "You write concise award rationales for an engineering procurement team. "
        "Cite concrete numbers from the data — price gaps, lead-time gaps, scorecard "
        "components, risk flags. If the winner was not the engine's recommendation "
        "or the lowest price, name the trade-off explicitly. Output 2-3 sentences, "
        "no more than 100 words. Plain prose, no markdown."
    )
    import json as _json
    user = (
        "Write the award rationale for this RFQ. Data follows:\n\n"
        + _json.dumps(summary, default=str, indent=2)
    )
    return grok_chat(system, user, max_tokens=250, temperature=0.3, timeout=25)


# --- SAP CPI submission ------------------------------------------------------


def submit_pr_to_sap(pr_no: str, tenant_id: Optional[str] = None):
    """Submit a draft PR to SAP via CPI. Updates the in-memory PR with the
    SAP doc number and status. Returns the updated PR or None if not found.
    """

    from .audit import emit
    from .integrations import sap_cpi
    pr = _prs.get(pr_no)
    if not pr:
        return None
    if tenant_id is not None and pr.tenant_id != tenant_id:
        return None
    pr.sap_status = "submitting"
    pr.sap_error = None
    _prs[pr_no] = pr

    result = sap_cpi.submit_pr(pr)
    pr.sap_status = result["sap_status"]
    pr.sap_pr_no = result.get("sap_pr_no")
    pr.sap_error = result.get("error")
    pr.sap_last_synced_at = _now()
    _prs[pr_no] = pr

    emit(
        action="submitted_to_sap",
        entity_kind="pr",
        entity_id=pr.pr_no,
        subject=pr.pr_no,
        summary=(
            f"PR {pr.pr_no} → SAP: {pr.sap_status}"
            + (f" (doc {pr.sap_pr_no})" if pr.sap_pr_no else "")
            + (f" — {pr.sap_error}" if pr.sap_error else "")
        ),
        actor="sap_cpi",
        source="api",
        tenant_id=pr.tenant_id,
        project_id=pr.project_id,
        bom_item_id=pr.bom_item_id,
        bom_code=pr.code,
        pr_no=pr.pr_no,
        sap_doc_no=pr.sap_pr_no,
        metadata={"sap_status": pr.sap_status, "sap_error": pr.sap_error},
    )
    return pr


def submit_po_to_sap(po_no: str, tenant_id: Optional[str] = None):
    """Submit a sourcing PO to SAP via CPI."""

    from .audit import emit
    from .integrations import sap_cpi
    po = _pos.get(po_no)
    if not po:
        return None
    if tenant_id is not None and po.tenant_id != tenant_id:
        return None
    po.sap_status = "submitting"
    po.sap_error = None
    _pos[po_no] = po

    result = sap_cpi.submit_po(po)
    po.sap_status = result["sap_status"]
    po.sap_po_no = result.get("sap_po_no")
    po.sap_error = result.get("error")
    po.sap_last_synced_at = _now()
    _pos[po_no] = po

    pr_for_po = _prs.get(po.pr_no)
    emit(
        action="submitted_to_sap",
        entity_kind="po",
        entity_id=po.po_no,
        subject=po.po_no,
        summary=(
            f"PO {po.po_no} → SAP: {po.sap_status}"
            + (f" (doc {po.sap_po_no})" if po.sap_po_no else "")
            + (f" — {po.sap_error}" if po.sap_error else "")
        ),
        actor="sap_cpi",
        source="api",
        tenant_id=po.tenant_id,
        project_id=po.project_id,
        bom_item_id=pr_for_po.bom_item_id if pr_for_po else None,
        bom_code=po.code,
        pr_no=po.pr_no,
        rfq_no=po.rfq_no,
        award_id=po.award_id,
        po_no=po.po_no,
        vendor=po.vendor,
        sap_doc_no=po.sap_po_no,
        metadata={"sap_status": po.sap_status, "sap_error": po.sap_error},
    )
    return po


def apply_sap_event(event) -> tuple[bool, Optional[str], Optional[str], Optional[str]]:
    """Apply an inbound SAP event to the matching PR or PO.

    Match priority: ct_ref (Control Tower's PR/PO number) > sap_doc_no.
    Returns (accepted, matched_ct_ref, applied_to, note).
    """

    from .audit import emit

    def _record(kind: str, ent_id: str, ct_ref: str, action_str: str, extra_meta: dict | None = None):
        # Map SAP event kind to a strong audit action when possible
        action_map = {
            "pr_released": "approved",
            "pr_rejected": "rejected",
            "po_released": "approved",
            "po_blocked": "rejected",
            "gr_posted": "gr_posted",
            "ir_posted": "ir_posted",
            "po_closed": "delivered",
        }
        action_value = action_map.get(event.kind, "sap_status_changed")
        # Enrich with vendor + bom_code from the linked entity
        vendor = None
        bom_code = None
        project_id = None
        bom_item_id = None
        event_tenant_id = ""
        if kind == "po":
            po_ref = _pos.get(ct_ref)
            if po_ref:
                vendor = po_ref.vendor
                bom_code = po_ref.code
                project_id = po_ref.project_id
                event_tenant_id = po_ref.tenant_id
                pr_for_po = _prs.get(po_ref.pr_no)
                if pr_for_po:
                    bom_item_id = pr_for_po.bom_item_id
        elif kind == "pr":
            pr_ref = _prs.get(ct_ref)
            if pr_ref:
                bom_code = pr_ref.code
                bom_item_id = pr_ref.bom_item_id
                project_id = pr_ref.project_id
                event_tenant_id = pr_ref.tenant_id
        emit(
            action=action_value,  # type: ignore[arg-type]
            entity_kind=kind,  # type: ignore[arg-type]
            entity_id=ent_id,
            subject=f"SAP · {event.sap_doc_no}",
            summary=action_str,
            actor="sap_cpi",
            source="sap_webhook",
            tenant_id=event_tenant_id,
            project_id=project_id,
            bom_item_id=bom_item_id,
            bom_code=bom_code,
            pr_no=ct_ref if kind == "pr" else None,
            po_no=ct_ref if kind == "po" else None,
            vendor=vendor,
            sap_doc_no=event.sap_doc_no,
            metadata={
                "kind": event.kind,
                "quantity": event.quantity,
                "value_usd": event.value_usd,
                **(extra_meta or {}),
            },
        )

    # Try CT ref first
    if event.ct_ref:
        if event.ct_ref in _prs:
            _apply_to_pr(_prs[event.ct_ref], event)
            _record("pr", event.ct_ref, event.ct_ref, f"SAP event {event.kind} applied to PR {event.ct_ref}")
            return True, event.ct_ref, "PR", f"applied {event.kind} to PR {event.ct_ref}"
        if event.ct_ref in _pos:
            _apply_to_po(_pos[event.ct_ref], event)
            _record("po", event.ct_ref, event.ct_ref, f"SAP event {event.kind} applied to PO {event.ct_ref}")
            return True, event.ct_ref, "PO", f"applied {event.kind} to PO {event.ct_ref}"

    # Fallback: match by SAP doc number
    for pr in _prs.values():
        if pr.sap_pr_no == event.sap_doc_no:
            _apply_to_pr(pr, event)
            _record("pr", pr.pr_no, pr.pr_no, f"SAP event {event.kind} applied to PR {pr.pr_no}")
            return True, pr.pr_no, "PR", f"applied {event.kind} to PR {pr.pr_no}"
    for po in _pos.values():
        if po.sap_po_no == event.sap_doc_no:
            _apply_to_po(po, event)
            _record("po", po.po_no, po.po_no, f"SAP event {event.kind} applied to PO {po.po_no}")
            return True, po.po_no, "PO", f"applied {event.kind} to PO {po.po_no}"

    return False, None, None, f"no matching PR/PO for sap_doc_no={event.sap_doc_no}"


def _apply_to_pr(pr: PurchaseRequisition, event) -> None:
    pr.sap_last_synced_at = _now()
    if event.kind == "pr_released":
        pr.sap_status = "synced"
        pr.status = "rfq_issued"  # SAP-released PRs are ready to source
    elif event.kind == "pr_rejected":
        pr.sap_status = "failed"
        pr.sap_error = "Rejected in SAP"
    _prs[pr.pr_no] = pr


def _apply_to_po(po: SourcingPO, event) -> None:
    po.sap_last_synced_at = _now()
    if event.kind == "po_released":
        po.sap_status = "synced"
        po.status = "released"
    elif event.kind == "po_blocked":
        po.sap_status = "failed"
        po.sap_error = "Blocked in SAP"
    elif event.kind == "gr_posted" and event.quantity is not None:
        po.sap_gr_qty = (po.sap_gr_qty or 0) + float(event.quantity)
        if po.sap_gr_qty >= po.quantity:
            po.status = "delivered"
    elif event.kind == "ir_posted" and event.value_usd is not None:
        po.sap_ir_value_usd = (po.sap_ir_value_usd or 0) + float(event.value_usd)
    elif event.kind == "po_closed":
        po.status = "delivered"
    _pos[po.po_no] = po


def apply_ct_receipt(po_no: str, qty: float, tenant_id: str, grn_no: str) -> Optional[SourcingPO]:
    """Accumulate a site (Storemark) goods receipt onto a sourcing PO.

    Site receipts land on ct_gr_qty — never sap_gr_qty; the two channels stay
    separate and 'delivered' flips when either reaches the PO quantity.
    Caller owns audit emission and cache invalidation.
    """
    po = _pos.get(po_no)
    if po is None or po.tenant_id != tenant_id:
        return None
    po.ct_gr_qty = (po.ct_gr_qty or 0) + float(qty)
    if po.status != "delivered" and max(po.ct_gr_qty, po.sap_gr_qty or 0) >= po.quantity:
        po.status = "delivered"
        po.ct_delivered_at = _now()
    _pos[po_no] = po
    return po

