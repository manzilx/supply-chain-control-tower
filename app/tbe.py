"""Technical Bid Evaluation (TBE) — qualitative scoring alongside the
commercial quote comparison.

Real EPC procurement evaluates bids on two axes:

  Commercial (TQE_C): price, lead time, payment terms, vendor reliability
  Technical  (TQE_T): spec compliance, scope of supply, materials, performance,
                     warranty, QA/QC, documentation, experience

This module owns the technical side and the combined ranking. Commercial
scores still come from sourcing.compare_quotes; we blend them here with a
configurable weight (default 60/40 commercial/technical).

In-memory store mirrors the rest of the app — per-RFQ state, no DB.
"""

from __future__ import annotations

import json as _json
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .schemas import (
    CombinedEvaluation,
    CriterionScore,
    QuoteComparison,
    SetCriteriaRequest,
    SetTechnicalEvaluationRequest,
    SetWeightsRequest,
    TBE,
    TechnicalCriterion,
    TechnicalEvaluation,
)


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


_criteria_by_rfq: Dict[str, List[TechnicalCriterion]] = {}
_evaluations: Dict[str, Dict[str, TechnicalEvaluation]] = {}  # rfq_no → quote_id → eval
_weights: Dict[str, tuple[float, float]] = {}  # rfq_no → (commercial, technical)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Criteria templates — auto-picked from RFQ description keywords
# ---------------------------------------------------------------------------


_CATEGORY_KEYWORDS: list[tuple[str, list[str]]] = [
    ("forged_valve",  ["valve", "gate valve", "globe valve", "check valve", "forged"]),
    ("pump",          ["pump", "bfp", "boiler feed", "centrifugal", "cw pump"]),
    ("transformer",   ["transformer", "txf", "mva", "11 kv", "33 kv", "220 kv"]),
    ("plc",           ["plc", "io module", "rtu", "controller"]),
    ("switchgear",    ["switchgear", "gis", "mcc", "panel", "vcb"]),
    ("turbine",       ["turbine", "runner", "wicket", "spiral case", "draft tube"]),
    ("generator",     ["generator", "stator", "rotor", "alternator"]),
    ("cable",         ["cable", "busbar", "xlpe", "lt cable", "ht cable"]),
    ("structural",    ["structural steel", "rebar", "tmt", "fabrication"]),
    ("crane",         ["crane", "eot", "bridge crane", "hoist"]),
    ("instruments",   ["transmitter", "rtd", "thermocouple", "sensor", "instrument"]),
    ("cooling_tower", ["cooling tower", "ct module", "fan", "drift"]),
    ("condenser",     ["condenser", "tube", "inconel", "shell tube"]),
    ("civil",         ["cement", "concrete", "aggregate", "fly ash"]),
    ("hydromech",     ["gate", "stop log", "trash rack", "penstock"]),
    ("hvac",          ["hvac", "ahu", "chiller", "precision ac"]),
    ("fire",          ["fire", "co2", "deluge", "fdas", "fm200"]),
]


def _detect_category(description: str) -> str:
    d = (description or "").lower()
    for cat, keys in _CATEGORY_KEYWORDS:
        if any(k in d for k in keys):
            return cat
    return "generic"


