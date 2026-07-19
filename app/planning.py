"""Project Procurement Planner module.

Owns:
- In-memory store of demo projects, documents, and BOM items
- CSV upload + parse for BOM data
- Procurement-plan builder with long-lead detection and missing-spec flags

Storage is module-level dicts for MVP; the shape is intentionally close to what
a real persistence layer would expose so swapping in SQLite/Postgres later is a
single-module change.
"""

from __future__ import annotations

from ._cache import invalidates_cache

import csv
import io
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Tuple

from .schemas import (
    BOMItem,
    BomUploadResult,
    Document,
    Milestone,
    PlanFlag,
    PlanSummary,
    ProcurementPackage,
    ProcurementPlan,
    Project,
    ProjectProgress,
)


LONG_LEAD_THRESHOLD_DAYS = 90


# --- In-memory store ---------------------------------------------------------


_projects: Dict[str, Project] = {}
_documents: Dict[str, Document] = {}
_bom_items: Dict[str, Dict[str, BOMItem]] = defaultdict(dict)  # project_id -> item_id -> item


def _today() -> date:
    return date.today()


def _seed() -> None:
    if _projects:
        # Snapshot may pre-date Hydro being part of the cold seed (upgrade
        # path) — top it up idempotently and return.
        _ensure_hydro_loaded()
        _migrate_tenant_tags()
        _ensure_extra_projects_loaded()
        _ensure_inflight_projects_loaded()
        return

    today = _today()

    def d(days: int) -> date:
        from datetime import timedelta
        return today + timedelta(days=days)

    # --- Project 1: Riverbank Power Plant ------------------------------------
    rb = Project(
        project_id="PRJ-RB-660",
        name="Riverbank 2x660 MW Power Plant",
        client="Arcforge Power",
        site="Riverbank, Gujarat",
        sector="Power EPC",
        start_date=d(-120),
        milestones=[
            Milestone(code="M1", name="Engineering freeze", phase="engineering", required_on_site_date=d(30)),
            Milestone(code="M2", name="Long-lead orders placed", phase="procurement", required_on_site_date=d(45)),
            Milestone(code="M3", name="Mechanical erection start", phase="installation", required_on_site_date=d(120)),
            Milestone(code="M4", name="Hydro test", phase="commissioning", required_on_site_date=d(210)),
        ],
    )

    rb_docs = [
        Document(doc_id="DRG-RB-001", kind="drawing", title="GA - Boiler feed pump", version="B"),
        Document(doc_id="DRG-RB-002", kind="drawing", title="GA - 16in gate valve"),
        Document(doc_id="SPEC-RB-001", kind="spec", title="Datasheet - BFP 660MW", version="C"),
        Document(doc_id="SPEC-RB-002", kind="spec", title="Valve spec - forged gate A105"),
        Document(doc_id="QAP-RB-001", kind="QAP", title="QAP - Rotating equipment"),
    ]
    for doc in rb_docs:
        _documents[doc.doc_id] = doc

    rb_items = [
        BOMItem(
            bom_item_id="RB-001",
            project_id=rb.project_id,
            level=1,
            code="BFP-660-A",
            description="Boiler Feed Pump 660MW set A",
            category="Rotating equipment",
            quantity=2,
            uom="EA",
            unit_cost_usd=920000,
            supplier_name="Helios Cast & Forge",
            spec_doc_id="SPEC-RB-001",
            drawing_id="DRG-RB-001",
            long_lead_days=240,
            planned_need_date=d(120),
            milestone_code="M3",
            status="planned",
        ),
        BOMItem(
            bom_item_id="RB-002",
            project_id=rb.project_id,
            level=1,
            code="VALVE-16-A105",
            description="16 inch forged gate valve",
            category="Forged valves",
            quantity=30,
            uom="EA",
            unit_cost_usd=3850,
            supplier_name="Helios Cast & Forge",
            spec_doc_id="SPEC-RB-002",
            drawing_id="DRG-RB-002",
            long_lead_days=95,
            planned_need_date=d(90),
            milestone_code="M3",
            status="ordered",
        ),
        BOMItem(
            bom_item_id="RB-003",
            project_id=rb.project_id,
            level=1,
            code="PLC-S7-IO48",
            description="PLC I/O module 48 point",
            category="Automation",
            quantity=16,
            uom="EA",
            unit_cost_usd=2250,
            supplier_name="BluePeak Controls",
            spec_doc_id=None,
            drawing_id=None,
            long_lead_days=55,
            planned_need_date=d(70),
            milestone_code="M2",
            status="spec_missing",
        ),
        BOMItem(
            bom_item_id="RB-004",
            project_id=rb.project_id,
            level=1,
            code="TXF-110-40",
            description="Auxiliary transformer 110/11 kV 40 MVA",
            category="Electrical",
            quantity=1,
            uom="EA",
            unit_cost_usd=480000,
            supplier_name=None,
            spec_doc_id=None,
            drawing_id=None,
            long_lead_days=180,
            planned_need_date=d(100),
            milestone_code="M3",
            status="spec_missing",
        ),
        BOMItem(
            bom_item_id="RB-005",
            project_id=rb.project_id,
            level=1,
            code="BUSBAR-CU-40",
            description="Copper busbar 40 mm",
            category="Electrical",
            quantity=140,
            uom="M",
            unit_cost_usd=92,
            supplier_name="Copperline Metals",
            spec_doc_id="SPEC-RB-002",
            long_lead_days=28,
            planned_need_date=d(65),
            milestone_code="M2",
            status="planned",
        ),
        BOMItem(
            bom_item_id="RB-006",
            project_id=rb.project_id,
            level=1,
            code="STRUCT-S355",
            description="Structural steel S355 fabrication",
            category="Fabrication",
            quantity=220,
            uom="T",
            unit_cost_usd=1850,
            supplier_name=None,
            spec_doc_id="SPEC-RB-001",
            long_lead_days=60,
            planned_need_date=d(80),
            milestone_code="M3",
            status="planned",
        ),
        BOMItem(
            bom_item_id="RB-007",
            project_id=rb.project_id,
            level=1,
            code="COND-TUBE-INC",
            description="Condenser tubes Inconel 625",
            category="Tubing",
            quantity=4200,
            uom="M",
            unit_cost_usd=48,
            supplier_name=None,
            spec_doc_id=None,
            long_lead_days=150,
            planned_need_date=d(110),
            milestone_code="M3",
            status="spec_missing",
        ),
        BOMItem(
            bom_item_id="RB-008",
            project_id=rb.project_id,
            level=1,
            code="COOLING-TWR-MOD",
            description="Induced draft cooling tower module",
            category="Cooling",
            quantity=4,
            uom="EA",
            unit_cost_usd=310000,
            supplier_name=None,
            spec_doc_id="SPEC-RB-001",
            long_lead_days=210,
            planned_need_date=d(180),
            milestone_code="M4",
            status="planned",
        ),
    ]
    for item in rb_items:
        _bom_items[rb.project_id][item.bom_item_id] = item
    _projects[rb.project_id] = rb

    # --- Project 2: North Sea Offshore Substation (Helios) ------------------
    oss = Project(
        project_id="PRJ-NS-OSS",
        tenant_id="helios",
        name="North Sea Offshore Substation",
        client="Helios Offshore Operations",
        site="Aberdeen, UK",
        sector="Offshore Engineering",
        currency="USD",
        start_date=d(-60),
        milestones=[
            Milestone(code="M1", name="Engineering freeze", phase="engineering", required_on_site_date=d(45)),
            Milestone(code="M2", name="Long-lead orders placed", phase="procurement", required_on_site_date=d(60)),
            Milestone(code="M3", name="Quayside load-out", phase="delivery", required_on_site_date=d(180)),
        ],
    )

    oss_docs = [
        Document(doc_id="DRG-NS-001", tenant_id="helios", kind="drawing", title="GA - Switchgear 33kV"),
        Document(doc_id="SPEC-NS-001", tenant_id="helios", kind="spec", title="Subsea cable spec 66kV"),
    ]
    for doc in oss_docs:
        _documents[doc.doc_id] = doc

    oss_items = [
        BOMItem(
            bom_item_id="NS-001",
            tenant_id="helios",
            project_id=oss.project_id,
            level=1,
            code="SWG-33-GIS",
            description="Gas-insulated switchgear 33kV",
            category="Electrical",
            quantity=2,
            uom="EA",
            unit_cost_usd=640000,
            supplier_name="BluePeak Controls",
            spec_doc_id=None,
            drawing_id="DRG-NS-001",
            long_lead_days=200,
            planned_need_date=d(140),
            milestone_code="M3",
            status="spec_missing",
        ),
        BOMItem(
            bom_item_id="NS-002",
            tenant_id="helios",
            project_id=oss.project_id,
            level=1,
            code="CBL-66-SUBSEA",
            description="Subsea export cable 66kV XLPE",
            category="Cables",
            quantity=28,
            uom="KM",
            unit_cost_usd=215000,
            supplier_name=None,
            spec_doc_id="SPEC-NS-001",
            long_lead_days=320,
            planned_need_date=d(160),
            milestone_code="M3",
            status="planned",
        ),
        BOMItem(
            bom_item_id="NS-003",
            tenant_id="helios",
            project_id=oss.project_id,
            level=1,
            code="JACKET-STEEL",
            description="Jacket fabrication carbon steel",
            category="Fabrication",
            quantity=1,
            uom="EA",
            unit_cost_usd=4200000,
            supplier_name=None,
            spec_doc_id=None,
            long_lead_days=180,
            planned_need_date=d(150),
            milestone_code="M3",
            status="spec_missing",
        ),
        BOMItem(
            bom_item_id="NS-004",
            tenant_id="helios",
            project_id=oss.project_id,
            level=1,
            code="J-TUBE-SS",
            description="J-tube stainless 316L",
            category="Tubing",
            quantity=6,
            uom="EA",
            unit_cost_usd=38000,
            supplier_name="Copperline Metals",
            spec_doc_id="SPEC-NS-001",
            long_lead_days=65,
            planned_need_date=d(120),
            milestone_code="M3",
            status="planned",
        ),
    ]
    for item in oss_items:
        _bom_items[oss.project_id][item.bom_item_id] = item
    _projects[oss.project_id] = oss

    # --- Project 3: Mahadev Hydro 220 MW ------------------------------------
    _ensure_hydro_loaded()

    # --- Projects 4-9: two more per tenant (lighter BOMs) -------------------
    _ensure_extra_projects_loaded()

    # --- Projects 10-12: one in-execution (~55% complete) per tenant --------
    _ensure_inflight_projects_loaded()


