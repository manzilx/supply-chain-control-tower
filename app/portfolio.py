"""Tenant portfolio aggregations.

Powers the executive cockpit at /overview. Pulls real tenant data
(projects, BOM, sourcing, audit) into one structured summary so the
dashboard renders with a single round-trip.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from ._cache import ttl_cache
from .audit import _events  # type: ignore[attr-defined]
from .planning import compute_project_progress, get_bom, list_projects
from .schemas import (
    BOMItem,
    Milestone,
    PortfolioActivity,
    PortfolioCompletionBucket,
    PortfolioCounts,
    PortfolioSchedule,
    PortfolioScheduleItem,
    PortfolioSpend,
    PortfolioSummary,
    Project,
    ProjectProgress,
)
from .sourcing import list_pos, list_prs, list_rfqs


def _today() -> date:
    return date.today()


def _bucket(pct: float) -> str:
    if pct >= 70:
        return "executing"
    if pct >= 25:
        return "in_progress"
    if pct > 0:
        return "kickoff"
    return "planned"


def _next_milestone(ms: List[Milestone], today: date) -> Optional[Milestone]:
    future = sorted(
        [m for m in ms if m.required_on_site_date >= today],
        key=lambda m: m.required_on_site_date,
    )
    return future[0] if future else None


def _is_at_risk(progress: ProjectProgress, next_ms: Optional[Milestone], today: date) -> bool:
    """A project is at-risk if its next milestone is <30 days away AND its
    physical/spend completion is meaningfully behind schedule."""
    if next_ms is None:
        return False
    days = (next_ms.required_on_site_date - today).days
    if days > 30:
        return False
    # Behind = bom delivered + spend committed average lags milestones passed by ≥15 pts
    physical_avg = (progress.bom_delivered_pct + progress.spend_committed_pct) / 2
    return physical_avg + 15 < progress.milestones_pct + (60 if days <= 14 else 0)


@ttl_cache(ttl_seconds=10.0)
def build_portfolio_summary(tenant_id: Optional[str] = None) -> PortfolioSummary:
    today = _today()
    horizon = today + timedelta(days=14)

    projects = list_projects(tenant_id=tenant_id)
    progress_by_id = {
        p.project_id: compute_project_progress(p.project_id, tenant_id=tenant_id)
        for p in projects
    }
    # Filter out None just in case
    progress_list: List[ProjectProgress] = [v for v in progress_by_id.values() if v is not None]

    # --- Counts ---
    bom_total = sum(len(get_bom(p.project_id, tenant_id=tenant_id)) for p in projects)
    prs = list_prs(tenant_id=tenant_id)
    rfqs = list_rfqs(tenant_id=tenant_id)
    pos = list_pos(tenant_id=tenant_id)
    counts = PortfolioCounts(
        projects=len(projects),
        bom_lines=bom_total,
        prs=len(prs),
        rfqs=len(rfqs),
        pos=len(pos),
    )

    # --- Completion summary ---
    if progress_list:
        avg = round(sum(p.completion_pct for p in progress_list) / len(progress_list), 1)
    else:
        avg = 0.0
    bucket_counter = Counter(_bucket(p.completion_pct) for p in progress_list)
    buckets = [
        PortfolioCompletionBucket(label="Executing (≥70%)", count=bucket_counter.get("executing", 0)),
        PortfolioCompletionBucket(label="In progress (25-70%)", count=bucket_counter.get("in_progress", 0)),
        PortfolioCompletionBucket(label="Kickoff (<25%)", count=bucket_counter.get("kickoff", 0)),
        PortfolioCompletionBucket(label="Planning (0%)", count=bucket_counter.get("planned", 0)),
    ]

    # --- Spend ---
    total_budget = sum(p.budget_value_usd for p in progress_list)
    total_committed = sum(p.committed_value_usd for p in progress_list)
    awarded_value = sum(po.value_usd for po in pos)
    committed_pct = (total_committed / total_budget * 100) if total_budget else 0.0
    spend = PortfolioSpend(
        total_budget_usd=round(total_budget, 2),
        total_committed_usd=round(total_committed, 2),
        total_awarded_usd=round(awarded_value, 2),
        committed_pct=round(committed_pct, 1),
        open_prs=sum(1 for pr in prs if pr.status in {"draft", "rfq_issued", "quoted"}),
    )

    # --- Schedule: top at-risk + next milestones ---
    at_risk_items: List[PortfolioScheduleItem] = []
    upcoming_items: List[PortfolioScheduleItem] = []
    for p in projects:
        prog = progress_by_id.get(p.project_id)
        if prog is None:
            continue
        next_ms = _next_milestone(p.milestones, today)
        if next_ms is None:
            continue
        days = (next_ms.required_on_site_date - today).days
        item = PortfolioScheduleItem(
            project_id=p.project_id,
            project_name=p.name,
            milestone_code=next_ms.code,
            milestone_name=next_ms.name,
            required_on_site_date=next_ms.required_on_site_date,
            days_until=days,
            completion_pct=prog.completion_pct,
            at_risk=_is_at_risk(prog, next_ms, today),
        )
        if item.at_risk:
            at_risk_items.append(item)
        if next_ms.required_on_site_date <= horizon:
            upcoming_items.append(item)
    at_risk_items.sort(key=lambda x: (x.days_until, -x.completion_pct))
    upcoming_items.sort(key=lambda x: x.days_until)
    schedule = PortfolioSchedule(
        at_risk=at_risk_items[:5],
        upcoming_14d=upcoming_items[:8],
    )

    # --- Activity feed (tenant-scoped audit events) ---
    activities: List[PortfolioActivity] = []
    for ev in reversed(list(_events)):  # newest first
        if tenant_id is not None and ev.tenant_id != tenant_id:
            continue
        activities.append(
            PortfolioActivity(
                at=ev.occurred_at,
                action=ev.action,
                entity_kind=ev.entity_kind,
                subject=ev.subject,
                summary=ev.summary,
                project_id=ev.project_id,
            )
        )
        if len(activities) >= 12:
            break

    return PortfolioSummary(
        generated_at=datetime.now(timezone.utc),
        counts=counts,
        average_completion_pct=avg,
        completion_buckets=buckets,
        spend=spend,
        schedule=schedule,
        activity=activities,
    )
