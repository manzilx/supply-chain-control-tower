"""M7.3 — Approvals workflow.

High-risk procurement writes pass through a governance gate before they
commit:

  * Awarding an RFQ whose PO value is >= $50k          -> po_create
  * Awarding a single-source / comparison-override RFQ -> award_single_source
  * Receiving a quote that exceeds the PR budget x1.10  -> quote_above_budget
  * Onboarding a new vendor                             -> vendor_onboarding

The acting user's role decides what happens when a rule fires:

  * If the user can already `approval:decide` (procurement_head / admin) the
    action commits immediately and we record an `auto_approved` Approval for
    the audit trail.
  * Otherwise a `pending` Approval is created with the *frozen request
    payload*; a head/admin later approves it, the registered committer
    replays the payload, and the resource (PO, quote) materialises.

State is per-tenant and snapshotted by `app.persistence`.
"""

from __future__ import annotations

import logging

from ._cache import invalidates_cache

from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from .auth import has_perm
from .schemas import (
    Approval,
    ApprovalKind,
    ApprovalRule,
    AwardRFQRequest,
    CreateQuoteRequest,
    GatedAwardReply,
    GatedQuoteReply,
    GatedVendorReply,
    Role,
    SupplierRecord,
    User,
)

log = logging.getLogger("ct.approvals")

PO_APPROVAL_THRESHOLD_USD = 50_000.0
QUOTE_BUDGET_TOLERANCE = 1.10

# tenant_id -> approval_id -> Approval
_approvals: Dict[str, Dict[str, Approval]] = {}
_counter = {"approval": 0}

# kind -> committer(payload, tenant_id) -> result_ref (str|None)
_committers: Dict[ApprovalKind, Callable[[dict, str], Optional[str]]] = {}