_DEFAULT_CRITERIA: Dict[str, List[TechnicalCriterion]] = {
    "forged_valve": [
        TechnicalCriterion(criterion_id="C01", name="Materials of construction", description="Conformance to specified body / trim / seat / stem materials (e.g. ASTM A105 + 13Cr trim)", category="materials", weight=0.20, mandatory=True),
        TechnicalCriterion(criterion_id="C02", name="Pressure class & dimensional std", description="ASME B16.34 / B16.10 / API 6D compliance", category="spec_compliance", weight=0.15, mandatory=True),
        TechnicalCriterion(criterion_id="C03", name="NDE & testing", description="Hydrostatic, seat leak, radiographic / ultrasonic per spec", category="quality", weight=0.15),
        TechnicalCriterion(criterion_id="C04", name="Fire-safe + anti-static", description="API 607 / API 6FA + anti-static device compliance", category="performance", weight=0.10),
        TechnicalCriterion(criterion_id="C05", name="QAP / ITP", description="Quality Assurance Plan + Inspection Test Plan submitted and accepted", category="documentation", weight=0.10),
        TechnicalCriterion(criterion_id="C06", name="Manufacturing experience", description="Number of similar valves supplied in last 3 years; reference projects", category="experience", weight=0.10),
        TechnicalCriterion(criterion_id="C07", name="Warranty + spares", description="Minimum 18-month warranty; spares list and pricing included", category="warranty", weight=0.10),
        TechnicalCriterion(criterion_id="C08", name="Scope completeness", description="Valves + actuators + manuals + commissioning spares included as required", category="scope_of_supply", weight=0.10),
    ],
    "pump": [
        TechnicalCriterion(criterion_id="C01", name="Performance curve (Q-H, NPSHr, η)", description="Performance at duty point matches spec within +/- 3%", category="performance", weight=0.20, mandatory=True),
        TechnicalCriterion(criterion_id="C02", name="Materials of construction", description="Casing, impeller, shaft, wear ring per spec; corrosion allowance", category="materials", weight=0.15, mandatory=True),
        TechnicalCriterion(criterion_id="C03", name="Hydraulic testing", description="Hydrostatic + performance test per HI / ISO 9906 Grade", category="quality", weight=0.12),
        TechnicalCriterion(criterion_id="C04", name="Seals & bearings", description="Mechanical seal selection, bearing rating + monitoring", category="performance", weight=0.10),
        TechnicalCriterion(criterion_id="C05", name="Driver & coupling", description="Motor sizing, IE class, coupling guard, base plate", category="scope_of_supply", weight=0.10),
        TechnicalCriterion(criterion_id="C06", name="QAP + FAT witness", description="QAP submitted; FAT witness offered to client/TPI", category="quality", weight=0.10),
        TechnicalCriterion(criterion_id="C07", name="Warranty + commissioning support", description="Warranty period; on-site commissioning engineer; training", category="warranty", weight=0.10),
        TechnicalCriterion(criterion_id="C08", name="Reference list (3 yrs)", description="Similar pumps supplied to similar projects in last 3 years", category="experience", weight=0.08),
        TechnicalCriterion(criterion_id="C09", name="Spares & special tools", description="Recommended 2-yr operational spares + special tools included", category="spares_service", weight=0.05),
    ],
    "transformer": [
        TechnicalCriterion(criterion_id="C01", name="Rating, vector group, taps", description="MVA / voltage ratio / vector group / OLTC range per spec", category="spec_compliance", weight=0.18, mandatory=True),
        TechnicalCriterion(criterion_id="C02", name="Insulation & cooling", description="Insulation class, BIL, cooling type (ONAN/ONAF), top-oil rise", category="performance", weight=0.15),
        TechnicalCriterion(criterion_id="C03", name="Losses (no-load + load)", description="Guaranteed losses at rated load; penalty / reward structure", category="performance", weight=0.15),
        TechnicalCriterion(criterion_id="C04", name="Materials (core, winding)", description="Grain-oriented silicon steel; copper conductor; oil type", category="materials", weight=0.12),
        TechnicalCriterion(criterion_id="C05", name="Type tests (impulse, short-circuit)", description="Type-test certificates from accredited lab", category="quality", weight=0.10),
        TechnicalCriterion(criterion_id="C06", name="Routine tests + FAT", description="Full routine test schedule per IEC 60076; FAT witness offered", category="quality", weight=0.10),
        TechnicalCriterion(criterion_id="C07", name="Bushings, OLTC, accessories", description="Bushing make/class, OLTC make, Buchholz, PRD, RTD", category="scope_of_supply", weight=0.08),
        TechnicalCriterion(criterion_id="C08", name="Reference & track record", description="MVA-equivalent transformers supplied to similar utilities", category="experience", weight=0.07),
        TechnicalCriterion(criterion_id="C09", name="Warranty + spares", description="Warranty period; mandatory + recommended spares list", category="warranty", weight=0.05),
    ],
    "plc": [
        TechnicalCriterion(criterion_id="C01", name="I/O density + redundancy", description="I/O count, hot-standby CPU, redundant power", category="spec_compliance", weight=0.18, mandatory=True),
        TechnicalCriterion(criterion_id="C02", name="Communication protocols", description="Modbus TCP / IEC 61850 / Profinet support per spec", category="spec_compliance", weight=0.15),
        TechnicalCriterion(criterion_id="C03", name="Environmental rating", description="Operating temp, humidity, vibration, EMC class", category="performance", weight=0.12),
        TechnicalCriterion(criterion_id="C04", name="Software & licensing", description="Engineering software, runtime, license type", category="scope_of_supply", weight=0.10),
        TechnicalCriterion(criterion_id="C05", name="Cybersecurity", description="IEC 62443 / NERC CIP compliance level", category="performance", weight=0.10),
        TechnicalCriterion(criterion_id="C06", name="Documentation", description="System architecture, I/O list, P&IDs, manuals", category="documentation", weight=0.10),
        TechnicalCriterion(criterion_id="C07", name="Service support", description="Local service centre, response time SLA, training", category="spares_service", weight=0.10),
        TechnicalCriterion(criterion_id="C08", name="Reference installations", description="Similar plant-scale installations in last 5 years", category="experience", weight=0.08),
        TechnicalCriterion(criterion_id="C09", name="Warranty & obsolescence", description="Warranty period; obsolescence policy + lifecycle commitment", category="warranty", weight=0.07),
    ],
    "switchgear": [
        TechnicalCriterion(criterion_id="C01", name="Rated current + short-circuit", description="Continuous current, short-circuit withstand kA / sec", category="spec_compliance", weight=0.18, mandatory=True),
        TechnicalCriterion(criterion_id="C02", name="Type tests (IEC 62271)", description="Type-test certificates from accredited lab; arc-flash class", category="quality", weight=0.15),
        TechnicalCriterion(criterion_id="C03", name="Protection scheme", description="Numerical relays make/model; communication; differential / distance scheme", category="performance", weight=0.15),
        TechnicalCriterion(criterion_id="C04", name="Insulation & gas (GIS only)", description="SF6 gas pressure / monitoring / low-pressure interlock", category="performance", weight=0.10),
        TechnicalCriterion(criterion_id="C05", name="Auxiliaries & wiring", description="LCC, CT/VT, AC/DC supplies, anti-condensation heaters", category="scope_of_supply", weight=0.10),
        TechnicalCriterion(criterion_id="C06", name="FAT + routine tests", description="FAT witness offered; routine test reports per panel", category="quality", weight=0.10),
        TechnicalCriterion(criterion_id="C07", name="Reference list (utility)", description="Similar voltage / current panels in operation > 3 years", category="experience", weight=0.10),
        TechnicalCriterion(criterion_id="C08", name="Spares & training", description="Mandatory spares; operator training; commissioning support", category="spares_service", weight=0.07),
        TechnicalCriterion(criterion_id="C09", name="Warranty", description="Warranty period; extended-warranty option", category="warranty", weight=0.05),
    ],
    "generic": [
        TechnicalCriterion(criterion_id="C01", name="Specification compliance", description="Conformance to the technical specification, clause by clause", category="spec_compliance", weight=0.25, mandatory=True),
        TechnicalCriterion(criterion_id="C02", name="Scope of supply completeness", description="All items in the scope are included; no exclusions on critical scope", category="scope_of_supply", weight=0.15),
        TechnicalCriterion(criterion_id="C03", name="Materials of construction", description="Materials per spec; corrosion allowances; certification", category="materials", weight=0.15),
        TechnicalCriterion(criterion_id="C04", name="Quality assurance (QAP/ITP/FAT)", description="QAP + ITP submitted; FAT witness offered; test certificates", category="quality", weight=0.15),
        TechnicalCriterion(criterion_id="C05", name="Documentation", description="Drawings, datasheets, manuals, GA, P&ID, calculation reports", category="documentation", weight=0.10),
        TechnicalCriterion(criterion_id="C06", name="Warranty + spares", description="Warranty period; spares list and pricing", category="warranty", weight=0.10),
        TechnicalCriterion(criterion_id="C07", name="Experience + references", description="Similar projects in last 3-5 years; references contactable", category="experience", weight=0.10),
    ],
}


