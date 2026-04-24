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

    # --- Project 2: North Sea Offshore Substation ----------------------------
    oss = Project(
        project_id="PRJ-NS-OSS",
        name="North Sea Offshore Substation",
        client="Arcforge Offshore",
        site="Aberdeen, UK",
        sector="Offshore EPC",
        currency="USD",
        start_date=d(-60),
        milestones=[
            Milestone(code="M1", name="Engineering freeze", phase="engineering", required_on_site_date=d(45)),
            Milestone(code="M2", name="Long-lead orders placed", phase="procurement", required_on_site_date=d(60)),
            Milestone(code="M3", name="Quayside load-out", phase="delivery", required_on_site_date=d(180)),
        ],
    )

    oss_docs = [
        Document(doc_id="DRG-NS-001", kind="drawing", title="GA - Switchgear 33kV"),
        Document(doc_id="SPEC-NS-001", kind="spec", title="Subsea cable spec 66kV"),
    ]
    for doc in oss_docs:
        _documents[doc.doc_id] = doc

    oss_items = [
        BOMItem(
            bom_item_id="NS-001",
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


# --- Public API --------------------------------------------------------------


def list_projects() -> List[Project]:
    _seed()
    return list(_projects.values())


def get_project(project_id: str) -> Optional[Project]:
    _seed()
    return _projects.get(project_id)


def get_bom(project_id: str) -> List[BOMItem]:
    _seed()
    return list(_bom_items.get(project_id, {}).values())


def get_documents_by_ids(ids: List[str]) -> List[Document]:
    _seed()
    return [_documents[i] for i in ids if i in _documents]


# --- CSV upload --------------------------------------------------------------


_REQUIRED_CSV_HEADERS = {"code", "description", "quantity"}


def upload_bom_csv(project_id: str, csv_text: str) -> BomUploadResult:
    _seed()
    if project_id not in _projects:
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

        item = BOMItem(
            bom_item_id=opt("bom_item_id") or f"{project_id}-U{idx:04d}",
            project_id=project_id,
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
            status="spec_missing" if not opt("spec_doc_id") else "planned",
        )
        accepted.append(item)

    for item in accepted:
        _bom_items[project_id][item.bom_item_id] = item

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


def build_procurement_plan(project_id: str) -> Optional[ProcurementPlan]:
    _seed()
    project = _projects.get(project_id)
    if not project:
        return None

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