def _migrate_tenant_tags() -> None:
    """One-shot upgrade for snapshots that pre-date M7.2 tenant tagging.

    Old snapshots have everything tagged "arcforge" by the schema default.
    Re-tag the seeded entities to their intended tenants so existing Fly /
    Compose deployments don't need a volume wipe to pick up M7.2 isolation.
    """
    HELIOS = {"PRJ-NS-OSS"}
    NORTHWIND = {"HYD-MAHADEV-220"}
    target_for_project: dict[str, str] = {pid: "helios" for pid in HELIOS}
    target_for_project.update({pid: "northwind" for pid in NORTHWIND})

    for project_id, target in target_for_project.items():
        proj = _projects.get(project_id)
        if proj is not None and proj.tenant_id != target:
            proj.tenant_id = target
        # Re-tag BOM items to match their parent project.
        for item in _bom_items.get(project_id, {}).values():
            if item.tenant_id != target:
                item.tenant_id = target

    # Documents follow their owning tenant (best effort by prefix).
    for doc in _documents.values():
        if doc.doc_id.startswith(("DRG-NS-", "SPEC-NS-")) and doc.tenant_id != "helios":
            doc.tenant_id = "helios"


def _ensure_extra_projects_loaded() -> None:
    """Add 2 secondary projects per tenant (idempotent).

    M7.2 split the 3 original projects 1-per-tenant, leaving each tenant with a
    single project. This fleshes the demo out to ~3 projects each. Light BOMs
    (5 lines) keep the seed compact. Idempotent — existing snapshots get topped
    up on the next call without a volume wipe.
    """
    today = _today()

    def d(days: int) -> date:
        from datetime import timedelta
        return today + timedelta(days=days)

    def ms(code: str, name: str, phase: str, days: int) -> Milestone:
        return Milestone(code=code, name=name, phase=phase, required_on_site_date=d(days))

    # (project_id, tenant_id, name, client, site, sector, milestones, bom rows)
    # bom row = (code, description, category, qty, uom, unit_cost, supplier, long_lead, ms_code, status)
    specs = [
        # ---- Arcforge (Power Systems EPC) ----
        ("PRJ-AF-CCGT", "arcforge", "Tanjore Combined-Cycle Gas Plant 750 MW",
         "Arcforge Power", "Tanjore, Tamil Nadu", "Power EPC",
         [ms("M1", "Engineering freeze", "engineering", 40),
          ms("M2", "Long-lead orders placed", "procurement", 70),
          ms("M3", "Mechanical erection", "installation", 160)],
         [("GT-9F-FRAME", "Gas turbine 9F frame unit", "Rotating equipment", 2, "EA", 4200000, "Helios Cast & Forge", 365, "M3", "planned"),
          ("HRSG-3P-RH", "Triple-pressure HRSG with reheat", "Heat recovery", 2, "EA", 2800000, None, 300, "M3", "spec_missing"),
          ("STG-250", "Steam turbine generator 250 MW", "Rotating equipment", 1, "EA", 3100000, "Helios Cast & Forge", 330, "M3", "planned"),
          ("GSU-XFMR-420", "Generator step-up transformer 420 MVA", "Electrical", 2, "EA", 880000, None, 240, "M2", "spec_missing"),
          ("DCS-CONTROL", "Distributed control system", "Automation", 1, "LOT", 1200000, "BluePeak Controls", 120, "M2", "planned")]),
        ("PRJ-AF-SUB", "arcforge", "Sundarpur 765 kV Substation Upgrade",
         "Arcforge Grid", "Sundarpur, Madhya Pradesh", "Transmission EPC",
         [ms("M1", "Design approval", "engineering", 35),
          ms("M2", "Equipment delivery", "delivery", 90),
          ms("M3", "Energization", "commissioning", 200)],
         [("GIS-765", "765 kV gas-insulated switchgear bay", "Electrical", 6, "EA", 1450000, "BluePeak Controls", 280, "M2", "planned"),
          ("ICT-1000", "Interconnecting transformer 1000 MVA", "Electrical", 3, "EA", 2600000, None, 320, "M2", "spec_missing"),
          ("REACTOR-330", "Shunt reactor 330 MVAr", "Electrical", 3, "EA", 980000, "Copperline Metals", 210, "M2", "planned"),
          ("BUSBAR-ACSR", "ACSR bundled conductor", "Electrical", 18, "KM", 42000, "Copperline Metals", 60, "M3", "planned"),
          ("PROT-RELAY", "Numerical protection relay panel", "Automation", 24, "EA", 18000, "Mitsuba Automation", 90, "M3", "planned")]),
        # ---- Helios (Offshore Engineering) ----
        ("PRJ-HE-WIND", "helios", "Dogger Bank Offshore Wind 480 MW",
         "Helios Renewables", "Dogger Bank, North Sea", "Offshore Wind EPC",
         [ms("M1", "Foundation design freeze", "engineering", 50),
          ms("M2", "Monopile fabrication", "fabrication", 120),
          ms("M3", "Turbine installation campaign", "installation", 240)],
         [("MONOPILE-XL", "XL monopile foundation", "Offshore structural", 32, "EA", 3400000, "Aberdeen Steel Fab", 300, "M2", "planned"),
          ("WTG-12MW", "12 MW offshore wind turbine", "Rotating equipment", 40, "EA", 14500000, None, 420, "M3", "spec_missing"),
          ("ARRAY-66KV", "66 kV inter-array cable", "Subsea cables", 85, "KM", 220000, "NorthCable Subsea", 240, "M3", "planned"),
          ("TP-COATING", "Transition piece marine coating", "Marine epoxy", 32, "LOT", 64000, "Coastline Marine Coatings", 45, "M2", "planned"),
          ("ROV-WETMATE", "ROV wet-mate connector set", "ROV connectors", 48, "EA", 4800, "DeepDive ROV Systems", 84, "M3", "planned")]),
        ("PRJ-HE-FPSO", "helios", "Hawthorn FPSO Topsides",
         "Helios Upstream", "West of Shetland", "Offshore Oil & Gas EPC",
         [ms("M1", "Topsides FEED complete", "engineering", 45),
          ms("M2", "Module fabrication", "fabrication", 140),
          ms("M3", "Integration + sail-away", "installation", 300)],
         [("SEP-TRAIN", "3-phase separation train", "Process", 2, "EA", 5600000, None, 360, "M2", "spec_missing"),
          ("GASCOMP-CENT", "Centrifugal gas compressor", "Rotating equipment", 3, "EA", 4100000, "Aberdeen Steel Fab", 330, "M2", "planned"),
          ("SWIVEL-STACK", "Fluid swivel stack", "Process", 1, "EA", 7800000, None, 400, "M3", "spec_missing"),
          ("FLARE-BOOM", "Flare boom structure", "Offshore structural", 1, "EA", 2200000, "Aberdeen Steel Fab", 180, "M2", "planned"),
          ("RISER-FLEX", "Flexible production riser", "Subsea cables", 6, "EA", 1450000, "NorthCable Subsea", 270, "M3", "planned")]),
        # ---- Northwind (Heavy Engineering) ----
        ("PRJ-NW-STEEL", "northwind", "Polaris Steel Rolling Mill Modernization",
         "Polaris Steel", "Jamshedpur, Jharkhand", "Heavy Industry EPC",
         [ms("M1", "Basic engineering", "engineering", 40),
          ms("M2", "Mill equipment delivery", "delivery", 130),
          ms("M3", "Hot commissioning", "commissioning", 260)],
         [("ROLL-STAND-6H", "6-high cold rolling stand", "Heavy machinery", 4, "EA", 3900000, "ThyssenKrupp Specialty Plate", 360, "M2", "planned"),
          ("REHEAT-FURN", "Walking-beam reheat furnace", "Furnace", 1, "EA", 6200000, None, 330, "M2", "spec_missing"),
          ("COILER-DOWN", "Downcoiler assembly", "Heavy machinery", 2, "EA", 2100000, "Voith Industrial Services", 280, "M3", "planned"),
          ("DRIVE-MV", "MV variable-speed mill drive", "Automation", 8, "EA", 480000, "Bharat Heavy Electricals", 210, "M3", "planned"),
          ("WORKROLL-FORGED", "Forged work roll set", "Alloy plate", 24, "EA", 95000, "ThyssenKrupp Specialty Plate", 150, "M3", "planned")]),
        ("PRJ-NW-CEMENT", "northwind", "Granite Ridge Cement Line 2",
         "Granite Ridge Cement", "Chandrapur, Maharashtra", "Heavy Industry EPC",
         [ms("M1", "Process design freeze", "engineering", 35),
          ms("M2", "Kiln + mill delivery", "delivery", 140),
          ms("M3", "Performance guarantee run", "commissioning", 270)],
         [("KILN-5000TPD", "Rotary kiln 5000 TPD", "Heavy machinery", 1, "EA", 8400000, None, 390, "M2", "spec_missing"),
          ("VRM-RAW", "Vertical raw mill", "Heavy machinery", 1, "EA", 4600000, "Voith Industrial Services", 330, "M2", "planned"),
          ("PREHEAT-TWR", "5-stage preheater tower", "Process", 1, "EA", 3700000, None, 300, "M2", "spec_missing"),
          ("CLINKER-COOL", "Grate clinker cooler", "Process", 1, "EA", 2400000, "ThyssenKrupp Specialty Plate", 240, "M3", "planned"),
          ("BAGHOUSE-PULSE", "Pulse-jet baghouse filter", "Environmental", 2, "EA", 680000, "Bharat Heavy Electricals", 120, "M3", "planned")]),
    ]

    for (pid, tenant, name, client, site, sector, milestones, rows) in specs:
        if pid in _projects:
            continue
        _projects[pid] = Project(
            project_id=pid,
            tenant_id=tenant,
            name=name,
            client=client,
            site=site,
            sector=sector,
            start_date=d(-30),
            milestones=milestones,
        )
        for idx, (code, desc, cat, qty, uom, cost, supplier, lead, mcode, status) in enumerate(rows, start=1):
            item_id = f"{pid}-{idx:03d}"
            _bom_items[pid][item_id] = BOMItem(
                bom_item_id=item_id,
                tenant_id=tenant,
                project_id=pid,
                level=1,
                code=code,
                description=desc,
                category=cat,
                quantity=qty,
                uom=uom,
                unit_cost_usd=cost,
                supplier_name=supplier,
                long_lead_days=lead,
                planned_need_date=d(lead // 2),
                milestone_code=mcode,
                status=status,
            )


def _ensure_inflight_projects_loaded() -> None:
    """Add one in-execution (~55% complete) project per tenant (idempotent).

    These start well in the past, have ~3/5 milestones already passed, and a
    BOM mix of delivered/ordered/planned lines so the blended completion
    metric lands in the 50-60% band — demonstrating what a mid-flight project
    looks like across every module (delivered material, committed spend,
    schedule burn-down) rather than greenfield planning.
    """
    today = _today()

    def d(days: int) -> date:
        from datetime import timedelta
        return today + timedelta(days=days)

    def ms(code: str, name: str, phase: str, days: int) -> Milestone:
        return Milestone(code=code, name=name, phase=phase, required_on_site_date=d(days))

    # 5 milestones each, 2 in the past (-300/-200) + 3 future = 40% schedule.
    # Long-lead equipment is delivered (ordered at M2) but the "bulk material
    # on site" milestone (M3) hasn't been certified yet — keeps the blended
    # completion in the 50-60% band.
    def milestones() -> List[Milestone]:
        return [
            ms("M1", "Engineering freeze", "engineering", -300),
            ms("M2", "Long-lead orders placed", "procurement", -200),
            ms("M3", "Bulk material on site", "delivery", 20),
            ms("M4", "Mechanical completion", "installation", 90),
            ms("M5", "Commissioning + handover", "commissioning", 200),
        ]

    # bom row = (code, description, category, qty, uom, unit_cost, supplier, long_lead, ms_code, status)
    # 9 lines each: 5 delivered + 1 ordered + 3 planned -> ~56% delivered.
    specs = [
        ("PRJ-AF-MERIDIAN", "arcforge", "Meridian 2x350 MW CCGT — Unit 1 Execution",
         "Arcforge Power", "Meridian, Andhra Pradesh", "Power EPC",
         [("GT-7HA-CORE", "Gas turbine 7HA core", "Rotating equipment", 2, "EA", 3800000, "Helios Cast & Forge", 365, "M2", "delivered"),
          ("HRSG-MOD-A", "HRSG pressure modules", "Heat recovery", 4, "EA", 1200000, "Helios Cast & Forge", 300, "M3", "delivered"),
          ("COND-SHELL", "Surface condenser shell", "Process", 1, "EA", 980000, "Kerala Forge Works", 210, "M3", "delivered"),
          ("FW-PUMP-MV", "Boiler feed pump + MV motor", "Rotating equipment", 3, "EA", 540000, "Helios Cast & Forge", 180, "M3", "delivered"),
          ("CABLE-MV-TRAY", "MV cable + tray bulk", "Electrical", 12, "KM", 88000, "Copperline Metals", 60, "M3", "delivered"),
          ("GSU-XFMR-300", "Generator step-up transformer 300 MVA", "Electrical", 2, "EA", 760000, "BluePeak Controls", 240, "M4", "ordered"),
          ("DCS-MERIDIAN", "DCS + field instrumentation", "Automation", 1, "LOT", 1100000, "BluePeak Controls", 120, "M4", "planned"),
          ("STACK-CEMS", "Stack + CEMS package", "Environmental", 2, "EA", 420000, None, 150, "M4", "planned"),
          ("AUX-COOLING", "Auxiliary cooling water system", "Cooling", 1, "LOT", 680000, "Mitsuba Automation", 90, "M5", "planned")]),
        ("PRJ-HE-VALHALL", "helios", "Valhall Bravo Platform Tie-In",
         "Helios Upstream", "Valhall Field, North Sea", "Offshore Oil & Gas EPC",
         [("SUBSEA-MANIFOLD", "Subsea production manifold", "Process", 1, "EA", 4200000, "Aberdeen Steel Fab", 360, "M2", "delivered"),
          ("UMBILICAL-STATIC", "Static control umbilical", "Subsea cables", 8, "KM", 310000, "NorthCable Subsea", 300, "M3", "delivered"),
          ("XMAS-TREE-HT", "High-temp subsea tree", "Process", 2, "EA", 2600000, None, 330, "M3", "delivered"),
          ("ROV-TIEIN-KIT", "ROV tie-in tooling kit", "ROV connectors", 4, "EA", 185000, "DeepDive ROV Systems", 84, "M3", "delivered"),
          ("COAT-SPLASH", "Splash-zone coating package", "Marine epoxy", 6, "LOT", 96000, "Coastline Marine Coatings", 45, "M3", "delivered"),
          ("RISER-FLEX-DYN", "Dynamic flexible riser", "Subsea cables", 3, "EA", 1450000, "NorthCable Subsea", 270, "M4", "ordered"),
          ("PIG-LAUNCHER", "Subsea pig launcher", "Process", 1, "EA", 720000, "Aberdeen Steel Fab", 150, "M4", "planned"),
          ("CP-ANODE-SLED", "Cathodic protection anode sled", "Offshore structural", 5, "EA", 64000, None, 120, "M4", "planned"),
          ("CTRL-MODULE-SC", "Subsea control module", "Automation", 2, "EA", 880000, "DeepDive ROV Systems", 180, "M5", "planned")]),
        ("PRJ-NW-KAVI", "northwind", "Kavi Hydro Unit 3 Major Overhaul",
         "Northern Hills Power Corporation", "Kavi, Himachal Pradesh", "Hydropower EPC",
         [("RUNNER-REFURB", "Francis runner refurbishment", "Hydro turbines", 1, "EA", 1900000, "Andritz Hydro", 300, "M2", "delivered"),
          ("GEN-REWIND", "Generator stator rewind", "Generators", 1, "EA", 1450000, "Bharat Heavy Electricals", 270, "M3", "delivered"),
          ("WICKET-GATE", "Wicket gate assembly set", "Hydro turbines", 24, "EA", 48000, "Andritz Hydro", 180, "M3", "delivered"),
          ("DRAFT-TUBE-LIN", "Draft tube liner plate", "Alloy plate", 60, "T", 2400, "ThyssenKrupp Specialty Plate", 120, "M3", "delivered"),
          ("GOV-HYDRAULIC", "Digital governor + hydraulics", "Automation", 1, "LOT", 620000, "Voith Industrial Services", 150, "M3", "delivered"),
          ("XFMR-GEN-90", "Generator transformer 90 MVA", "Electrical", 1, "EA", 540000, "Bharat Heavy Electricals", 240, "M4", "ordered"),
          ("PENSTOCK-LINER", "Penstock liner segments", "Penstock fabrication", 8, "EA", 210000, "Voith Industrial Services", 210, "M4", "planned"),
          ("EXCITER-STATIC", "Static excitation system", "Automation", 1, "EA", 380000, None, 120, "M4", "planned"),
          ("COOLING-WTR-PMP", "Cooling water pump set", "Rotating equipment", 2, "EA", 145000, "Voith Industrial Services", 90, "M5", "planned")]),
    ]

    for (pid, tenant, name, client, site, sector, rows) in specs:
        if pid in _projects:
            continue
        _projects[pid] = Project(
            project_id=pid,
            tenant_id=tenant,
            name=name,
            client=client,
            site=site,
            sector=sector,
            start_date=d(-400),
            milestones=milestones(),
        )
        for idx, (code, desc, cat, qty, uom, cost, supplier, lead, mcode, status) in enumerate(rows, start=1):
            item_id = f"{pid}-{idx:03d}"
            # Delivered/ordered lines already have specs; planned ones may not.
            spec_id = f"SPEC-{pid[-4:]}-{idx:02d}" if status in ("delivered", "ordered") else None
            _bom_items[pid][item_id] = BOMItem(
                bom_item_id=item_id,
                tenant_id=tenant,
                project_id=pid,
                level=1,
                code=code,
                description=desc,
                category=cat,
                quantity=qty,
                uom=uom,
                unit_cost_usd=cost,
                supplier_name=supplier,
                spec_doc_id=spec_id,
                long_lead_days=lead,
                planned_need_date=d(lead - 200),  # backdated; many already due
                milestone_code=mcode,
                status=status if (spec_id or status != "planned") else "spec_missing",
            )


def _ensure_hydro_loaded() -> None:
    """Load the Mahadev Hydro fixture into the planning store if missing.

    Pulled from the fixtures package so every cold boot (local, Compose, Fly)
    gets the same three projects. Previously this only loaded under
    `make demo` via serve_with_hydro.py, so production saw 2 projects while
    the topbar said 6. Idempotent so older snapshots (RB+OSS only) get
    topped up at the next call.
    """
    if "HYD-MAHADEV-220" in _projects:
        return
    try:
        from fixtures.hydro.hydro_seed import build_hydro_demo
        hydro = build_hydro_demo()
        # Override tenant_id — hydro fixture pre-dates M7.2 and bakes in
        # "arcforge" via the schema default. Mahadev Hydro belongs to
        # Northwind under the new multi-tenant seed.
        hydro.project.tenant_id = "northwind"
        _projects[hydro.project.project_id] = hydro.project
        for item in hydro.bom_items:
            item.tenant_id = "northwind"
            _bom_items[hydro.project.project_id][item.bom_item_id] = item
    except Exception:
        # Fixture is optional — tests / minimal envs may not ship fixtures/.
        pass


# --- Public API --------------------------------------------------------------


@invalidates_cache
def upsert_project(project: Project) -> Project:
    """Insert or replace a project (used by the ingest engine)."""
    _seed()
    _projects[project.project_id] = project
    return project


@invalidates_cache
def upsert_bom_item(item: BOMItem) -> BOMItem:
    """Insert or replace a BOM line (used by the ingest engine)."""
    _seed()
    _bom_items[item.project_id][item.bom_item_id] = item
    return item


@invalidates_cache
def patch_bom_item(
    project_id: str,
    bom_item_id: str,
    *,
    category: Optional[str] = None,
    supplier_name: Optional[str] = None,
    update_category: bool = False,
    update_supplier: bool = False,
    tenant_id: Optional[str] = None,
) -> Optional[BOMItem]:
    """Apply a partial update to one BOM line (autofill apply path)."""
    _seed()
    if get_project(project_id, tenant_id=tenant_id) is None:
        return None
    item = _bom_items.get(project_id, {}).get(bom_item_id)
    if item is None:
        return None
    if tenant_id is not None and item.tenant_id != tenant_id:
        return None
    updated = item.model_copy(deep=True)
    if update_category:
        updated.category = category
    if update_supplier:
        updated.supplier_name = supplier_name
    _bom_items[project_id][bom_item_id] = updated
    return updated


def list_projects(tenant_id: Optional[str] = None) -> List[Project]:
    """List projects, optionally filtered by tenant_id.

    When tenant_id is None we return everything (used by audit / system
    paths and pre-auth scenarios). When tenant_id is set, only projects
    owned by that tenant are returned.
    """
    _seed()
    if tenant_id is None:
        return list(_projects.values())
    return [p for p in _projects.values() if p.tenant_id == tenant_id]


def get_project(project_id: str, tenant_id: Optional[str] = None) -> Optional[Project]:
    _seed()
    p = _projects.get(project_id)
    if p is None:
        return None
    if tenant_id is not None and p.tenant_id != tenant_id:
        return None  # cross-tenant read denied — looks identical to "not found"
    return p


def get_bom(project_id: str, tenant_id: Optional[str] = None) -> List[BOMItem]:
    _seed()
    # Validate project belongs to the tenant first (transitive scoping).
    if tenant_id is not None:
        owner = _projects.get(project_id)
        if owner is None or owner.tenant_id != tenant_id:
            return []
    return list(_bom_items.get(project_id, {}).values())


def get_documents_by_ids(ids: List[str], tenant_id: Optional[str] = None) -> List[Document]:
    _seed()
    docs = [_documents[i] for i in ids if i in _documents]
    if tenant_id is None:
        return docs
    return [d for d in docs if d.tenant_id == tenant_id]


# --- Project progress (blended completion) -----------------------------------

# Blend weights — milestones (schedule), BOM delivered (physical), spend
# committed (commercial). Tunable; must sum to 1.0.
_PROGRESS_WEIGHTS = {"milestones": 0.40, "bom_delivered": 0.40, "spend_committed": 0.20}
_COMMITTED_STATUSES = {"ordered", "delivered"}


def compute_project_progress(
    project_id: str,
    tenant_id: Optional[str] = None,
) -> Optional[ProjectProgress]:
    """Blended completion for one project. Returns None if not found / cross-tenant."""
    _seed()
    project = _projects.get(project_id)
    if project is None or (tenant_id is not None and project.tenant_id != tenant_id):
        return None

    today = _today()
    milestones = project.milestones
    ms_total = len(milestones)
    ms_passed = sum(1 for m in milestones if m.required_on_site_date < today)
    ms_pct = (ms_passed / ms_total * 100) if ms_total else 0.0

    bom = list(_bom_items.get(project_id, {}).values())
    bom_total = len(bom)
    bom_delivered = sum(1 for b in bom if b.status == "delivered")
    bom_pct = (bom_delivered / bom_total * 100) if bom_total else 0.0

    def line_value(b: BOMItem) -> float:
        return (b.unit_cost_usd or 0) * b.quantity

    budget = sum(line_value(b) for b in bom)
    committed = sum(line_value(b) for b in bom if b.status in _COMMITTED_STATUSES)
    spend_pct = (committed / budget * 100) if budget else 0.0

    blended = round(
        _PROGRESS_WEIGHTS["milestones"] * ms_pct
        + _PROGRESS_WEIGHTS["bom_delivered"] * bom_pct
        + _PROGRESS_WEIGHTS["spend_committed"] * spend_pct,
        1,
    )

    return ProjectProgress(
        project_id=project_id,
        completion_pct=blended,
        milestones_pct=round(ms_pct, 1),
        bom_delivered_pct=round(bom_pct, 1),
        spend_committed_pct=round(spend_pct, 1),
        milestones_passed=ms_passed,
        milestones_total=ms_total,
        bom_delivered=bom_delivered,
        bom_total=bom_total,
        committed_value_usd=round(committed, 2),
        budget_value_usd=round(budget, 2),
    )


def list_project_progress(tenant_id: Optional[str] = None) -> List[ProjectProgress]:
    """Progress for every project the tenant owns."""
    _seed()
    out: List[ProjectProgress] = []
    for p in list_projects(tenant_id=tenant_id):
        prog = compute_project_progress(p.project_id, tenant_id=tenant_id)
        if prog is not None:
            out.append(prog)
    return out


# --- CSV upload --------------------------------------------------------------


_REQUIRED_CSV_HEADERS = {"code", "description", "quantity"}


@invalidates_cache
def upload_bom_csv(
    project_id: str,
    csv_text: str,
    tenant_id: Optional[str] = None,
) -> BomUploadResult:
    _seed()
    project = _projects.get(project_id)
    if project is None or (tenant_id is not None and project.tenant_id != tenant_id):
        return BomUploadResult(
            project_id=project_id,
            rows_parsed=0,
            rows_accepted=0,
            rows_rejected=0,
            errors=[f"Unknown project {project_id}"],
            bom_items=[],
        )

    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames or not _REQUIRED_CSV_HEADERS.issubset({h.strip() for h in reader.fieldnames}):
        return BomUploadResult(
            project_id=project_id,
            rows_parsed=0,
            rows_accepted=0,
            rows_rejected=0,
            errors=[f"CSV must have headers: {', '.join(sorted(_REQUIRED_CSV_HEADERS))}"],
            bom_items=[],
        )

    accepted: List[BOMItem] = []
    errors: List[str] = []
    rows_parsed = 0

    for idx, row in enumerate(reader, start=2):  # line 1 = header
        rows_parsed += 1
        code = (row.get("code") or "").strip()
        desc = (row.get("description") or "").strip()
        qty_raw = (row.get("quantity") or "").strip()

        if not code or not desc or not qty_raw:
            errors.append(f"row {idx}: missing code/description/quantity")
            continue
        try:
            qty = float(qty_raw)
        except ValueError:
            errors.append(f"row {idx}: quantity '{qty_raw}' is not a number")
            continue

        def opt_int(key: str) -> Optional[int]:
            v = (row.get(key) or "").strip()
            if not v:
                return None
            try:
                return int(float(v))
            except ValueError:
                return None

        def opt_float(key: str) -> Optional[float]:
            v = (row.get(key) or "").strip()
            if not v:
                return None
            try:
                return float(v)
            except ValueError:
                return None

        def opt_date(key: str) -> Optional[date]:
            v = (row.get(key) or "").strip()
            if not v:
                return None
            try:
                return date.fromisoformat(v)
            except ValueError:
                return None

        def opt(key: str) -> Optional[str]:
            v = (row.get(key) or "").strip()
            return v or None

        # Optional explicit status — only honored if it matches the BomStatus
        # literal; otherwise we fall back to the spec-driven default below so
        # malformed input cannot inject arbitrary status strings.
        _VALID_STATUSES = {
            "spec_missing", "planned", "requisitioned", "ordered", "delivered",
        }
        status_in = (opt("status") or "").lower()
        if status_in in _VALID_STATUSES:
            status_value = status_in
        else:
            status_value = "spec_missing" if not opt("spec_doc_id") else "planned"
            if opt("status") and status_in not in _VALID_STATUSES:
                errors.append(
                    f"row {idx}: unknown status '{opt('status')}' — using "
                    f"'{status_value}'"
                )

        item = BOMItem(
            bom_item_id=opt("bom_item_id") or f"{project_id}-U{idx:04d}",
            tenant_id=project.tenant_id,
            project_id=project_id,
            parent_item_id=opt("parent_item_id"),
            code=code,
            description=desc,
            category=opt("category"),
            quantity=qty,
            uom=opt("uom") or "EA",
            unit_cost_usd=opt_float("unit_cost_usd"),
            supplier_name=opt("supplier_name"),
            spec_doc_id=opt("spec_doc_id"),
            drawing_id=opt("drawing_id"),
            long_lead_days=opt_int("long_lead_days"),
            planned_need_date=opt_date("planned_need_date"),
            milestone_code=opt("milestone_code"),
            status=status_value,  # type: ignore[arg-type]
        )
        accepted.append(item)

    for item in accepted:
        _bom_items[project_id][item.bom_item_id] = item

    # Audit
    from .audit import emit
    emit(
        action="uploaded",
        entity_kind="project",
        entity_id=project_id,
        subject=project_id,
        summary=f"BOM CSV uploaded: {len(accepted)} accepted, {rows_parsed - len(accepted)} rejected",
        source="csv_upload",
        tenant_id=project.tenant_id,
        project_id=project_id,
        metadata={"rows_parsed": rows_parsed, "rows_accepted": len(accepted), "errors_count": len(errors)},
    )
    for item in accepted:
        emit(
            action="created",
            entity_kind="bom_item",
            entity_id=item.bom_item_id,
            subject=f"{item.code}",
            summary=(
                f"BOM line {item.code} · {item.description[:60]} · "
                f"{item.quantity} {item.uom}"
                + (f" · long-lead {item.long_lead_days}d" if item.long_lead_days else "")
                + (" · spec missing" if not item.spec_doc_id else "")
            ),
            source="csv_upload",
            tenant_id=project.tenant_id,
            project_id=project_id,
            bom_item_id=item.bom_item_id,
            bom_code=item.code,
            vendor=item.supplier_name,
            metadata={
                "category": item.category,
                "supplier": item.supplier_name,
                "spec_doc_id": item.spec_doc_id,
                "long_lead_days": item.long_lead_days,
                "milestone_code": item.milestone_code,
            },
        )

    return BomUploadResult(
        project_id=project_id,
        rows_parsed=rows_parsed,
        rows_accepted=len(accepted),
        rows_rejected=rows_parsed - len(accepted),
        errors=errors,
        bom_items=accepted,
    )


# --- Procurement plan builder ------------------------------------------------


def _milestone_map(project: Project) -> Dict[str, Milestone]:
    return {m.code: m for m in project.milestones}


def _nearest_milestone(
    project: Project, need_date: Optional[date]
) -> Optional[Milestone]:
    if need_date is None or not project.milestones:
        return None
    ordered = sorted(project.milestones, key=lambda m: m.required_on_site_date)
    for m in ordered:
        if m.required_on_site_date >= need_date:
            return m
    return ordered[-1]


def build_procurement_plan(
    project_id: str,
    tenant_id: Optional[str] = None,
) -> Optional[ProcurementPlan]:
    _seed()
    project = _projects.get(project_id)
    if not project:
        return None
    if tenant_id is not None and project.tenant_id != tenant_id:
        return None  # cross-tenant request — same response as missing project

    items = list(_bom_items.get(project_id, {}).values())
    milestones = _milestone_map(project)
    today = _today()

    # Assign each item to a milestone (use explicit milestone_code if set,
    # else nearest milestone by planned_need_date).
    by_milestone: Dict[str, List[BOMItem]] = defaultdict(list)
    for item in items:
        code: Optional[str] = item.milestone_code
        if not code or code not in milestones:
            nearest = _nearest_milestone(project, item.planned_need_date)
            code = nearest.code if nearest else "UNASSIGNED"
        by_milestone[code].append(item)

    packages: List[ProcurementPackage] = []
    for code, group in by_milestone.items():
        milestone = milestones.get(code)
        ms_date = milestone.required_on_site_date if milestone else today
        ms_name = milestone.name if milestone else "Unassigned"
        earliest = min(
            (i.planned_need_date for i in group if i.planned_need_date),
            default=None,
        )
        long_lead = sum(
            1
            for i in group
            if (i.long_lead_days or 0) >= LONG_LEAD_THRESHOLD_DAYS
        )
        missing_spec = sum(1 for i in group if not i.spec_doc_id)
        total_value = sum((i.unit_cost_usd or 0) * i.quantity for i in group)
        packages.append(
            ProcurementPackage(
                package_id=f"PKG-{project_id}-{code}",
                project_id=project_id,
                milestone_code=code,
                milestone_name=ms_name,
                required_on_site_date=ms_date,
                bom_item_ids=[i.bom_item_id for i in group],
                item_count=len(group),
                total_value_usd=round(total_value, 2),
                earliest_need_date=earliest,
                long_lead_count=long_lead,
                missing_spec_count=missing_spec,
            )
        )

    packages.sort(key=lambda p: p.required_on_site_date)

    long_lead_items: List[PlanFlag] = []
    missing_spec_items: List[PlanFlag] = []

    for item in items:
        days_until_need = (
            (item.planned_need_date - today).days if item.planned_need_date else None
        )
        long_lead = item.long_lead_days or 0
        if long_lead >= LONG_LEAD_THRESHOLD_DAYS:
            severity: str = "high"
            if days_until_need is not None and days_until_need < long_lead:
                severity = "critical"
            long_lead_items.append(
                PlanFlag(
                    bom_item_id=item.bom_item_id,
                    code=item.code,
                    description=item.description,
                    reason=(
                        f"Lead time {long_lead} days vs "
                        f"{days_until_need if days_until_need is not None else '—'} days to need-by. "
                        f"Order window is tight."
                    ),
                    severity=severity,  # type: ignore[arg-type]
                    milestone_code=item.milestone_code,
                    days_until_need=days_until_need,
                    long_lead_days=long_lead,
                )
            )

        if not item.spec_doc_id:
            missing_spec_items.append(
                PlanFlag(
                    bom_item_id=item.bom_item_id,
                    code=item.code,
                    description=item.description,
                    reason="No spec document linked. Engineering must release a spec before requisition.",
                    severity="high" if (item.long_lead_days or 0) >= LONG_LEAD_THRESHOLD_DAYS else "medium",
                    milestone_code=item.milestone_code,
                    days_until_need=days_until_need,
                    long_lead_days=item.long_lead_days,
                )
            )

    long_lead_items.sort(key=lambda f: (f.days_until_need is None, f.days_until_need or 0))
    missing_spec_items.sort(key=lambda f: (f.days_until_need is None, f.days_until_need or 0))

    earliest_need = min((i.planned_need_date for i in items if i.planned_need_date), default=None)
    latest_need = max((i.planned_need_date for i in items if i.planned_need_date), default=None)
    total_value = round(sum((i.unit_cost_usd or 0) * i.quantity for i in items), 2)

    summary = PlanSummary(
        bom_item_count=len(items),
        packages_count=len(packages),
        long_lead_count=len(long_lead_items),
        missing_spec_count=len(missing_spec_items),
        total_value_usd=total_value,
        earliest_need_date=earliest_need,
        latest_need_date=latest_need,
    )

    return ProcurementPlan(
        project_id=project_id,
        project_name=project.name,
        generated_at=datetime.now(timezone.utc),
        summary=summary,
        packages=packages,
        long_lead_items=long_lead_items,
        missing_spec_items=missing_spec_items,
        assumptions=[
            f"An item is flagged as long-lead when its supplier lead time is ≥ {LONG_LEAD_THRESHOLD_DAYS} days.",
            "BOM items without a linked spec document are treated as blocked for requisition.",
            "Items are grouped to the milestone explicitly set on the row; otherwise the earliest milestone after the planned need-date.",
        ],
    )