def suggest_criteria(description: str) -> List[TechnicalCriterion]:
    cat = _detect_category(description)
    return [c.model_copy() for c in _DEFAULT_CRITERIA.get(cat, _DEFAULT_CRITERIA["generic"])]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_criteria(rfq_no: str, description: str = "") -> List[TechnicalCriterion]:
    """Return criteria for an RFQ. If none set yet, auto-pick a template."""

    if rfq_no in _criteria_by_rfq:
        return list(_criteria_by_rfq[rfq_no])
    criteria = suggest_criteria(description)
    _criteria_by_rfq[rfq_no] = criteria
    return criteria


def set_criteria(rfq_no: str, criteria: List[TechnicalCriterion]) -> List[TechnicalCriterion]:
    # Normalise weights to sum to 1.0 if user didn't
    total = sum(c.weight for c in criteria) or 1.0
    if abs(total - 1.0) > 0.001:
        for c in criteria:
            c.weight = round(c.weight / total, 4)
    _criteria_by_rfq[rfq_no] = list(criteria)
    return _criteria_by_rfq[rfq_no]


def list_evaluations(rfq_no: str) -> List[TechnicalEvaluation]:
    return list((_evaluations.get(rfq_no) or {}).values())


def set_evaluation(
    rfq_no: str,
    quote_id: str,
    vendor: str,
    scores: List[CriterionScore],
    notes: str = "",
    evaluated_by: str = "Control Tower",
    source: str = "manual",
) -> TechnicalEvaluation:
    criteria = _criteria_by_rfq.get(rfq_no) or []
    weighted, disqualified, dq_reason = _compute_technical_score(criteria, scores)
    grade = _grade_for(weighted)
    ev = TechnicalEvaluation(
        rfq_no=rfq_no,
        quote_id=quote_id,
        vendor=vendor,
        criteria_scores=scores,
        technical_score=weighted,
        technical_grade=grade,
        disqualified=disqualified,
        disqualification_reason=dq_reason,
        notes=notes,
        source=source,  # type: ignore[arg-type]
        evaluated_by=evaluated_by,
        evaluated_at=_now(),
    )
    _evaluations.setdefault(rfq_no, {})[quote_id] = ev

    # Audit
    from .audit import emit
    from .sourcing import _rfqs, _prs  # type: ignore[attr-defined]
    rfq_obj = _rfqs.get(rfq_no)
    pr_no = rfq_obj.pr_no if rfq_obj else None
    pr_obj = _prs.get(pr_no) if pr_no else None
    emit(
        action="evaluated" if source != "grok" else "ai_generated",
        entity_kind="technical_evaluation",
        entity_id=f"{rfq_no}:{quote_id}",
        subject=f"TBE · {vendor}",
        summary=(
            f"Technical evaluation for {vendor} on {rfq_no}: "
            f"score {weighted}/100 ({grade})"
            + (f" · {dq_reason}" if disqualified else "")
            + f" · source: {source}"
        ),
        actor="grok" if source == "grok" else evaluated_by,
        source="ai" if source == "grok" else "api",
        tenant_id=rfq_obj.tenant_id if rfq_obj else "",
        project_id=rfq_obj.project_id if rfq_obj else None,
        bom_item_id=pr_obj.bom_item_id if pr_obj else None,
        bom_code=rfq_obj.code if rfq_obj else None,
        pr_no=pr_no,
        rfq_no=rfq_no,
        quote_id=quote_id,
        vendor=vendor,
        metadata={
            "technical_score": weighted,
            "grade": grade,
            "disqualified": disqualified,
            "criteria_count": len(scores),
            "deviations": sum(1 for s in scores if s.compliance in {"deviation", "non_compliant"}),
        },
    )
    return ev


