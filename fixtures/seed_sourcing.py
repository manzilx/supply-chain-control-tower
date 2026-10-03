"""Walk a representative slice of BOM lines through the full sourcing workflow.

For each (project, bom_item) pair:

    PR (create)
        → RFQ (issue, vendors invited)
            → Quotes (one per vendor, differentiated pricing/lead-time)
                → Compare (engine ranks)
                    → Award (winner)
                        → Sourcing PO (auto-generated)

The point is to populate every downstream page that depends on the sourcing
workflow having been completed: /sourcing, /awards, /sourcing-pos,
/commercial, the post-award slice of /logistics, and the AI weekly plan.

Also closes out the pre-seeded demo RFQ (RFQ-00001, quotes received but never
awarded),
and posts shipment events on a handful of brand-new POs so /logistics has more
than just the legacy scenario rows.

Run against a live backend on :8010 — assumes Mahadev Hydro fixture is already
loaded (i.e. you started uvicorn via fixtures.hydro.serve_with_hydro).
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from typing import Any, Optional


API = os.getenv("SEED_API_BASE", "http://127.0.0.1:8010")

# Every project this script touches, mapped to its owning tenant. Writes are
# tenant-scoped since M7, so each workflow runs under that tenant's
# procurement head (who self-approves any gated award/quote).
TENANT_FOR_PROJECT = {
    "PRJ-RB-660": "arcforge",
    "HYD-MAHADEV-220": "northwind",
    "PRJ-NS-OSS": "helios",
    "PRJ-HE-WIND": "helios",
    "PRJ-HE-FPSO": "helios",
}

_tokens: dict[str, str] = {}


def _req(method: str, path: str, body: Optional[dict] = None, token: Optional[str] = None) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    headers: dict[str, str] = {}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        f"{API}{path}",
        data=data,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req) as r:
            payload = r.read().decode()
            return json.loads(payload) if payload else None
    except urllib.error.HTTPError as e:
        print(f"  [HTTP {e.code}] {method} {path}: {e.read().decode()[:200]}")
        return None


def _login(tenant_id: str, role: str = "head") -> str:
    """JWT for a tenant persona (procurement head by default), cached."""
    user_id = f"{tenant_id}-{role}-01"
    token = _tokens.get(user_id)
    if token:
        return token
    reply = _req("POST", "/api/auth/login", {"user_id": user_id})
    if not reply or not reply.get("token"):
        print(f"login failed for {user_id}")
        sys.exit(1)
    _tokens[user_id] = reply["token"]
    return reply["token"]


# ---------------------------------------------------------------------------
# Workflow walker
# ---------------------------------------------------------------------------


def walk_workflow(
    project_id: str,
    bom_item_id: str,
    code: str,
    description: str,
    quantity: float,
    quotes: list[dict],
    award_pref: Optional[str] = None,
    note_prefix: str = "",
    price_factor: float = 1.0,
    need_in_days: Optional[int] = None,
) -> Optional[str]:
    """One full PR→RFQ→Quote→Award→PO walk. Returns the PO number on success.

    `price_factor` scales every quote uniformly (vendor ranking unchanged) so the
    market lands under or over the BOM estimate — which is what /commercial
    reports as savings or overrun.

    `need_in_days` overrides the BOM need date for lines whose fixture date has
    already passed — otherwise a PR raised today shows up months overdue.
    """

    label = f"{code:18} ({project_id})"
    print(f"  {label}")
    token = _login(TENANT_FOR_PROJECT[project_id])

    # 1. PR
    pr = _req("POST", "/api/prs", {
        "project_id": project_id,
        "bom_item_id": bom_item_id,
        "code": code,
        "description": description,
        "quantity": quantity,
        **({"need_by": (date.today() + timedelta(days=need_in_days)).isoformat()} if need_in_days else {}),
    }, token=token)
    if not pr:
        print(f"    pr failed for {code}")
        return None
    pr_no = pr["pr_no"]
    print(f"    + PR  {pr_no}")

    # 2. RFQ
    vendors = [q["vendor"] for q in quotes]
    rfq = _req("POST", "/api/rfqs", {
        "pr_no": pr_no,
        "vendors": vendors,
        "due_in_days": 14,
        "notes": f"{note_prefix} Multi-source RFQ with {len(vendors)} vendors invited.".strip(),
    }, token=token)
    if not rfq:
        print(f"    rfq failed for {code}")
        return None
    rfq_no = rfq["rfq_no"]
    print(f"    + RFQ {rfq_no} ({len(vendors)} vendors)")

    # 3. Quotes
    quote_ids = []
    for q in quotes:
        body = {
            "vendor": q["vendor"],
            "unit_price_usd": round(q["unit_price"] * price_factor, 2),
            "lead_time_days": q["lead_days"],
            "incoterm": q.get("incoterm", "CIP"),
            "validity_days": q.get("validity", 30),
            "notes": q.get("notes"),
        }
        # Strip None notes
        if body["notes"] is None:
            del body["notes"]
        reply = _req("POST", f"/api/rfqs/{rfq_no}/quotes", body, token=token)
        quote = (reply or {}).get("quote")  # GatedQuoteReply; head self-approves → applied
        if not quote:
            print(f"    quote {q['vendor']} failed ({(reply or {}).get('status', 'no reply')})")
            continue
        quote_ids.append((q["vendor"], quote["quote_id"], quote["total_usd"]))
    print(f"    + {len(quote_ids)} quotes")

    # 4. Compare (logged for visibility)
    comp = _req("GET", f"/api/rfqs/{rfq_no}/compare", token=token)
    if comp:
        winner_engine = comp.get("recommended_vendor")
        print(f"    = engine recommends: {winner_engine}")

    # 5. Award
    pick = award_pref or (comp.get("recommended_vendor") if comp else None)
    if not pick:
        print(f"    no award pick, skipping")
        return None
    award_quote_id = next((qid for v, qid, _ in quote_ids if v == pick), None)
    if not award_quote_id:
        print(f"    award pick {pick} not in quotes")
        return None
    award_total = next((t for v, _, t in quote_ids if v == pick), 0)
    rationale = (
        f"Awarded to {pick} based on composite score (price + lead-time + "
        f"reliability). Total quoted: USD {award_total:,.0f}."
    )
    if award_pref and comp and pick != comp.get("recommended_vendor"):
        rationale += f" NOTE: Override from engine recommendation ({comp.get('recommended_vendor')}) — strategic / continuity reasons."
    reply = _req("POST", f"/api/rfqs/{rfq_no}/award", {
        "quote_id": award_quote_id,
        "rationale": rationale,
        "awarded_by": "Procurement Head",
    }, token=token)
    award = (reply or {}).get("award")  # GatedAwardReply; head self-approves → applied
    if not award:
        print(f"    award failed ({(reply or {}).get('status', 'no reply')})")
        return None
    print(f"    + Award {award['award_id']} → {pick} (USD {award_total:,.0f})")

    # 6. PO is auto-created; the gated reply carries it.
    po = reply.get("po")
    if po is None:
        pos = _req("GET", "/api/sourcing-pos", token=token) or []
        po = next((p for p in pos if p["award_id"] == award["award_id"]), None)
    if po:
        print(f"    + PO  {po['po_no']}")
        return po["po_no"]
    return None


# ---------------------------------------------------------------------------
# Items to walk
# ---------------------------------------------------------------------------


WORKFLOWS = [
    # ---- Riverbank 2x660 MW ----
    dict(
        project_id="PRJ-RB-660", bom_item_id="RB-001", code="BFP-660-A",
        description="Boiler Feed Pump 660MW set A",
        quantity=2,
        price_factor=0.94,
        award="Helios Cast & Forge",
        quotes=[
            {"vendor": "Helios Cast & Forge", "unit_price": 920000, "lead_days": 240, "notes": "Standard scope, includes FAT at vendor works"},
            {"vendor": "KSB India",            "unit_price": 968000, "lead_days": 220, "notes": "Includes spare impeller and one-year service contract"},
            {"vendor": "Sulzer",               "unit_price": 1015000, "lead_days": 270, "notes": "Premium offering, FX-locked EUR"},
        ],
    ),
    dict(
        project_id="PRJ-RB-660", bom_item_id="RB-003", code="PLC-S7-IO48",
        description="PLC I/O module 48 point",
        quantity=16,
        price_factor=0.91,
        award="BluePeak Controls",
        quotes=[
            {"vendor": "BluePeak Controls",  "unit_price": 2250, "lead_days": 55, "notes": "Stock available, includes test certificates"},
            {"vendor": "Siemens Energy",     "unit_price": 2480, "lead_days": 60, "notes": "Genuine S7 modules, OEM warranty"},
            {"vendor": "Schneider Electric", "unit_price": 2380, "lead_days": 70, "notes": "Modicon equivalent with conversion support"},
        ],
    ),
    dict(
        project_id="PRJ-RB-660", bom_item_id="RB-004", code="TXF-110-40",
        description="Auxiliary transformer 110/11 kV 40 MVA",
        quantity=1,
        price_factor=1.06,
        award="CG Power",
        quotes=[
            {"vendor": "CG Power",        "unit_price": 480000, "lead_days": 180, "notes": "Type-tested, ICT compliance certified"},
            {"vendor": "BHEL Bhopal",     "unit_price": 462000, "lead_days": 240, "notes": "Lower price; longer lead due to Q3 capacity"},
            {"vendor": "Hyundai Electric","unit_price": 528000, "lead_days": 210, "notes": "FX-locked KRW, premium copper winding"},
        ],
    ),
    dict(
        project_id="PRJ-RB-660", bom_item_id="RB-006", code="STRUCT-S355",
        description="Structural steel S355 fabrication",
        quantity=220,
        price_factor=0.95,
        award="JSW Steel",
        quotes=[
            {"vendor": "JSW Steel",  "unit_price": 1850, "lead_days": 60, "notes": "Mill rolled + fabricated to ASTM A572 Gr 50"},
            {"vendor": "Tata Steel", "unit_price": 1920, "lead_days": 55, "notes": "Includes shop primer, premium QA"},
            {"vendor": "SAIL",       "unit_price": 1810, "lead_days": 75, "notes": "Lowest price; longer transit from Bhilai"},
        ],
    ),
    dict(
        project_id="PRJ-RB-660", bom_item_id="RB-007", code="COND-TUBE-INC",
        description="Condenser tubes Inconel 625",
        quantity=4200,
        price_factor=0.97,
        award="Sandvik Materials Tech",
        quotes=[
            {"vendor": "Sandvik Materials Tech", "unit_price": 48,  "lead_days": 150, "notes": "EN 10216-5 compliant, FX-locked SEK"},
            {"vendor": "Vallourec",              "unit_price": 51,  "lead_days": 165, "notes": "Premium pickling + passivation"},
            {"vendor": "Tubacex",                "unit_price": 46,  "lead_days": 180, "notes": "Lowest price; longer dispatch from Spain"},
        ],
    ),
    dict(
        project_id="PRJ-RB-660", bom_item_id="RB-008", code="COOLING-TWR-MOD",
        description="Induced draft cooling tower module",
        quantity=4,
        price_factor=1.04,
        award="GEI Industrial Systems",
        quotes=[
            {"vendor": "GEI Industrial Systems",     "unit_price": 310000, "lead_days": 210, "notes": "FRP construction, 28% drift eliminator"},
            {"vendor": "Paharpur Cooling Towers",    "unit_price": 295000, "lead_days": 240, "notes": "Lowest price; in-house drift eliminator"},
            {"vendor": "Voltas",                     "unit_price": 328000, "lead_days": 180, "notes": "Faster delivery, premium FRP"},
        ],
    ),

    # ---- Mahadev Hydro 220 MW ----
    dict(
        project_id="HYD-MAHADEV-220", bom_item_id="HYD-HM-002", code="HM-INTGT-01",
        description="Intake gate vertical lift 6.5x7.5 m",
        quantity=2,
        need_in_days=330,
        price_factor=0.93,
        award="ISGEC Heavy Engineering",
        quotes=[
            {"vendor": "ISGEC Heavy Engineering", "unit_price": 420000, "lead_days": 365, "notes": "Standard SS304 sealing, hydraulic interface"},
            {"vendor": "Texmaco Rail",            "unit_price": 408000, "lead_days": 390, "notes": "Lower price, similar scope"},
            {"vendor": "SLP Industries",          "unit_price": 432000, "lead_days": 360, "notes": "Includes one-year on-site commissioning support"},
        ],
    ),
    dict(
        project_id="HYD-MAHADEV-220", bom_item_id="HYD-CR-001", code="CR-EOT-PWR",
        description="Powerhouse EOT crane 200/30 t double girder",
        quantity=1,
        price_factor=0.96,
        award="Konecranes",
        quotes=[
            {"vendor": "Konecranes",  "unit_price": 1280000, "lead_days": 300, "notes": "VFD, anti-sway, redundant brakes"},
            {"vendor": "Demag Cranes","unit_price": 1245000, "lead_days": 330, "notes": "Lower price, longer lead"},
            {"vendor": "ELECON",      "unit_price": 1080000, "lead_days": 330, "notes": "Domestic; cost-leader, single-girder option also offered"},
        ],
    ),
    dict(
        project_id="HYD-MAHADEV-220", bom_item_id="HYD-CV-003", code="CV-REBAR-550",
        description="TMT rebar Fe 550 8 to 32 mm",
        quantity=6500,
        need_in_days=75,
        price_factor=1.08,
        award="Tata Steel",
        quotes=[
            {"vendor": "Tata Steel", "unit_price": 720, "lead_days": 60, "notes": "Tata Tiscon Fe 550, mill cert"},
            {"vendor": "JSW Steel",  "unit_price": 712, "lead_days": 65, "notes": "JSW Neosteel Fe 550, lower price"},
            {"vendor": "SAIL",       "unit_price": 708, "lead_days": 75, "notes": "SAIL Fe 550, longer transit"},
        ],
    ),
    dict(
        project_id="HYD-MAHADEV-220", bom_item_id="HYD-CV-001", code="CV-CEM-OPC",
        description="OPC 53 grade cement bulk",
        quantity=28000,
        need_in_days=45,
        price_factor=0.97,
        award="UltraTech Cement",
        quotes=[
            {"vendor": "UltraTech Cement", "unit_price": 98, "lead_days": 30, "notes": "Bulk delivery, dedicated rake"},
            {"vendor": "Ambuja Cements",   "unit_price": 96, "lead_days": 35, "notes": "Lower price; smaller rake size"},
            {"vendor": "ACC Limited",      "unit_price": 99, "lead_days": 30, "notes": "Same lead as UltraTech, premium"},
        ],
    ),
    dict(
        project_id="HYD-MAHADEV-220", bom_item_id="HYD-CB-002", code="CB-13-MV",
        description="13.8 kV power cable 3C 240 sq.mm",
        quantity=4500,
        price_factor=0.92,
        award="Polycab",
        quotes=[
            {"vendor": "Polycab",         "unit_price": 72, "lead_days": 150, "notes": "FRLS, type-tested at CPRI"},
            {"vendor": "KEI Industries",  "unit_price": 74, "lead_days": 140, "notes": "Faster lead, premium insulation"},
            {"vendor": "Havells Cables",  "unit_price": 70, "lead_days": 165, "notes": "Lowest price, longer lead"},
        ],
    ),
    dict(
        project_id="HYD-MAHADEV-220", bom_item_id="HYD-CW-001", code="CW-PUMP-VT",
        description="CW pump vertical turbine 5 m3/s",
        quantity=4,
        price_factor=0.95,
        award="Kirloskar Brothers",
        quotes=[
            {"vendor": "Kirloskar Brothers", "unit_price": 165000, "lead_days": 240, "notes": "Domestic OEM, includes startup spares"},
            {"vendor": "KSB India",          "unit_price": 178000, "lead_days": 210, "notes": "Faster lead, premium impeller alloy"},
            {"vendor": "Flowserve",          "unit_price": 198000, "lead_days": 270, "notes": "Imported scope, full BOM compliance"},
        ],
    ),
    dict(
        project_id="HYD-MAHADEV-220", bom_item_id="HYD-GIS-001", code="GIS-220-BAY",
        description="220 kV GIS bay (CB+ISO+ES+CT+VT)",
        quantity=4,
        price_factor=0.94,
        award="Hitachi Energy",
        quotes=[
            {"vendor": "Hitachi Energy",  "unit_price": 895000, "lead_days": 360, "notes": "ELK-04 series, type-tested"},
            {"vendor": "Siemens Energy",  "unit_price": 925000, "lead_days": 340, "notes": "8DN8 series, faster lead"},
            {"vendor": "ABB India",       "unit_price": 880000, "lead_days": 380, "notes": "ELK-3 series, lowest price"},
        ],
    ),
    dict(
        project_id="HYD-MAHADEV-220", bom_item_id="HYD-TR-001", code="TR-GT-130MVA",
        description="Generator transformer 130 MVA 13.8/220 kV",
        quantity=2,
        price_factor=1.03,
        award="BHEL Bhopal",
        quotes=[
            {"vendor": "BHEL Bhopal",      "unit_price": 2150000, "lead_days": 450, "notes": "OLTC, ICT-compliant, MAKE in India compliant"},
            {"vendor": "Hyundai Electric", "unit_price": 2280000, "lead_days": 420, "notes": "Faster lead, premium copper"},
            {"vendor": "Hitachi Energy",   "unit_price": 2380000, "lead_days": 405, "notes": "Premium offering, FX exposure"},
        ],
    ),

    # ---- Helios Offshore ----
    dict(
        project_id="PRJ-NS-OSS", bom_item_id="NS-002", code="CBL-66-SUBSEA",
        description="Subsea export cable 66kV XLPE",
        quantity=28,
        quotes=[
            {"vendor": "NorthCable Subsea", "unit_price": 198000, "lead_days": 330, "notes": "Includes jointing and load-out at Bergen"},
            {"vendor": "NKT",               "unit_price": 205000, "lead_days": 300, "notes": "Type-tested to IEC 63026, Karlskrona works"},
            {"vendor": "Prysmian",          "unit_price": 221000, "lead_days": 280, "notes": "Fastest slot; premium for Q2 factory capacity"},
        ],
    ),
    dict(
        project_id="PRJ-NS-OSS", bom_item_id="NS-004", code="J-TUBE-SS",
        description="J-tube stainless 316L",
        quantity=6,
        quotes=[
            {"vendor": "Aberdeen Steel Fab",     "unit_price": 41500, "lead_days": 120, "notes": "Fabricated and NDT'd in Aberdeen"},
            {"vendor": "Sandvik Materials Tech", "unit_price": 44000, "lead_days": 100, "notes": "Seamless 316L, mill-direct"},
            {"vendor": "Tenaris",                "unit_price": 39800, "lead_days": 150, "notes": "Lowest price; nickel surcharge not locked"},
        ],
    ),
    dict(
        project_id="PRJ-HE-WIND", bom_item_id="PRJ-HE-WIND-003", code="ARRAY-66KV",
        description="66 kV inter-array cable",
        quantity=85,
        quotes=[
            {"vendor": "NorthCable Subsea", "unit_price": 226000, "lead_days": 240, "notes": "Earliest delivery, carousel load-out included"},
            {"vendor": "NKT",               "unit_price": 212000, "lead_days": 270, "notes": "Framework pricing from Dogger Bank phase A"},
            {"vendor": "Prysmian",          "unit_price": 209000, "lead_days": 300, "notes": "Lowest price; Arco Felice factory slot"},
        ],
    ),
    dict(
        project_id="PRJ-HE-WIND", bom_item_id="PRJ-HE-WIND-004", code="TP-COATING",
        description="Transition piece marine coating",
        quantity=32,
        quotes=[
            {"vendor": "Coastline Marine Coatings", "unit_price": 61500, "lead_days": 45, "notes": "NORSOK M-501 system 7, applied at yard"},
            {"vendor": "Jotun",                     "unit_price": 63800, "lead_days": 40, "notes": "Includes coating inspector on site"},
            {"vendor": "Hempel",                    "unit_price": 59900, "lead_days": 60, "notes": "Lowest price; longer cure schedule"},
        ],
    ),
    dict(
        project_id="PRJ-HE-FPSO", bom_item_id="PRJ-HE-FPSO-002", code="GASCOMP-CENT",
        description="Centrifugal gas compressor",
        quantity=3,
        quotes=[
            {"vendor": "Siemens Energy",       "unit_price": 4350000, "lead_days": 420, "notes": "Dry gas seals, string test at Duisburg"},
            {"vendor": "Baker Hughes",         "unit_price": 4280000, "lead_days": 450, "notes": "Lowest price; longer string-test queue"},
            {"vendor": "MAN Energy Solutions", "unit_price": 4460000, "lead_days": 400, "notes": "Fastest delivery, premium for slot"},
        ],
    ),
    dict(
        project_id="PRJ-HE-FPSO", bom_item_id="PRJ-HE-FPSO-005", code="RISER-FLEX",
        description="Flexible production riser",
        quantity=6,
        quotes=[
            {"vendor": "NorthCable Subsea", "unit_price": 1390000, "lead_days": 300, "notes": "API 17J, includes bend stiffeners"},
            {"vendor": "TechnipFMC",        "unit_price": 1420000, "lead_days": 270, "notes": "Qualified for 25-year sour service"},
            {"vendor": "NOV Flexibles",     "unit_price": 1365000, "lead_days": 330, "notes": "Lowest price; Kalundborg capacity tight"},
        ],
    ),
]


# ---------------------------------------------------------------------------
# Existing-RFQ closeout (RFQ-00001)
# ---------------------------------------------------------------------------


def close_out_existing_rfqs() -> list[tuple[str, str]]:
    """Award the pre-seeded demo RFQs that have quotes but no award yet.
    These live in the arcforge scenario (seeded off Riverbank BOM lines);
    missing ones are skipped. Returns (po_no, tenant_id) pairs."""

    tenant_id = "arcforge"
    token = _login(tenant_id)
    pos: list[tuple[str, str]] = []
    for rfq_no, prefer in [("RFQ-00001", None)]:
        comp = _req("GET", f"/api/rfqs/{rfq_no}/compare", token=token)
        if not comp or not comp.get("recommended_vendor"):
            print(f"  [skip] {rfq_no} has no recommendation")
            continue
        winner = prefer or comp["recommended_vendor"]
        quotes = _req("GET", f"/api/rfqs/{rfq_no}/quotes", token=token) or []
        winner_quote = next((q for q in quotes if q["vendor"] == winner), None)
        if not winner_quote:
            continue
        rationale = (
            f"Awarded to {winner} per engine ranking (composite score). "
            f"Total: USD {winner_quote['total_usd']:,.0f}."
        )
        reply = _req("POST", f"/api/rfqs/{rfq_no}/award", {
            "quote_id": winner_quote["quote_id"],
            "rationale": rationale,
            "awarded_by": "Procurement Head",
        }, token=token)
        award = (reply or {}).get("award")
        if not award:
            continue
        po = reply.get("po")
        if po is None:
            all_pos = _req("GET", "/api/sourcing-pos", token=token) or []
            po = next((p for p in all_pos if p["award_id"] == award["award_id"]), None)
        if po:
            pos.append((po["po_no"], tenant_id))
            print(f"  awarded {rfq_no} → {winner} (PO {po['po_no']})")
    return pos


# ---------------------------------------------------------------------------
# Logistics shipment events
# ---------------------------------------------------------------------------


def add_shipment_events(po_numbers: list[tuple[str, str]]) -> None:
    """Push a couple of stage events on the first few sourcing POs so /logistics
    has something post-award beyond the legacy scenario rows.
    """

    print("\n=== shipment events on sourcing POs ===")
    seq = [
        ("manufacturing",     "Linz, AT",      "FAT scheduled at vendor works"),
        ("ready_to_dispatch", "Linz, AT",      "FAT cleared, awaiting export licence"),
        ("dispatched",        "Hamburg, DE",   "Loaded on MV Northern Wind"),
        ("in_transit",        "Suez Canal",    "Vessel transiting Suez"),
        ("at_port",           "JNPT, IN",      "Discharged at JNPT — pending customs"),
        ("at_customs",        "JNPT, IN",      "BIS clearance in progress"),
    ]
    # Every other PO, so each tenant gets some in-flight freight. Stage depth
    # comes from the PO number (not hash(), which is randomised per process)
    # so every `make demo` boot shows the same shipments.
    for po_no, tenant_id in po_numbers[::2]:
        token = _login(tenant_id)
        depth = int("".join(c for c in po_no if c.isdigit()) or 0) % len(seq) + 1
        for stage, location, note in seq[:depth]:
            evt = _req(
                "POST",
                f"/api/logistics/shipments/{po_no}/events",
                {"stage": stage, "location": location, "note": note},
                token=token,
            )
            if evt:
                print(f"  + {po_no} → {stage} @ {location}")


# ---------------------------------------------------------------------------
# Pending approvals
# ---------------------------------------------------------------------------


# A buyer proposes an alternate source for each tenant's single-source vendor.
# Buyers can't onboard vendors directly, so these land in the procurement
# head's /approvals queue — something to approve live in the demo.
PENDING_VENDORS = {
    "northwind": {
        "name": "GE Vernova Hydro", "category": "Hydro turbine and accessories",
        "country": "France", "lead_time_days": 330, "on_time_delivery_pct": 91.0,
        "quality_ppm": 260, "annual_spend_usd": 0, "approved_alternatives": 1,
    },
    "helios": {
        "name": "Oceaneering Connectors", "category": "ROV connectors",
        "country": "Norway", "lead_time_days": 120, "on_time_delivery_pct": 93.0,
        "quality_ppm": 210, "annual_spend_usd": 0, "approved_alternatives": 1,
    },
}


def file_pending_approvals() -> None:
    print("\n=== buyer vendor proposals (pending head approval) ===")
    for tenant_id, vendor in PENDING_VENDORS.items():
        reply = _req("POST", "/api/vendors", vendor, token=_login(tenant_id, "buyer"))
        approval = (reply or {}).get("approval") or {}
        print(f"  {tenant_id:10} {vendor['name']} → {(reply or {}).get('status')} {approval.get('approval_id', '')}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    # Sanity: backend up
    health = _req("GET", "/api/health")
    if not health or health.get("status") != "ok":
        print("backend not reachable on :8010")
        sys.exit(1)

    print("=== closing out existing RFQs ===")
    existing_pos = close_out_existing_rfqs()

    print("\n=== walking new sourcing workflows ===")
    new_pos: list[tuple[str, str]] = []
    for w in WORKFLOWS:
        po_no = walk_workflow(
            project_id=w["project_id"],
            bom_item_id=w["bom_item_id"],
            code=w["code"],
            description=w["description"],
            quantity=w["quantity"],
            quotes=w["quotes"],
            award_pref=w.get("award"),
            price_factor=w.get("price_factor", 1.0),
            need_in_days=w.get("need_in_days"),
        )
        if po_no:
            new_pos.append((po_no, TENANT_FOR_PROJECT[w["project_id"]]))

    add_shipment_events(existing_pos + new_pos)
    file_pending_approvals()

    # Final tally — reads are tenant-scoped, so report per tenant.
    for tenant_id in sorted({t for t in TENANT_FOR_PROJECT.values()}):
        token = _login(tenant_id)
        final_prs   = _req("GET", "/api/prs", token=token) or []
        final_rfqs  = _req("GET", "/api/rfqs", token=token) or []
        final_aw    = _req("GET", "/api/awards", token=token) or []
        final_pos   = _req("GET", "/api/sourcing-pos", token=token) or []
        final_ship  = _req("GET", "/api/logistics/shipments", token=token) or {"shipments": []}
        final_comm  = _req("GET", "/api/commercial/summary", token=token) or {}
        print(f"\n=== final tally ({tenant_id}) ===")
        print(f"  PRs            : {len(final_prs)}")
        print(f"  RFQs           : {len(final_rfqs)}")
        print(f"  Awards         : {len(final_aw)}")
        print(f"  Sourcing POs   : {len(final_pos)}")
        print(f"  Shipments      : {len(final_ship.get('shipments', []))}")
        print(
            f"  Commercial     : USD {final_comm.get('total_awarded_usd', 0):>12,.0f} "
            f"awarded · USD {final_comm.get('total_savings_usd', 0):>10,.0f} savings"
        )


if __name__ == "__main__":
    main()
