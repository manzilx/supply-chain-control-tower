"""Persisted per-project risk register, seeded from live process signals.

Upsert by signal_key refreshes title/detail/severity but never resets
status, owner, or mitigation. Disappeared signals set live=False.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from threading import Lock
from typing import Dict, List, Optional

from ._cache import invalidates_cache
from .schemas import (
    CreateManagedRiskRequest,
    ManagedRisk,
    PatchManagedRiskRequest,
    ProcessStageName,
    Severity,
)


log = logging.getLogger("ct.risk_register")

# tenant_id -> risk_id -> ManagedRisk
_risks: Dict[str, Dict[str, ManagedRisk]] = {}
_counter = {"risk": 0}
_lock = Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _next_id() -> str:
    """Caller must hold _lock."""
    _counter["risk"] += 1
    return f"RSK-{_counter['risk']:04d}"


def _flush() -> None:
    try:
        from .persistence import flush_critical
        flush_critical()
    except Exception:  # noqa: BLE001
        log.exception("flush_critical failed after risk mutation")


def list_project_risks(project_id: str, tenant_id: str) -> List[ManagedRisk]:
    with _lock:
        items = [
            r for r in _risks.get(tenant_id, {}).values()
            if r.project_id == project_id
        ]
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return sorted(items, key=lambda r: (rank.get(r.severity, 9), r.title))


def get_risk(tenant_id: str, risk_id: str) -> Optional[ManagedRisk]:
    with _lock:
        return _risks.get(tenant_id, {}).get(risk_id)


def _upsert_live(
    *,
    tenant_id: str,
    project_id: str,
    signal_key: str,
    title: str,
    detail: str,
    severity: Severity,
    category: str,
    process_stage: Optional[ProcessStageName],
    href: str,
) -> None:
    """Caller must hold _lock."""
    now = _now()
    existing = next(
        (
            r for r in _risks.get(tenant_id, {}).values()
            if r.project_id == project_id and r.signal_key == signal_key
        ),
        None,
    )
    if existing:
        changed = (
            existing.title != title
            or existing.detail != detail
            or existing.severity != severity
            or existing.category != category
            or existing.process_stage != process_stage
            or existing.href != href
            or not existing.live
        )
        existing.title = title
        existing.detail = detail
        existing.severity = severity
        existing.category = category
        existing.process_stage = process_stage
        existing.href = href
        existing.live = True
        if changed:
            existing.updated_at = now
        _risks[tenant_id][existing.risk_id] = existing
        return
    risk = ManagedRisk(
        risk_id=_next_id(),
        tenant_id=tenant_id,
        project_id=project_id,
        signal_key=signal_key,
        source="live",
        live=True,
        title=title,
        detail=detail,
        severity=severity,
        category=category,
        process_stage=process_stage,
        href=href,
        created_at=now,
        updated_at=now,
    )
    _risks.setdefault(tenant_id, {})[risk.risk_id] = risk


def seed_project(project_id: str, tenant_id: str) -> None:
    """Collect live signals and upsert. Marks vanished live rows live=False."""
    from .approvals import list_approvals
    from .commercial import build_commercial_lines
    from .expediting import build_expedite_queue
    from .planning import compute_project_progress, get_bom, get_project
    from .sourcing import list_pos, list_rfqs
    from .vendor_intel import list_vendor_summaries

    project = get_project(project_id, tenant_id=tenant_id)
    if project is None:
        return

    today = date.today()
    seen: set[str] = set()
    pending: List[tuple] = []

    def add(key: str, **kwargs) -> None:
        seen.add(key)
        pending.append((key, kwargs))

    bom = get_bom(project_id, tenant_id=tenant_id)
    for b in bom:
        if b.status != "spec_missing":
            continue
        add(
            f"spec:{b.bom_item_id}",
            title=f"Missing spec: {b.code}",
            detail=b.description,
            severity="high",
            category="engineering",
            process_stage="spec",
            href=f"/projects/{project_id}/bom",
        )

    prog = compute_project_progress(project_id, tenant_id=tenant_id)
    for m in project.milestones:
        days = (m.required_on_site_date - today).days
        if days > 30:
            continue
        behind = prog is not None and (
            (prog.bom_delivered_pct + prog.spend_committed_pct) / 2 + 15 < prog.milestones_pct
        )
        if days > 14 and not behind:
            continue
        sev: Severity = "critical" if days <= 7 else "high" if days <= 14 else "medium"
        due_label = f"overdue by {-days}d" if days < 0 else f"due in {days}d"
        add(
            f"milestone:{m.code}",
            title=f"{m.code} {m.name} {due_label}",
            detail="Physical progress lagging schedule" if behind else f"Required on site {m.required_on_site_date.isoformat()}",
            severity=sev,
            category="schedule",
            process_stage="delivery",
            href=f"/projects/{project_id}",
        )

    for item in build_expedite_queue(tenant_id=tenant_id).items:
        if item.project_id != project_id or item.source != "sourcing":
            continue
        if item.urgency not in {"nudge", "escalate"}:
            continue
        sev = "critical" if item.urgency == "escalate" else "high"
        add(
            f"expedite:{item.po_number}",
            title=f"{item.urgency.title()} {item.po_number} · {item.supplier_name}",
            detail=f"{item.slip_probability_pct}% slip probability, {item.predicted_slip_days}d expected slip",
            severity=sev,
            category="expediting",
            process_stage="shipment",
            href="/expediting",
        )

    commercial_ok = True
    try:
        for line in build_commercial_lines(tenant_id=tenant_id):
            if line.project_id != project_id or line.variance_pct <= 5:
                continue
            add(
                f"commercial:{line.ref_id}",
                title=f"Over budget: {line.code}",
                detail=f"+{line.variance_pct:.0f}% variance on {line.code}",
                severity="high" if line.variance_pct > 15 else "medium",
                category="commercial",
                process_stage="award",
                href="/commercial",
            )
    except Exception:  # noqa: BLE001
        commercial_ok = False
        log.exception("commercial collector failed; leaving commercial risks live")

    vendors_used = {b.supplier_name for b in bom if b.supplier_name}
    vendors_used.update(p.vendor for p in list_pos(tenant_id=tenant_id) if p.project_id == project_id)
    for v in list_vendor_summaries(tenant_id=tenant_id):
        if not v.single_source_exposure or v.vendor not in vendors_used:
            continue
        add(
            f"vendor:{v.vendor}",
            title=f"Single-source: {v.vendor}",
            detail=f"{v.category} · no approved alternative · ${v.annual_spend_usd:,.0f} annual spend",
            severity="medium",
            category="vendor",
            process_stage="award",
            href=f"/vendors/{v.vendor}",
        )

    rfqs = {r.rfq_no: r for r in list_rfqs(tenant_id=tenant_id) if r.project_id == project_id}
    for a in list_approvals(tenant_id):
        if a.status != "pending":
            continue
        rfq_no = (a.payload or {}).get("rfq_no")
        on_project = False
        if rfq_no and rfq_no in rfqs:
            on_project = True
        if not on_project:
            continue
        add(
            f"approval:{a.approval_id}",
            title=f"Approval needed: {a.title}",
            detail=a.summary,
            severity="high",
            category="approval",
            process_stage="award",
            href="/approvals",
        )

    now = _now()
    with _lock:
        for key, kwargs in pending:
            _upsert_live(
                tenant_id=tenant_id,
                project_id=project_id,
                signal_key=key,
                **kwargs,
            )
        for r in list(_risks.get(tenant_id, {}).values()):
            if r.project_id != project_id or r.source != "live":
                continue
            if r.signal_key in seen or not r.live:
                continue
            if not commercial_ok and (
                r.category == "commercial"
                or (r.signal_key or "").startswith("commercial:")
            ):
                continue
            r.live = False
            r.updated_at = now
            _risks[tenant_id][r.risk_id] = r
    _flush()


@invalidates_cache
def create_manual(project_id: str, tenant_id: str, req: CreateManagedRiskRequest) -> ManagedRisk:
    now = _now()
    with _lock:
        risk = ManagedRisk(
            risk_id=_next_id(),
            tenant_id=tenant_id,
            project_id=project_id,
            signal_key=None,
            source="manual",
            live=False,
            title=req.title,
            detail=req.detail,
            severity=req.severity,
            category=req.category,
            process_stage=req.process_stage,
            href=req.href,
            owner=req.owner,
            mitigation=req.mitigation,
            created_at=now,
            updated_at=now,
        )
        _risks.setdefault(risk.tenant_id, {})[risk.risk_id] = risk
    _flush()
    return risk


@invalidates_cache
def patch_risk(tenant_id: str, risk_id: str, req: PatchManagedRiskRequest) -> Optional[ManagedRisk]:
    with _lock:
        risk = _risks.get(tenant_id, {}).get(risk_id)
        if risk is None:
            return None
        if req.status is not None:
            risk.status = req.status
        if req.owner is not None:
            risk.owner = req.owner
        if req.mitigation is not None:
            risk.mitigation = req.mitigation
        risk.updated_at = _now()
    _flush()
    return risk


def dump() -> dict:
    with _lock:
        return {
            "counter": dict(_counter),
            "risks": {
                tid: {rid: r.model_dump(mode="json") for rid, r in bucket.items()}
                for tid, bucket in _risks.items()
            },
        }


def load(data: dict) -> None:
    with _lock:
        _risks.clear()
        for tid, bucket in (data.get("risks") or {}).items():
            _risks[tid] = {rid: ManagedRisk.model_validate(r) for rid, r in bucket.items()}
        saved = data.get("counter") or {}
        _counter["risk"] = int(saved.get("risk", 0))


def reset() -> None:
    """Test helper."""
    with _lock:
        _risks.clear()
        _counter["risk"] = 0
