"""Commercial module.

Rolls budget vs quoted vs awarded vs final-PO values across all projects,
project-by-project, with savings and variance highlights.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .planning import list_projects
from .schemas import (
    CommercialLine,
    CommercialSummary,
    ProjectCommercialSummary,
)
from .sourcing import (
    get_quotes,
    list_awards,
    list_pos as list_sourcing_pos,
    list_prs,
    list_rfqs,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _pct(numerator: float, denom: float) -> float:
    if not denom:
        return 0.0
    return round(numerator / denom * 100, 1)


from ._cache import ttl_cache


@ttl_cache(ttl_seconds=10.0)
def build_commercial_lines(tenant_id: Optional[str] = None) -> List[CommercialLine]:
    prs = list_prs(tenant_id=tenant_id)
    rfqs_by_pr: Dict[str, str] = {p.pr_no: p.rfq_no for p in prs if p.rfq_no}
    awards_by_pr: Dict[str, str] = {a.pr_no: a.award_id for a in list_awards(tenant_id=tenant_id)}
    pos_by_pr: Dict[str, float] = {p.pr_no: p.value_usd for p in list_sourcing_pos(tenant_id=tenant_id)}
    rfqs = {r.rfq_no: r for r in list_rfqs(tenant_id=tenant_id)}

    lines: List[CommercialLine] = []
    for pr in prs:
        budget = pr.budget_value_usd
        quoted_min: Optional[float] = None
        awarded: Optional[float] = None
        final_po: Optional[float] = pos_by_pr.get(pr.pr_no)

        rfq_no = rfqs_by_pr.get(pr.pr_no)
        if rfq_no:
            quotes = get_quotes(rfq_no, tenant_id=tenant_id)
            if quotes:
                quoted_min = min(q.total_usd for q in quotes)

        if pr.award_id:
            for award in list_awards(tenant_id=tenant_id):
                if award.award_id == pr.award_id:
                    awarded = award.awarded_value_usd
                    break

        reference = final_po or awarded or quoted_min
        savings = 0.0
        variance = 0.0
        if budget and reference is not None:
            savings = round(budget - reference, 2)
            variance = _pct(reference - budget, budget)

        state: str = "budget_only"
        if final_po is not None:
            state = "awarded"
        elif awarded is not None:
            state = "awarded"
        elif quoted_min is not None:
            state = "quoted"

        lines.append(
            CommercialLine(
                ref_id=pr.pr_no,
                tenant_id=pr.tenant_id,
                project_id=pr.project_id,
                code=pr.code,
                description=pr.description,
                vendor=None,  # fill below
                budget_value_usd=budget,
                quoted_value_usd=quoted_min,
                awarded_value_usd=awarded,
                final_po_value_usd=final_po,
                savings_usd=savings,
                variance_pct=variance,
                state=state,  # type: ignore[arg-type]
            )
        )

    # Fill vendor from PO when present
    po_vendor_by_pr: Dict[str, str] = {p.pr_no: p.vendor for p in list_sourcing_pos(tenant_id=tenant_id)}
    for line in lines:
        if line.ref_id in po_vendor_by_pr:
            line.vendor = po_vendor_by_pr[line.ref_id]

    return lines


def build_commercial_summary(tenant_id: Optional[str] = None) -> CommercialSummary:
    lines = build_commercial_lines(tenant_id=tenant_id)
    projects = {p.project_id: p for p in list_projects(tenant_id=tenant_id)}

    by_project: Dict[str, List[CommercialLine]] = defaultdict(list)
    for line in lines:
        by_project[line.project_id].append(line)

    project_summaries: List[ProjectCommercialSummary] = []
    total_budget = 0.0
    total_awarded = 0.0
    total_savings = 0.0

    for project_id, group in by_project.items():
        project = projects.get(project_id)
        budget = sum((l.budget_value_usd or 0) for l in group)
        quoted = sum((l.quoted_value_usd or 0) for l in group)
        awarded = sum((l.awarded_value_usd or l.final_po_value_usd or 0) for l in group)
        savings = sum(l.savings_usd for l in group if l.savings_usd > 0)
        over_budget = sum(1 for l in group if l.variance_pct > 0)

        project_summaries.append(
            ProjectCommercialSummary(
                project_id=project_id,
                project_name=project.name if project else project_id,
                line_count=len(group),
                total_budget_usd=round(budget, 2),
                total_quoted_usd=round(quoted, 2),
                total_awarded_usd=round(awarded, 2),
                total_savings_usd=round(savings, 2),
                savings_pct=_pct(savings, budget),
                variance_pct=_pct(awarded - budget, budget),
                over_budget_lines=over_budget,
            )
        )

        total_budget += budget
        total_awarded += awarded
        total_savings += savings

    project_summaries.sort(key=lambda s: s.total_budget_usd, reverse=True)

    top_savings = sorted(
        [l for l in lines if l.savings_usd > 0], key=lambda l: l.savings_usd, reverse=True
    )[:5]
    top_overruns = sorted(
        [l for l in lines if l.variance_pct > 0], key=lambda l: l.variance_pct, reverse=True
    )[:5]

    return CommercialSummary(
        generated_at=_now(),
        total_budget_usd=round(total_budget, 2),
        total_awarded_usd=round(total_awarded, 2),
        total_savings_usd=round(total_savings, 2),
        savings_pct=_pct(total_savings, total_budget),
        projects=project_summaries,
        top_savings=top_savings,
        top_overruns=top_overruns,
    )


def get_project_commercials(
    project_id: str,
    tenant_id: Optional[str] = None,
) -> List[CommercialLine]:
    return [
        l for l in build_commercial_lines(tenant_id=tenant_id)
        if l.project_id == project_id
    ]