def _compute_technical_score(
    criteria: List[TechnicalCriterion], scores: List[CriterionScore]
) -> tuple[int, bool, Optional[str]]:
    by_id = {c.criterion_id: c for c in criteria}
    weighted = 0.0
    disqualified = False
    dq_reason: Optional[str] = None
    for s in scores:
        c = by_id.get(s.criterion_id)
        if not c:
            continue
        weighted += c.weight * s.score
        if c.mandatory and s.compliance in {"non_compliant"}:
            disqualified = True
            dq_reason = f"Non-compliant on mandatory criterion '{c.name}'"
    return int(round(min(weighted, 100))), disqualified, dq_reason


def _grade_for(score: int):  # -> Literal["A","B","C","D","F"]
    if score >= 85:
        return "A"
    if score >= 75:
        return "B"
    if score >= 65:
        return "C"
    if score >= 50:
        return "D"
    return "F"


def get_weights(rfq_no: str) -> tuple[float, float]:
    return _weights.get(rfq_no, (0.6, 0.4))


def set_weights(rfq_no: str, commercial: float, technical: float) -> tuple[float, float]:
    total = (commercial + technical) or 1.0
    commercial, technical = commercial / total, technical / total
    _weights[rfq_no] = (commercial, technical)
    return _weights[rfq_no]


# ---------------------------------------------------------------------------
# Combined ranking (commercial + technical)
# ---------------------------------------------------------------------------


