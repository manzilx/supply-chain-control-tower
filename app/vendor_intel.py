"""Vendor Intelligence module.

Computes multi-dimension scorecards, concentration analysis, and suggests
alternates. Reads supplier data from the demo scenario for now; once the app
supports persistent vendor masters this module will read from storage instead.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional

from .sample_data import build_demo_request
from .schemas import (
    CategoryConcentration,
    Grade,
    ScoreDimension,
    ScorecardComponent,
    SupplierRecord,
    VendorAlternate,
    VendorScorecard,
    VendorSummary,
)


WEIGHTS: Dict[ScoreDimension, float] = {
    "delivery": 0.25,
    "quality": 0.20,
    "price": 0.15,
    "responsiveness": 0.15,
    "claims": 0.10,
    "risk": 0.15,
}


DIMENSION_LABEL: Dict[ScoreDimension, str] = {
    "delivery": "Delivery",
    "quality": "Quality",
    "price": "Price",
    "responsiveness": "Responsiveness",
    "claims": "Claims",
    "risk": "Risk",
}


def _grade(score: int) -> Grade:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 45:
        return "D"
    return "F"


def _clamp(x: float, lo: float = 0, hi: float = 100) -> int:
    return int(max(lo, min(hi, x)))


# --- Per-dimension scoring ---------------------------------------------------


def _score_delivery(s: SupplierRecord) -> ScorecardComponent:
    # 100% OTD = 100, 80% OTD = 40, linearly
    score = _clamp((s.on_time_delivery_pct - 80) * 5 + 50)
    note = (
        "On time — keep momentum."
        if s.on_time_delivery_pct >= 95
        else "Below operating threshold; schedule recovery review."
        if s.on_time_delivery_pct < 90
        else "Acceptable but watch trend."
    )
    return ScorecardComponent(
        dimension="delivery",
        score=score,
        grade=_grade(score),
        label=DIMENSION_LABEL["delivery"],
        value=f"{s.on_time_delivery_pct:.0f}% OTD",
        note=note,
    )


def _score_quality(s: SupplierRecord) -> ScorecardComponent:
    # 0 ppm = 100, 1000 ppm = 75, 3000 ppm = 30, 5000+ = 0
    if s.quality_ppm <= 250:
        score = 100
    elif s.quality_ppm <= 1000:
        score = 75 + (1000 - s.quality_ppm) * 25 / 750
    elif s.quality_ppm <= 3000:
        score = 30 + (3000 - s.quality_ppm) * 45 / 2000
    else:
        score = max(0, 30 - (s.quality_ppm - 3000) / 100)
    score = _clamp(score)
    note = (
        "World-class quality (<250 PPM)."
        if s.quality_ppm <= 250
        else "Within tolerance; monitor NCR trend."
        if s.quality_ppm <= 1000
        else "Escapes above target — audit needed."
    )
    return ScorecardComponent(
        dimension="quality",
        score=score,
        grade=_grade(score),
        label=DIMENSION_LABEL["quality"],
        value=f"{s.quality_ppm} PPM",
        note=note,
    )


def _score_price(s: SupplierRecord, spend_by_category: Dict[str, float]) -> ScorecardComponent:
    # Heuristic: cost-competitiveness inferred from spend share in category.
    # Lower share within category + more alternates available = more competitive signal.
    category_spend = spend_by_category.get(s.category, 0) or 1
    share = s.annual_spend_usd / category_spend
    alt_bonus = min(15, s.approved_alternatives * 7)
    score = _clamp(60 + (1 - share) * 30 + alt_bonus)
    note = (
        "Price benchmark is favourable relative to peers."
        if score >= 75
        else "Limited leverage — few alternates on file."
    )
    return ScorecardComponent(
        dimension="price",
        score=score,
        grade=_grade(score),
        label=DIMENSION_LABEL["price"],
        value=f"${s.annual_spend_usd / 1000:.0f}k spend",
        note=note,
    )


def _score_responsiveness(s: SupplierRecord) -> ScorecardComponent:
    # Proxy: fewer risk flags and decent OTD implies responsive account team.
    penalties = 10 * len(s.risk_flags)
    bonus = 10 if s.on_time_delivery_pct >= 95 else 0
    score = _clamp(80 - penalties + bonus)
    note = (
        "Account team responsive."
        if score >= 75
        else "Follow-ups slow; assign a single point of contact."
    )
    return ScorecardComponent(
        dimension="responsiveness",
        score=score,
        grade=_grade(score),
        label=DIMENSION_LABEL["responsiveness"],
        value=f"{len(s.risk_flags)} flags",
        note=note,
    )


def _score_claims(s: SupplierRecord) -> ScorecardComponent:
    # Combine quality escapes + late deliveries as proxy for claims risk.
    quality_penalty = max(0, s.quality_ppm - 500) / 40
    delivery_penalty = max(0, 95 - s.on_time_delivery_pct) * 2
    score = _clamp(95 - quality_penalty - delivery_penalty)
    note = (
        "No active claims exposure expected."
        if score >= 80
        else "Claims exposure rising; review NCR + LD history."
    )
    return ScorecardComponent(
        dimension="claims",
        score=score,
        grade=_grade(score),
        label=DIMENSION_LABEL["claims"],
        value="no open claims",
        note=note,
    )


def _score_risk(s: SupplierRecord) -> ScorecardComponent:
    penalties = 0
    reasons: List[str] = []
    if s.approved_alternatives == 0:
        penalties += 25
        reasons.append("single source")
    if s.annual_spend_usd >= 1_000_000:
        penalties += 10
        reasons.append("high spend concentration")
    penalties += min(30, 8 * len(s.risk_flags))
    score = _clamp(95 - penalties)
    note = (
        "No material supply risk flagged."
        if score >= 80
        else "Qualify alternates; high disruption impact on schedule."
    )
    return ScorecardComponent(
        dimension="risk",
        score=score,
        grade=_grade(score),
        label=DIMENSION_LABEL["risk"],
        value=", ".join(reasons) if reasons else "clean",
        note=note,
    )


def _composite(components: List[ScorecardComponent]) -> int:
    total = 0.0
    for c in components:
        total += c.score * WEIGHTS[c.dimension]
    return _clamp(total)


# --- Public helpers ----------------------------------------------------------


def _suppliers(tenant_id: Optional[str] = None) -> List[SupplierRecord]:
    """Static demo suppliers + any user-added runtime suppliers for the tenant.

    Runtime suppliers override static ones with the same name (case-insensitive).
    """
    from .vendor_store import list_runtime
    static = list(build_demo_request(tenant_id or "arcforge").suppliers)
    runtime = list_runtime(tenant_id)
    if not runtime:
        return static
    runtime_names = {s.name.strip().lower() for s in runtime}
    merged = [s for s in static if s.name.strip().lower() not in runtime_names]
    merged.extend(runtime)
    return merged


def _category_spend_map(suppliers: List[SupplierRecord]) -> Dict[str, float]:
    by_cat: Dict[str, float] = defaultdict(float)
    for s in suppliers:
        by_cat[s.category] += s.annual_spend_usd
    return dict(by_cat)


def _build_components(s: SupplierRecord, spend_by_category: Dict[str, float]) -> List[ScorecardComponent]:
    return [
        _score_delivery(s),
        _score_quality(s),
        _score_price(s, spend_by_category),
        _score_responsiveness(s),
        _score_claims(s),
        _score_risk(s),
    ]


def _alternates_for(
    target: SupplierRecord,
    suppliers: List[SupplierRecord],
    spend_by_category: Dict[str, float],
) -> List[VendorAlternate]:
    alternates: List[VendorAlternate] = []
    for peer in suppliers:
        if peer.name == target.name:
            continue
        if peer.category.lower() != target.category.lower():
            continue
        components = _build_components(peer, spend_by_category)
        score = _composite(components)
        reason_parts: List[str] = []
        if peer.on_time_delivery_pct > target.on_time_delivery_pct:
            reason_parts.append(f"{peer.on_time_delivery_pct:.0f}% OTD vs {target.on_time_delivery_pct:.0f}%")
        if peer.quality_ppm < target.quality_ppm:
            reason_parts.append(f"{peer.quality_ppm} PPM vs {target.quality_ppm}")
        if peer.lead_time_days < target.lead_time_days:
            reason_parts.append(f"{peer.lead_time_days}d lead vs {target.lead_time_days}d")
        reason = "; ".join(reason_parts) or "same category on approved list"
        alternates.append(
            VendorAlternate(
                name=peer.name,
                category=peer.category,
                country=peer.country,
                composite_score=score,
                lead_time_days=peer.lead_time_days,
                on_time_delivery_pct=peer.on_time_delivery_pct,
                reason=reason,
            )
        )
    alternates.sort(key=lambda a: a.composite_score, reverse=True)
    return alternates


def _find_supplier(name: str, tenant_id: Optional[str] = None) -> Optional[SupplierRecord]:
    for s in _suppliers(tenant_id=tenant_id):
        if s.name == name:
            return s
    return None


# --- Public API --------------------------------------------------------------


from ._cache import ttl_cache


@ttl_cache(ttl_seconds=15.0)
def list_vendor_summaries(tenant_id: Optional[str] = None) -> List[VendorSummary]:
    suppliers = _suppliers(tenant_id=tenant_id)
    spend_by_category = _category_spend_map(suppliers)
    summaries: List[VendorSummary] = []
    for s in suppliers:
        components = _build_components(s, spend_by_category)
        score = _composite(components)
        summaries.append(
            VendorSummary(
                vendor=s.name,
                category=s.category,
                country=s.country,
                composite_score=score,
                composite_grade=_grade(score),
                annual_spend_usd=s.annual_spend_usd,
                on_time_delivery_pct=s.on_time_delivery_pct,
                quality_ppm=s.quality_ppm,
                flags_count=len(s.risk_flags),
                single_source_exposure=s.approved_alternatives == 0,
            )
        )
    summaries.sort(key=lambda v: v.composite_score, reverse=True)
    return summaries


def get_vendor_scorecard(
    name: str,
    tenant_id: Optional[str] = None,
) -> Optional[VendorScorecard]:
    supplier = _find_supplier(name, tenant_id=tenant_id)
    if not supplier:
        return None
    suppliers = _suppliers(tenant_id=tenant_id)
    spend_by_category = _category_spend_map(suppliers)
    components = _build_components(supplier, spend_by_category)
    score = _composite(components)
    category_total = spend_by_category.get(supplier.category, 0) or 1
    concentration = supplier.annual_spend_usd / category_total * 100

    alternates = _alternates_for(supplier, suppliers, spend_by_category)

    return VendorScorecard(
        vendor=supplier.name,
        category=supplier.category,
        country=supplier.country,
        lead_time_days=supplier.lead_time_days,
        annual_spend_usd=supplier.annual_spend_usd,
        composite_score=score,
        composite_grade=_grade(score),
        components=components,
        flags=list(supplier.risk_flags),
        single_source_exposure=supplier.approved_alternatives == 0,
        concentration_pct=round(concentration, 1),
        approved_alternatives=supplier.approved_alternatives,
        alternates=alternates,
    )


def list_category_concentration(tenant_id: Optional[str] = None) -> List[CategoryConcentration]:
    suppliers = _suppliers(tenant_id=tenant_id)
    by_cat: Dict[str, List[SupplierRecord]] = defaultdict(list)
    for s in suppliers:
        by_cat[s.category].append(s)

    out: List[CategoryConcentration] = []
    for category, group in by_cat.items():
        total = sum(s.annual_spend_usd for s in group) or 1
        top = max(group, key=lambda s: s.annual_spend_usd)
        share_pct = top.annual_spend_usd / total * 100
        out.append(
            CategoryConcentration(
                category=category,
                vendor_count=len(group),
                total_spend_usd=round(total, 2),
                top_vendor=top.name,
                top_vendor_share_pct=round(share_pct, 1),
                single_source=len(group) == 1,
            )
        )
    out.sort(key=lambda c: c.total_spend_usd, reverse=True)
    return out


def build_vendor_briefing(name: str, tenant_id: Optional[str] = None):
    """Generate a risk briefing for a single vendor.

    Tries Grok (source='grok'); falls back to deterministic summary
    (source='deterministic'). Returns None if the vendor isn't known.
    """

    from datetime import datetime as _dt, timezone as _tz
    from .schemas import VendorBriefing
    from .llm import grok_json, is_enabled

    scorecard = get_vendor_scorecard(name, tenant_id=tenant_id)
    if not scorecard:
        return None

    request = build_demo_request(tenant_id or "arcforge")
    open_pos = [
        {
            "po": p.po_number,
            "sku": p.sku,
            "due_in_days": p.due_in_days,
            "status": p.status,
            "value_usd": p.value_usd,
        }
        for p in request.purchase_orders
        if p.supplier_name == name and p.status != "received"
    ]
    incidents = [
        {"title": i.title, "severity": i.severity, "days_open": i.days_open}
        for i in request.incidents
        if i.supplier_name == name
    ]

    if is_enabled():
        import json as _json
        context = {
            "vendor": scorecard.vendor,
            "category": scorecard.category,
            "country": scorecard.country,
            "composite_score": scorecard.composite_score,
            "composite_grade": scorecard.composite_grade,
            "annual_spend_usd": scorecard.annual_spend_usd,
            "lead_time_days": scorecard.lead_time_days,
            "flags": scorecard.flags,
            "single_source_exposure": scorecard.single_source_exposure,
            "concentration_pct": scorecard.concentration_pct,
            "approved_alternatives": scorecard.approved_alternatives,
            "alternates": [{"name": a.name, "score": a.composite_score} for a in scorecard.alternates],
            "components": [{"dim": c.dimension, "score": c.score, "note": c.note} for c in scorecard.components],
            "open_pos": open_pos,
            "incidents": incidents,
        }
        system = (
            "You are a strategic-sourcing analyst writing a 200-word risk briefing "
            "for a single vendor. Be concrete: cite scorecard numbers, flag exposure, "
            "any recent incidents or open POs of concern. End with a watchlist of "
            "3-5 specific items to monitor.\n\n"
            "Return JSON: {\"headline\": <=14-word string, "
            "\"body\": 2-3 short paragraph plain prose string, "
            "\"watchlist\": list of 3-5 short strings}"
        )
        user = (
            "Write the briefing using only this data:\n\n"
            + _json.dumps(context, default=str, indent=2)
        )
        parsed = grok_json(system, user, max_tokens=700)
        if parsed and isinstance(parsed.get("headline"), str) and isinstance(parsed.get("body"), str):
            watchlist = parsed.get("watchlist") or []
            if not isinstance(watchlist, list):
                watchlist = []
            return VendorBriefing(
                vendor=scorecard.vendor,
                headline=parsed["headline"][:140],
                body=parsed["body"],
                watchlist=[str(w) for w in watchlist][:6],
                generated_at=_dt.now(_tz.utc),
                source="grok",
            )

    # Deterministic fallback
    parts = [
        f"{scorecard.vendor} runs at composite score {scorecard.composite_score}/100 "
        f"(grade {scorecard.composite_grade}) on USD {scorecard.annual_spend_usd:,.0f} "
        f"annual spend across the {scorecard.category} category."
    ]
    if scorecard.single_source_exposure:
        parts.append(
            f"This vendor is the sole approved source for {scorecard.category} with "
            f"{scorecard.concentration_pct:.0f}% category concentration — a real continuity risk."
        )
    if scorecard.flags:
        parts.append("Active risk flags: " + ", ".join(scorecard.flags) + ".")
    if incidents:
        parts.append(f"{len(incidents)} open incident(s) on file.")
    if open_pos:
        parts.append(
            f"{len(open_pos)} open PO(s) totaling USD {sum(p['value_usd'] for p in open_pos):,.0f}."
        )

    watchlist: List[str] = []
    if scorecard.flags:
        watchlist.extend(f"Track flag: {f}" for f in scorecard.flags[:3])
    if scorecard.single_source_exposure:
        watchlist.append("Identify and qualify a second source for this category")
    if any(p["due_in_days"] <= 14 for p in open_pos):
        watchlist.append("Tighten expediting on POs due within 14 days")
    if not watchlist:
        watchlist = ["Quarterly performance review", "Annual capacity confirmation"]

    return VendorBriefing(
        vendor=scorecard.vendor,
        headline=(
            f"{scorecard.vendor} — grade {scorecard.composite_grade}, "
            f"{'single-source' if scorecard.single_source_exposure else 'multi-source'}"
        ),
        body="\n\n".join(parts),
        watchlist=watchlist[:6],
        generated_at=_dt.now(_tz.utc),
        source="deterministic",
    )
