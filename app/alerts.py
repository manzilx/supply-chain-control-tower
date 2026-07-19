"""Live alert feed for the control tower.

Synthesises a single tenant-scoped, severity-ranked alert list from signals
that already exist across modules — what a control tower exists to surface:

  * pending approvals awaiting the user's decision (PO, award, quote, vendor onboarding)
  * milestones at risk in the next 30 days
  * single-source vendor exposure
  * projects trending over budget
  * expediting escalations (high slip probability)
  * BOM lines still missing specifications on near-term milestones

Read-only + cached. Each alert carries an href so the UI can deep-link.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import List, Optional

from ._cache import ttl_cache
from .schemas import Alert, AlertFeed, User


_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> date:
    return date.today()


def build_alert_feed(user: User) -> AlertFeed:
    """Entry point. The feed content depends only on the tenant and whether
    the viewer can decide approvals — NOT on their identity — so we key the
    cache on (tenant_id, can_decide). Two buyers in the same tenant share one
    cached fan-out instead of each recomputing it every 30s poll."""
    from .auth import has_perm
    can_decide = has_perm(user.role, "approval", "decide")
    return _cached_feed(user.tenant_id, can_decide)


@ttl_cache(ttl_seconds=10.0)
def _cached_feed(tenant_id: str, can_decide: bool) -> AlertFeed:
    from . import approvals
    from .planning import compute_project_progress, get_bom, list_projects
    from .commercial import build_commercial_summary
    from .expediting import build_expedite_queue
    from .vendor_intel import list_vendor_summaries

    alerts: List[Alert] = []
    today = _today()
    n = 0

    def add(severity: str, category: str, title: str, detail: str, href: str) -> None:
        nonlocal n
        n += 1
        alerts.append(
            Alert(
                alert_id=f"AL-{n:04d}",
                severity=severity,  # type: ignore[arg-type]
                category=category,
                title=title,
                detail=detail,
                href=href,
            )
        )

    # 1. Pending approvals (only if this viewer can act on them)
    if can_decide:
        pend = [a for a in approvals.list_approvals(tenant_id) if a.status == "pending"]
        for a in pend[:6]:
            add("high", "approval", f"Approval needed: {a.title}", a.summary, "/approvals")

    projects = list_projects(tenant_id=tenant_id)

    # 2. At-risk + imminent milestones
    for p in projects:
        prog = compute_project_progress(p.project_id, tenant_id=tenant_id)
        for m in p.milestones:
            days = (m.required_on_site_date - today).days
            if 0 <= days <= 30:
                behind = prog is not None and (
                    (prog.bom_delivered_pct + prog.spend_committed_pct) / 2 + 15 < prog.milestones_pct
                )
                if days <= 14 or behind:
                    sev = "critical" if days <= 7 else "high" if days <= 14 else "medium"
                    add(
                        sev, "schedule",
                        f"{m.code} {m.name} — {p.name}",
                        f"Required on site in {days}d"
                        + (" · physical progress lagging schedule" if behind else ""),
                        f"/projects/{p.project_id}",
                    )

    # 3. Single-source vendor exposure
    vendors = list_vendor_summaries(tenant_id=tenant_id)
    ss = [v for v in vendors if v.single_source_exposure]
    for v in ss[:4]:
        add(
            "medium", "vendor",
            f"Single-source exposure: {v.vendor}",
            f"{v.category} · no approved alternative · ${v.annual_spend_usd:,.0f} annual spend",
            f"/vendors/{v.vendor}",
        )

    # 4. Budget overruns
    try:
        commercial = build_commercial_summary(tenant_id=tenant_id)
        for line in commercial.top_overruns[:3]:
            if line.variance_pct > 5:
                add(
                    "high" if line.variance_pct > 15 else "medium", "commercial",
                    f"Over budget: {line.code}",
                    f"+{line.variance_pct:.0f}% variance on {line.code}",
                    "/commercial",
                )
    except Exception:  # noqa: BLE001
        pass

    # 5. Expediting escalations
    try:
        queue = build_expedite_queue(tenant_id=tenant_id)
        for item in queue.items:
            if item.urgency == "escalate":
                add(
                    "critical", "expediting",
                    f"Escalate {item.po_number} · {item.supplier_name}",
                    f"{item.slip_probability_pct}% slip probability, {item.predicted_slip_days}d expected slip",
                    "/expediting",
                )
    except Exception:  # noqa: BLE001
        pass

    # 6. Missing specs on near-term milestones
    spec_gaps = 0
    for p in projects:
        ms_dates = {m.code: m.required_on_site_date for m in p.milestones}
        for b in get_bom(p.project_id, tenant_id=tenant_id):
            if b.status == "spec_missing" and b.milestone_code in ms_dates:
                days = (ms_dates[b.milestone_code] - today).days
                if 0 <= days <= 45:
                    spec_gaps += 1
    if spec_gaps:
        add(
            "medium", "engineering",
            f"{spec_gaps} BOM line(s) missing specs on near-term milestones",
            "Issue spec requests to engineering to protect the procurement runway.",
            "/projects",
        )

    alerts.sort(key=lambda a: _SEVERITY_RANK.get(a.severity, 9))
    counts: dict[str, int] = {}
    for a in alerts:
        counts[a.severity] = counts.get(a.severity, 0) + 1

    return AlertFeed(
        generated_at=_now(),
        total=len(alerts),
        counts=counts,
        alerts=alerts,
    )