def build_tbe(rfq_no: str) -> TBE:
    from .sourcing import compare_quotes, get_rfq, get_quotes

    rfq = get_rfq(rfq_no)
    quotes = get_quotes(rfq_no) if rfq else []
    description = rfq.description if rfq else ""

    criteria = get_criteria(rfq_no, description)
    tech_evals = list_evaluations(rfq_no)
    commercial = compare_quotes(rfq_no) if rfq else None
    commercial_w, technical_w = get_weights(rfq_no)

    # Index by quote_id
    tech_by_quote = {e.quote_id: e for e in tech_evals}
    comm_by_quote = {e.quote_id: e for e in (commercial.evaluations if commercial else [])}

    # Build combined list over the union of quotes
    combined: List[CombinedEvaluation] = []
    for q in quotes:
        c = comm_by_quote.get(q.quote_id)
        t = tech_by_quote.get(q.quote_id)
        commercial_score = c.composite_score if c else 0.0
        technical_score = t.technical_score if t else 0
        deviations = sum(1 for s in (t.criteria_scores if t else []) if s.compliance in {"deviation", "non_compliant"})
        disqualified = t.disqualified if t else False
        combined_score = (
            0.0 if disqualified
            else round(commercial_w * commercial_score + technical_w * technical_score, 1)
        )
        notes: List[str] = []
        if disqualified:
            notes.append(f"Disqualified: {t.disqualification_reason if t else ''}".strip())
        if not t:
            notes.append("Technical evaluation pending")
        combined.append(
            CombinedEvaluation(
                vendor=q.vendor,
                quote_id=q.quote_id,
                commercial_score=round(commercial_score, 1),
                technical_score=technical_score,
                combined_score=combined_score,
                commercial_rank=0,  # set below
                technical_rank=0,
                combined_rank=0,
                deviations_count=deviations,
                disqualified=disqualified,
                notes=notes,
            )
        )

    # Ranks
    for key, attr in [("commercial_score", "commercial_rank"), ("technical_score", "technical_rank"), ("combined_score", "combined_rank")]:
        ranked = sorted(combined, key=lambda c: getattr(c, key), reverse=True)
        for i, item in enumerate(ranked, start=1):
            setattr(item, attr, i)

    # Recommendation: highest combined among non-disqualified
    qualified = [c for c in combined if not c.disqualified]
    rec = max(qualified, key=lambda c: c.combined_score) if qualified else None
    rationale = None
    if rec:
        rationale = (
            f"Awarded to {rec.vendor} on combined score {rec.combined_score:.1f}/100 "
            f"(commercial {rec.commercial_score:.0f} × {commercial_w:.0%} + "
            f"technical {rec.technical_score} × {technical_w:.0%}). "
            f"{rec.deviations_count} deviation(s) noted."
        )
    notes_global: List[str] = []
    if not commercial:
        notes_global.append("No commercial comparison yet — at least 2 quotes are needed.")
    if not tech_evals:
        notes_global.append("No technical evaluations yet — use the AI button or fill scores manually.")
    if any(c.disqualified for c in combined):
        notes_global.append(f"{sum(c.disqualified for c in combined)} vendor(s) disqualified on mandatory criteria.")

    return TBE(
        rfq_no=rfq_no,
        generated_at=_now(),
        criteria=criteria,
        technical_evaluations=tech_evals,
        commercial=commercial,
        combined=sorted(combined, key=lambda c: c.combined_rank),
        commercial_weight=commercial_w,
        technical_weight=technical_w,
        recommended_vendor=rec.vendor if rec else None,
        recommendation_rationale=rationale,
        notes=notes_global,
    )


# ---------------------------------------------------------------------------
# AI auto-evaluation
# ---------------------------------------------------------------------------


