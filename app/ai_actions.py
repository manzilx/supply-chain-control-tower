"""Cross-module AI features that don't belong inside any single domain module.

- bom_autofill        : propose category + supplier for BOM rows missing them
- draft_spec_request  : email to engineering for a missing-spec BOM item
- explain_entity      : generic 'what should I know' brief over any entity
                        (PO, vendor, risk, project, RFQ, PR)
- propose_vendor_onboarding : submit new vendor through approval gate

Each function tries Grok and falls back to deterministic output, returning a
typed schema with `source` indicating which path was used.
"""

from __future__ import annotations

import json as _json
from datetime import datetime, timezone
from typing import Optional

from .llm import grok_chat, grok_json, is_enabled
from .planning import get_bom, get_project, list_projects
from .sample_data import build_demo_request
from .schemas import (
    BOMAutofillReply,
    BOMAutofillSuggestion,
    ExplainReply,
    ExplainRequest,
    GatedVendorReply,
    SpecRequestReply,
    SupplierRecord,
    User,
)


# ---------------------------------------------------------------------------
# BOM auto-fill
# ---------------------------------------------------------------------------


def bom_autofill(project_id: str) -> BOMAutofillReply:
    """Propose category + supplier_name for BOM rows missing them.

    The frontend can present these as suggestions for the buyer to accept.
    """

    items = get_bom(project_id)
    sparse = [i for i in items if (not i.category) or (not i.supplier_name)]
    if not sparse:
        return BOMAutofillReply(
            project_id=project_id,
            suggestions=[],
            source="deterministic",
            generated_at=datetime.now(timezone.utc),
        )

    suppliers = build_demo_request().suppliers
    supplier_directory = [
        {"name": s.name, "category": s.category, "country": s.country}
        for s in suppliers
    ]
    categories = sorted({s.category for s in suppliers})

    if is_enabled():
        context = {
            "approved_suppliers": supplier_directory,
            "category_options": categories,
            "items_needing_fill": [
                {
                    "bom_item_id": i.bom_item_id,
                    "code": i.code,
                    "description": i.description,
                    "current_category": i.category,
                    "current_supplier": i.supplier_name,
                }
                for i in sparse[:30]
            ],
        }
        system = (
            "You match BOM rows to the most appropriate supplier and category "
            "from the approved supplier directory provided. Only propose "
            "suppliers that exist in `approved_suppliers`. Only propose "
            "categories that exist in `category_options`. If you cannot find a "
            "good match for a row, omit it from the response. Return JSON: "
            "{\"suggestions\": ["
            "{\"bom_item_id\": str, \"suggested_category\": str|null, "
            "\"suggested_supplier\": str|null, \"reason\": str}]}"
        )
        user = "Match these BOM rows:\n" + _json.dumps(context, default=str, indent=2)
        parsed = grok_json(system, user, max_tokens=2000, timeout=45)
        if parsed and isinstance(parsed.get("suggestions"), list):
            by_id = {i.bom_item_id: i for i in sparse}
            suggestions = []
            for s in parsed["suggestions"]:
                item = by_id.get(s.get("bom_item_id"))
                if not item:
                    continue
                suggestions.append(
                    BOMAutofillSuggestion(
                        bom_item_id=item.bom_item_id,
                        code=item.code,
                        description=item.description,
                        current_category=item.category,
                        current_supplier=item.supplier_name,
                        suggested_category=s.get("suggested_category"),
                        suggested_supplier=s.get("suggested_supplier"),
                        reason=str(s.get("reason") or "category and description match"),
                    )
                )
            if suggestions:
                return BOMAutofillReply(
                    project_id=project_id,
                    suggestions=suggestions,
                    source="grok",
                    generated_at=datetime.now(timezone.utc),
                )

    # Deterministic fallback — match by category keyword in description
    desc_keywords = {
        "Forged valves":            ["valve", "gate valve", "globe", "check valve"],
        "PLC and control panels":   ["plc", "control panel", "i/o module", "rtu"],
        "Copper busbars":           ["busbar", "copper bus"],
        "Power transformers":       ["transformer", "txf-"],
        "GIS Switchgear":           ["gis", "switchgear", "switchyard"],
        "Power cables":             ["cable", "xlpe"],
        "Hydromechanical equipment":["gate", "hoist", "trash rack", "stop log"],
        "Civil consumables":        ["cement", "rebar", "tmt"],
    }
    suggestions: list[BOMAutofillSuggestion] = []
    for item in sparse:
        desc = (item.description or "").lower()
        match_cat: Optional[str] = item.category
        if not match_cat:
            for cat, keys in desc_keywords.items():
                if any(k in desc for k in keys):
                    match_cat = cat
                    break
        match_sup = item.supplier_name
        if not match_sup and match_cat:
            pool = [s for s in suppliers if s.category == match_cat]
            pool.sort(key=lambda s: (-s.on_time_delivery_pct, s.quality_ppm))
            if pool:
                match_sup = pool[0].name
        if match_cat or match_sup:
            suggestions.append(
                BOMAutofillSuggestion(
                    bom_item_id=item.bom_item_id,
                    code=item.code,
                    description=item.description,
                    current_category=item.category,
                    current_supplier=item.supplier_name,
                    suggested_category=match_cat,
                    suggested_supplier=match_sup,
                    reason="keyword match against description",
                )
            )

    return BOMAutofillReply(
        project_id=project_id,
        suggestions=suggestions,
        source="deterministic",
        generated_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Spec request drafter
# ---------------------------------------------------------------------------


def draft_spec_request(project_id: str, bom_item_id: str) -> Optional[SpecRequestReply]:
    """Draft an email asking engineering to release a spec for a BOM item."""

    project = get_project(project_id)
    if not project:
        return None
    item = next((i for i in get_bom(project_id) if i.bom_item_id == bom_item_id), None)
    if not item:
        return None

    subject = f"[Spec needed] {item.code} — required for {project.name}"
    to_placeholder = "engineering@" + project.name.lower().replace(" ", "")[:20] + ".com"

    if is_enabled():
        context = {
            "project": {"id": project.project_id, "name": project.name, "site": project.site},
            "item": {
                "code": item.code,
                "description": item.description,
                "category": item.category,
                "quantity": item.quantity,
                "uom": item.uom,
                "need_by": item.planned_need_date,
                "milestone_code": item.milestone_code,
                "long_lead_days": item.long_lead_days,
            },
            "missing": [
                f for f, v in [
                    ("spec_doc_id", item.spec_doc_id),
                    ("drawing_id", item.drawing_id),
                ] if not v
            ],
        }
        system = (
            "You are a buyer drafting an email to engineering asking them to "
            "release the spec for a procurement line item. Be specific: cite "
            "the code, description, need-by date, milestone, and what's missing. "
            "Tone: professional, time-aware. 3 short paragraphs max. End with "
            "'Best regards,' and 'Procurement — Control Tower'. Plain prose, no markdown."
        )
        user = "Draft the email body using only this data:\n" + _json.dumps(context, default=str, indent=2)
        body = grok_chat(system, user, max_tokens=500, temperature=0.3, timeout=25)
        if body:
            return SpecRequestReply(
                bom_item_id=item.bom_item_id,
                code=item.code,
                to_placeholder=to_placeholder,
                subject=subject,
                body=body,
                source="grok",
                generated_at=datetime.now(timezone.utc),
            )

    # Deterministic fallback
    need_phrase = f" before {item.planned_need_date.isoformat()}" if item.planned_need_date else ""
    milestone = f" (linked to milestone {item.milestone_code})" if item.milestone_code else ""
    body = (
        f"Hi Engineering team,\n\n"
        f"We need the released specification for {item.code} — {item.description} "
        f"on {project.name}. This is a {item.quantity} {item.uom} requirement{milestone}, "
        f"and we'd like to issue the PR{need_phrase}.\n\n"
        f"Currently the BOM line is missing "
        f"{'a spec document' if not item.spec_doc_id else ''}"
        f"{' and ' if not item.spec_doc_id and not item.drawing_id else ''}"
        f"{'a drawing reference' if not item.drawing_id else ''}. "
        f"Please share the latest revision (or confirm an existing reference) so we can "
        f"proceed with vendor enquiries.\n\n"
        f"Lead time on this category is roughly {item.long_lead_days or 'TBC'} days, "
        f"so any delay here pushes the milestone date.\n\n"
        f"Best regards,\nProcurement — Control Tower"
    )
    return SpecRequestReply(
        bom_item_id=item.bom_item_id,
        code=item.code,
        to_placeholder=to_placeholder,
        subject=subject,
        body=body,
        source="deterministic",
        generated_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Explain anything
# ---------------------------------------------------------------------------


def explain_entity(request: ExplainRequest) -> ExplainReply:
    """Build a 'what should I know about this' brief over a single entity."""

    payload, deterministic_fallback = _gather_context(request)

    if not payload:
        return ExplainReply(
            kind=request.kind,
            id=request.id,
            headline=f"{request.kind} {request.id} not found",
            body="No data was located for that identifier.",
            bullets=[],
            source="deterministic",
            generated_at=datetime.now(timezone.utc),
        )

    if is_enabled():
        system = (
            "You are an operations analyst. Given the data for a single entity, "
            "write a brief 'what should I know about this' summary. Cite concrete "
            "fields. Return JSON: {\"headline\": <=14-word string, "
            "\"body\": 2-3 short paragraph plain prose string, "
            "\"bullets\": list of 3-5 short fact bullets (each <=14 words)}"
        )
        user = (
            f"Entity kind: {request.kind}\nEntity id: {request.id}\n\n"
            f"Data:\n" + _json.dumps(payload, default=str, indent=2)
        )
        parsed = grok_json(system, user, max_tokens=700)
        if parsed and parsed.get("headline") and parsed.get("body"):
            bullets = parsed.get("bullets") or []
            return ExplainReply(
                kind=request.kind,
                id=request.id,
                headline=str(parsed["headline"])[:140],
                body=str(parsed["body"]),
                bullets=[str(b) for b in bullets][:6],
                source="grok",
                generated_at=datetime.now(timezone.utc),
            )

    return ExplainReply(
        kind=request.kind,
        id=request.id,
        headline=deterministic_fallback["headline"],
        body=deterministic_fallback["body"],
        bullets=deterministic_fallback["bullets"],
        source="deterministic",
        generated_at=datetime.now(timezone.utc),
    )


def _gather_context(request: ExplainRequest):
    """Look up the entity and return (data_payload, deterministic_fallback_dict).

    Returns (None, _) if the entity is not found.
    """

    kind = request.kind
    eid = request.id

    if kind == "po":
        # First look at the legacy scenario POs, then sourcing POs
        from .sourcing import get_po as _get_sourcing_po
        sp = _get_sourcing_po(eid)
        if sp:
            payload = sp.model_dump()
            payload["_kind"] = "sourcing_po"
            fb = {
                "headline": f"PO {sp.po_no} — {sp.vendor} — ${sp.value_usd:,.0f}",
                "body": (
                    f"Sourcing PO {sp.po_no} issued to {sp.vendor} for "
                    f"{sp.quantity} {sp.uom} of {sp.code} ({sp.description}). "
                    f"Value ${sp.value_usd:,.0f}, lead time {sp.lead_time_days}d, "
                    f"need-by {sp.need_by}, currently {sp.status}."
                ),
                "bullets": [
                    f"Project {sp.project_id}",
                    f"Award {sp.award_id} from RFQ {sp.rfq_no}",
                    f"Status: {sp.status}",
                    f"Incoterm {sp.incoterm}",
                ],
            }
            return payload, fb
        legacy = next(
            (p for p in build_demo_request().purchase_orders if p.po_number == eid),
            None,
        )
        if legacy:
            payload = legacy.model_dump()
            payload["_kind"] = "scenario_po"
            fb = {
                "headline": f"PO {legacy.po_number} — {legacy.supplier_name}",
                "body": (
                    f"PO {legacy.po_number} to {legacy.supplier_name} for {legacy.quantity} "
                    f"× {legacy.sku}, valued ${legacy.value_usd:,.0f}, due in "
                    f"{legacy.due_in_days} days, status '{legacy.status}'."
                ),
                "bullets": [
                    f"Supplier: {legacy.supplier_name}",
                    f"SKU: {legacy.sku}",
                    f"Status: {legacy.status}",
                    f"Expedite possible: {'yes' if legacy.expedite_possible else 'no'}",
                ],
            }
            return payload, fb
        return None, None

    if kind == "vendor":
        from .vendor_intel import get_vendor_scorecard
        sc = get_vendor_scorecard(eid)
        if not sc:
            return None, None
        payload = sc.model_dump()
        fb = {
            "headline": f"{sc.vendor} — score {sc.composite_score}/100 (grade {sc.composite_grade})",
            "body": (
                f"{sc.vendor} in {sc.country}, category {sc.category}. "
                f"Composite {sc.composite_score}/100 ({sc.composite_grade}). "
                f"Annual spend ${sc.annual_spend_usd:,.0f}. "
                f"{'Single-source exposure. ' if sc.single_source_exposure else ''}"
                f"{len(sc.flags)} active risk flag(s)."
            ),
            "bullets": [
                f"Composite {sc.composite_score}/100",
                f"Concentration {sc.concentration_pct:.0f}%",
                f"Alternates: {sc.approved_alternatives}",
                *[f"Flag: {f}" for f in sc.flags[:3]],
            ],
        }
        return payload, fb

    if kind == "project":
        proj = next((p for p in list_projects() if p.project_id == eid), None)
        if not proj:
            return None, None
        bom = get_bom(eid)
        long_lead = [i for i in bom if (i.long_lead_days or 0) >= 365]
        missing = [i for i in bom if not i.spec_doc_id]
        payload = {
            "project": proj.model_dump(),
            "bom_count": len(bom),
            "long_lead_count": len(long_lead),
            "missing_spec_count": len(missing),
            "milestones": [m.model_dump() for m in proj.milestones],
        }
        fb = {
            "headline": f"{proj.name} — {len(bom)} BOM items · {len(long_lead)} long-lead",
            "body": (
                f"{proj.name} for {proj.client} at {proj.site}. Sector {proj.sector}. "
                f"{len(proj.milestones)} milestones tracked. {len(bom)} BOM lines, of "
                f"which {len(long_lead)} are long-lead (≥365d) and {len(missing)} are "
                f"missing specs."
            ),
            "bullets": [
                f"Client: {proj.client}",
                f"Site: {proj.site}",
                f"Currency: {proj.currency}",
                f"Milestones: {len(proj.milestones)}",
                f"Long-lead items: {len(long_lead)}",
                f"Missing specs: {len(missing)}",
            ],
        }
        return payload, fb

    if kind == "risk":
        # The id is the risk title; analyzer is stateless so we re-run.
        from .analytics import analyze_supply_chain
        analyzed = analyze_supply_chain(build_demo_request(), ai_response="")
        risk = next((r for r in analyzed.top_risks if r.title == eid), None)
        if not risk:
            return None, None
        payload = risk.model_dump()
        fb = {
            "headline": f"{risk.severity.upper()} — {risk.title}",
            "body": f"{risk.summary} Owner: {risk.owner}.",
            "bullets": [
                f"Type: {risk.risk_type}",
                f"Severity: {risk.severity}",
                f"Score: {risk.score}",
                f"Owner: {risk.owner}",
                *([f"Supplier: {risk.supplier_name}"] if risk.supplier_name else []),
            ],
        }
        return payload, fb

    if kind == "rfq":
        from .sourcing import get_rfq, get_quotes
        rfq = get_rfq(eid)
        if not rfq:
            return None, None
        quotes = get_quotes(eid)
        payload = {"rfq": rfq.model_dump(), "quotes": [q.model_dump() for q in quotes]}
        fb = {
            "headline": f"RFQ {rfq.rfq_no} — {rfq.code} — {rfq.status}",
            "body": (
                f"RFQ {rfq.rfq_no} for {rfq.quantity} {rfq.uom} of {rfq.code}, "
                f"issued to {len(rfq.vendors)} vendor(s), currently {rfq.status}. "
                f"{len(quotes)} quote(s) received."
            ),
            "bullets": [
                f"PR: {rfq.pr_no}",
                f"Vendors: {', '.join(rfq.vendors)}",
                f"Status: {rfq.status}",
                f"Quotes received: {len(quotes)}",
            ],
        }
        return payload, fb

    if kind == "pr":
        from .sourcing import get_pr
        pr = get_pr(eid)
        if not pr:
            return None, None
        payload = pr.model_dump()
        fb = {
            "headline": f"PR {pr.pr_no} — {pr.code} — {pr.status}",
            "body": (
                f"Purchase requisition {pr.pr_no} for {pr.quantity} {pr.uom} of "
                f"{pr.code} ({pr.description}). Buyer {pr.buyer}, status {pr.status}, "
                f"need-by {pr.need_by}."
            ),
            "bullets": [
                f"Project: {pr.project_id}",
                f"Buyer: {pr.buyer}",
                f"Strategy: {pr.strategy}",
                f"Status: {pr.status}",
            ],
        }
        return payload, fb

    return None, None


# ---------------------------------------------------------------------------
# Vendor onboarding (AI propose → approval gate)
# ---------------------------------------------------------------------------


def propose_vendor_onboarding(supplier: SupplierRecord, user: User) -> GatedVendorReply:
    """Thin wrapper around the vendor onboarding approval gate."""
    from .approvals import gate_vendor

    return gate_vendor(supplier, user)