RULES: List[ApprovalRule] = [
    ApprovalRule(
        kind="po_create",
        condition_summary=f"PO value >= ${PO_APPROVAL_THRESHOLD_USD:,.0f}",
        required_role="procurement_head",
        auto_below_value_usd=PO_APPROVAL_THRESHOLD_USD,
    ),
    ApprovalRule(
        kind="award_single_source",
        condition_summary="Only one vendor quoted, or award overrides the comparison winner",
        required_role="procurement_head",
    ),
    ApprovalRule(
        kind="quote_above_budget",
        condition_summary=f"Quote total exceeds PR budget x{QUOTE_BUDGET_TOLERANCE}",
        required_role="procurement_head",
    ),
    ApprovalRule(
        kind="vendor_onboarding",
        condition_summary="New vendor added to the approved supplier master",
        required_role="procurement_head",
    ),
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _po_for_award(award, tenant_id: str):
    """Resolve the SourcingPO created by an award (linked via its PR)."""
    if not award:
        return None
    from . import sourcing
    pr = sourcing.get_pr(award.pr_no, tenant_id=tenant_id)
    if pr and pr.po_no:
        return sourcing.get_po(pr.po_no, tenant_id=tenant_id)
    return None


def _next_id() -> str:
    _counter["approval"] += 1
    return f"APR-{_counter['approval']:04d}"


def register_committer(kind: ApprovalKind, fn: Callable[[dict, str], Optional[str]]) -> None:
    _committers[kind] = fn


def _flush_critical_safe() -> None:
    try:
        from .persistence import flush_critical

        flush_critical()
    except Exception:  # noqa: BLE001
        log.exception("flush_critical failed after approval mutation")


def _store(approval: Approval) -> Approval:
    _approvals.setdefault(approval.tenant_id, {})[approval.approval_id] = approval
    _flush_critical_safe()
    return approval


def _make_approval(
    *,
    kind: ApprovalKind,
    tenant_id: str,
    title: str,
    summary: str,
    payload: dict,
    user: User,
    status: str,
    result_ref: Optional[str] = None,
) -> Approval:
    rule = next((r for r in RULES if r.kind == kind), None)
    now = _now()
    approval = Approval(
        approval_id=_next_id(),
        tenant_id=tenant_id,
        kind=kind,
        title=title,
        summary=summary,
        payload=payload,
        requested_by=user.user_id,
        requested_by_name=user.display_name,
        requested_at=now,
        required_role=(rule.required_role if rule else "procurement_head"),
        status=status,  # type: ignore[arg-type]
        result_ref=result_ref,
    )
    if status == "auto_approved":
        approval.decided_by = user.user_id
        approval.decided_by_name = user.display_name
        approval.decided_at = now
        approval.decision_note = "Auto-approved — requester holds decision authority."
    return _store(approval)


def _can_self_approve(user: User) -> bool:
    return has_perm(user.role, "approval", "decide")


# --- Read API ----------------------------------------------------------------


def list_approvals(tenant_id: str, user: Optional[User] = None) -> List[Approval]:
    """Approvals for a tenant, newest first.

    Heads/admins see everything; other roles see only the ones they raised.
    """
    items = list(_approvals.get(tenant_id, {}).values())
    if user is not None and not _can_self_approve(user):
        items = [a for a in items if a.requested_by == user.user_id]
    return sorted(items, key=lambda a: a.requested_at, reverse=True)


def get_approval(tenant_id: str, approval_id: str) -> Optional[Approval]:
    return _approvals.get(tenant_id, {}).get(approval_id)


def pending_count(tenant_id: str, user: Optional[User] = None) -> int:
    return sum(1 for a in list_approvals(tenant_id, user) if a.status == "pending")


# --- Decision ----------------------------------------------------------------


@invalidates_cache
def decide(
    tenant_id: str,
    approval_id: str,
    approver: User,
    approve: bool,
    note: Optional[str] = None,
) -> Optional[Approval]:
    approval = get_approval(tenant_id, approval_id)
    if approval is None:
        return None
    if approval.status != "pending":
        return approval  # idempotent — already decided
    approval.decided_by = approver.user_id
    approval.decided_by_name = approver.display_name
    approval.decided_at = _now()
    approval.decision_note = note
    if approve:
        approval.status = "approved"
        committer = _committers.get(approval.kind)
        if committer is not None:
            try:
                commit_payload = {**approval.payload, "_decided_by": approver.user_id}
                approval.result_ref = committer(commit_payload, tenant_id)
            except Exception as e:  # noqa: BLE001
                approval.decision_note = (
                    (note + " | " if note else "")
                    + f"commit failed: {type(e).__name__}: {e}"
                )
    else:
        approval.status = "rejected"
    _flush_critical_safe()
    return approval


# --- Gates (called by routes) ------------------------------------------------


def gate_award(rfq_no: str, request: AwardRFQRequest, user: User) -> GatedAwardReply:
    """Evaluate an award for approval. Commits immediately (returning the
    award + PO) when no rule fires or the user can self-approve; otherwise
    returns a pending Approval and does NOT touch sourcing state."""
    from . import sourcing

    tenant_id = user.tenant_id
    rfq = sourcing.get_rfq(rfq_no, tenant_id=tenant_id)
    if rfq is None:
        # Let the normal route 404 — gate only handles the happy path.
        award = sourcing.award_rfq(rfq_no, request, tenant_id=tenant_id)
        return GatedAwardReply(status="applied", award=award)

    quotes = sourcing.get_quotes(rfq_no, tenant_id=tenant_id)
    quote = next((q for q in quotes if q.quote_id == request.quote_id), None)
    value = quote.total_usd if quote else 0.0

    # Single-source / override detection
    distinct_vendors = {q.vendor for q in quotes}
    single_source = len(distinct_vendors) <= 1
    comparison = sourcing.compare_quotes(rfq_no, tenant_id=tenant_id)
    override = bool(
        comparison
        and comparison.recommended_vendor
        and quote
        and quote.vendor != comparison.recommended_vendor
    )

    kind: Optional[ApprovalKind] = None
    reason = ""
    if single_source or override:
        kind = "award_single_source"
        reason = (
            "Single vendor quoted" if single_source else "Award overrides the comparison winner"
        )
    elif value >= PO_APPROVAL_THRESHOLD_USD:
        kind = "po_create"
        reason = f"PO value ${value:,.0f} ≥ ${PO_APPROVAL_THRESHOLD_USD:,.0f}"

    payload = {"rfq_no": rfq_no, "request": request.model_dump(mode="json")}
    vendor = quote.vendor if quote else "?"
    title = f"Award {rfq.code} to {vendor}"
    summary = f"{reason} · ${value:,.0f} · {rfq.code} ({rfq_no})"

    if kind is None:
        # No gate — commit normally.
        award = sourcing.award_rfq(rfq_no, request, tenant_id=tenant_id)
        return GatedAwardReply(status="applied", award=award, po=_po_for_award(award, tenant_id))

    if _can_self_approve(user):
        # Authorised — commit + record auto-approval.
        award = sourcing.award_rfq(rfq_no, request, tenant_id=tenant_id)
        po = _po_for_award(award, tenant_id)
        result_ref = po.po_no if po else (award.award_id if award else None)
        _make_approval(
            kind=kind, tenant_id=tenant_id, title=title, summary=summary,
            payload=payload, user=user, status="auto_approved", result_ref=result_ref,
        )
        return GatedAwardReply(status="applied", award=award, po=po)

    # Gated — create pending approval, do not commit.
    approval = _make_approval(
        kind=kind, tenant_id=tenant_id, title=title, summary=summary,
        payload=payload, user=user, status="pending",
    )
    return GatedAwardReply(status="pending_approval", approval=approval)


def gate_quote(rfq_no: str, request: CreateQuoteRequest, user: User) -> GatedQuoteReply:
    from . import sourcing

    tenant_id = user.tenant_id
    rfq = sourcing.get_rfq(rfq_no, tenant_id=tenant_id)
    if rfq is None:
        quote = sourcing.add_quote(rfq_no, request, tenant_id=tenant_id)
        return GatedQuoteReply(status="applied", quote=quote)

    qty = request.quantity or rfq.quantity
    total = float(request.unit_price_usd) * float(qty)

    pr = sourcing.get_pr(rfq.pr_no, tenant_id=tenant_id)
    budget = pr.budget_value_usd if pr else None
    over_budget = bool(budget and total > budget * QUOTE_BUDGET_TOLERANCE)

    if not over_budget:
        quote = sourcing.add_quote(rfq_no, request, tenant_id=tenant_id)
        return GatedQuoteReply(status="applied", quote=quote)

    payload = {"rfq_no": rfq_no, "request": request.model_dump(mode="json")}
    title = f"Over-budget quote · {rfq.code}"
    summary = (
        f"{request.vendor} quoted ${total:,.0f} vs ${budget:,.0f} budget "
        f"(+{(total / budget - 1) * 100:.0f}%) on {rfq.code}"
    )

    if _can_self_approve(user):
        quote = sourcing.add_quote(rfq_no, request, tenant_id=tenant_id)
        _make_approval(
            kind="quote_above_budget", tenant_id=tenant_id, title=title, summary=summary,
            payload=payload, user=user, status="auto_approved",
            result_ref=quote.quote_id if quote else None,
        )
        return GatedQuoteReply(status="applied", quote=quote)

    approval = _make_approval(
        kind="quote_above_budget", tenant_id=tenant_id, title=title, summary=summary,
        payload=payload, user=user, status="pending",
    )
    return GatedQuoteReply(status="pending_approval", approval=approval)


def gate_vendor(supplier: SupplierRecord, user: User) -> GatedVendorReply:
    """Always gates vendor onboarding. Commits immediately when the user can
    self-approve; otherwise returns a pending Approval without touching the
    vendor store."""
    from . import vendor_intel
    from . import vendor_store

    tenant_id = user.tenant_id
    kind: ApprovalKind = "vendor_onboarding"
    payload = {"supplier": supplier.model_dump(mode="json")}
    title = f"Onboard vendor · {supplier.name}"
    summary = f"{supplier.name} · {supplier.category} · {supplier.country}"

    if _can_self_approve(user):
        vendor_store.add_supplier(tenant_id, supplier)
        scorecard = vendor_intel.get_vendor_scorecard(supplier.name, tenant_id=tenant_id)
        _make_approval(
            kind=kind,
            tenant_id=tenant_id,
            title=title,
            summary=summary,
            payload=payload,
            user=user,
            status="auto_approved",
            result_ref=supplier.name,
        )
        return GatedVendorReply(status="applied", scorecard=scorecard)

    approval = _make_approval(
        kind=kind,
        tenant_id=tenant_id,
        title=title,
        summary=summary,
        payload=payload,
        user=user,
        status="pending",
    )
    return GatedVendorReply(status="pending_approval", approval=approval)


# --- Committers --------------------------------------------------------------


def _commit_award(payload: dict, tenant_id: str) -> Optional[str]:
    from . import sourcing
    req = AwardRFQRequest(**payload["request"])
    award = sourcing.award_rfq(payload["rfq_no"], req, tenant_id=tenant_id)
    if not award:
        raise RuntimeError("award commit produced no award")
    po = _po_for_award(award, tenant_id)
    return po.po_no if po else award.award_id


def _commit_quote(payload: dict, tenant_id: str) -> Optional[str]:
    from . import sourcing
    req = CreateQuoteRequest(**payload["request"])
    quote = sourcing.add_quote(payload["rfq_no"], req, tenant_id=tenant_id)
    if not quote:
        raise RuntimeError("quote commit produced no quote")
    return quote.quote_id


def _commit_vendor(payload: dict, tenant_id: str) -> Optional[str]:
    from . import vendor_store
    from .audit import emit
    from .vendor_intel import get_vendor_scorecard

    supplier = SupplierRecord(**payload["supplier"])
    vendor_store.add_supplier(tenant_id, supplier)
    scorecard = get_vendor_scorecard(supplier.name, tenant_id=tenant_id)
    actor = payload.get("_decided_by") or "system"
    if scorecard is not None:
        emit(
            action="created",
            entity_kind="vendor",
            entity_id=supplier.name,
            subject=supplier.name,
            summary=(
                f"Vendor {supplier.name} added · {supplier.category} · {supplier.country} · "
                f"composite {scorecard.composite_score} grade {scorecard.composite_grade}"
            ),
            actor=actor,
            source="api",
            tenant_id=tenant_id,
            vendor=supplier.name,
            metadata={
                "category": supplier.category,
                "country": supplier.country,
                "lead_time_days": supplier.lead_time_days,
                "on_time_delivery_pct": supplier.on_time_delivery_pct,
                "quality_ppm": supplier.quality_ppm,
                "annual_spend_usd": supplier.annual_spend_usd,
                "approved_alternatives": supplier.approved_alternatives,
                "risk_flags": supplier.risk_flags,
            },
        )
    return supplier.name


register_committer("po_create", _commit_award)
register_committer("award_single_source", _commit_award)
register_committer("quote_above_budget", _commit_quote)
register_committer("vendor_onboarding", _commit_vendor)


# --- Persistence hooks -------------------------------------------------------


def dump() -> dict:
    return {
        "counter": _counter,
        "approvals": {
            tid: {aid: a.model_dump(mode="json") for aid, a in bucket.items()}
            for tid, bucket in _approvals.items()
        },
    }


def load(data: dict) -> None:
    _approvals.clear()
    for tid, bucket in (data.get("approvals") or {}).items():
        _approvals[tid] = {aid: Approval(**a) for aid, a in bucket.items()}
    saved = data.get("counter") or {}
    _counter["approval"] = int(saved.get("approval", 0))