def auto_evaluate(rfq_no: str) -> List[TechnicalEvaluation]:
    """For each quote on this RFQ, generate technical scores per criterion.

    Tries Grok first (source='grok'); falls back to deterministic heuristics
    (source='deterministic') that use vendor scorecard + quote notes as proxies.
    """

    from .llm import grok_json, is_enabled
    from .sourcing import get_quotes, get_rfq
    from .vendor_intel import get_vendor_scorecard

    rfq = get_rfq(rfq_no)
    if not rfq:
        return []
    quotes = get_quotes(rfq_no)
    criteria = get_criteria(rfq_no, rfq.description)

    out: List[TechnicalEvaluation] = []
    for q in quotes:
        scorecard = get_vendor_scorecard(q.vendor)
        if is_enabled():
            ctx = {
                "rfq": {
                    "code": rfq.code,
                    "description": rfq.description,
                    "quantity": rfq.quantity,
                    "uom": rfq.uom,
                    "notes": rfq.notes,
                },
                "quote": {
                    "vendor": q.vendor,
                    "unit_price_usd": q.unit_price_usd,
                    "lead_time_days": q.lead_time_days,
                    "incoterm": q.incoterm,
                    "notes": q.notes,
                },
                "vendor_scorecard": (
                    {
                        "composite_score": scorecard.composite_score,
                        "country": scorecard.country,
                        "flags": scorecard.flags,
                        "quality_components": [
                            {"dim": c.dimension, "score": c.score, "note": c.note}
                            for c in scorecard.components
                        ],
                    }
                    if scorecard
                    else None
                ),
                "criteria": [
                    {"id": c.criterion_id, "name": c.name, "description": c.description, "weight": c.weight, "mandatory": c.mandatory}
                    for c in criteria
                ],
            }
            system = (
                "You are a senior procurement engineer doing a Technical Bid Evaluation. "
                "Given an RFQ, a vendor quote, the vendor's scorecard, and a list of weighted "
                "technical criteria, return a score (0-100) and compliance level for each "
                "criterion. Be realistic: vendors with poor scorecards or single-source flags "
                "score lower on quality / experience criteria. If the quote notes mention a "
                "deviation, mark it explicitly. Compliance levels: full · partial · deviation · "
                "non_compliant · not_assessed.\n\n"
                "Return JSON: {\"scores\": [{\"criterion_id\": str, \"score\": int 0-100, "
                "\"compliance\": one of the levels, \"note\": <=12-word string, "
                "\"deviation_text\": optional string}]}"
            )
            user = "Evaluate this quote:\n" + _json.dumps(ctx, default=str, indent=2)
            parsed = grok_json(system, user, max_tokens=900)
            if parsed and isinstance(parsed.get("scores"), list):
                scores = []
                for s in parsed["scores"]:
                    try:
                        scores.append(
                            CriterionScore(
                                criterion_id=str(s["criterion_id"]),
                                score=int(s.get("score", 0)),
                                compliance=s.get("compliance", "not_assessed"),
                                note=str(s.get("note") or "")[:200],
                                deviation_text=s.get("deviation_text"),
                            )
                        )
                    except (KeyError, ValueError, TypeError):
                        continue
                if scores:
                    out.append(
                        set_evaluation(
                            rfq_no=rfq_no,
                            quote_id=q.quote_id,
                            vendor=q.vendor,
                            scores=scores,
                            notes="Grok-generated TBE",
                            source="grok",
                        )
                    )
                    continue

        # Deterministic fallback — derive heuristic scores from the scorecard
        base = scorecard.composite_score if scorecard else 65
        flag_penalty = (len(scorecard.flags) * 4) if scorecard else 0
        scores: List[CriterionScore] = []
        for c in criteria:
            # Bias by category
            bias = {
                "materials":      +2 if scorecard and any("nde" in f.lower() or "ncr" in f.lower() for f in scorecard.flags) else 0,
                "quality":        -flag_penalty // 2,
                "warranty":       -2 if scorecard and "new supplier" in [f.lower() for f in scorecard.flags] else 0,
                "experience":     -8 if scorecard and "new supplier" in [f.lower() for f in scorecard.flags] else +4,
                "scope_of_supply": 0,
                "documentation":  -3 if not q.notes else +2,
                "performance":    0,
                "delivery_terms": +2 if q.incoterm in ("DAP", "DDP", "CIP") else -2,
                "spec_compliance": 0,
                "spares_service": -3 if not scorecard else 0,
                "commercial_terms": 0,
            }.get(c.category, 0)
            raw = max(35, min(95, base + bias))
            compliance = (
                "full"          if raw >= 85 else
                "partial"       if raw >= 70 else
                "deviation"     if raw >= 50 else
                "non_compliant"
            )
            scores.append(
                CriterionScore(
                    criterion_id=c.criterion_id,
                    score=raw,
                    compliance=compliance,  # type: ignore[arg-type]
                    note=(
                        f"Heuristic from scorecard ({scorecard.composite_score}/100)" if scorecard
                        else "Heuristic — no scorecard data on file"
                    ),
                )
            )
        out.append(
            set_evaluation(
                rfq_no=rfq_no,
                quote_id=q.quote_id,
                vendor=q.vendor,
                scores=scores,
                notes="Heuristic deterministic TBE",
                source="deterministic",
            )
        )
    return out
