"""Per-tenant demo scenarios.

`build_demo_request(tenant_id)` returns the AgentRequest slice for that tenant
(or arcforge if tenant_id is unknown — keeps unauthenticated `/api/analyze`
calls working with the original demo).

Each slice is tuned to that tenant's sector:
- **arcforge** — Power Systems EPC: forged valves, PLC controls, copper busbars
- **helios** — Offshore Engineering: subsea cables, ROV connectors, marine paints
- **northwind** — Heavy Engineering (hydro + steel): hydro turbines, alloy plates
"""

from __future__ import annotations

from typing import Callable, Dict

from .schemas import (
    AgentRequest,
    CompanyProfile,
    DemandSignal,
    Incident,
    InventoryItem,
    PurchaseOrder,
    SupplierRecord,
)


# ---------------------------------------------------------------------------
# arcforge — Power Systems EPC
# ---------------------------------------------------------------------------


def _arcforge() -> AgentRequest:
    return AgentRequest(
        company=CompanyProfile(
            company_name="Arcforge Engineering",
            sector="Power Systems EPC",
            active_projects=2,
            planner_horizon_days=90,
            target_service_level_pct=98.0,
        ),
        suppliers=[
            SupplierRecord(
                name="Helios Cast & Forge",
                category="Forged valves",
                country="India",
                lead_time_days=42,
                on_time_delivery_pct=88.0,
                quality_ppm=1800,
                annual_spend_usd=740000.0,
                approved_alternatives=0,
                risk_flags=["single source", "late NCR closure"],
            ),
            SupplierRecord(
                name="BluePeak Controls",
                category="PLC and control panels",
                country="Germany",
                lead_time_days=55,
                on_time_delivery_pct=93.0,
                quality_ppm=650,
                annual_spend_usd=1280000.0,
                approved_alternatives=1,
                risk_flags=["port congestion"],
            ),
            SupplierRecord(
                name="Copperline Metals",
                category="Copper busbars",
                country="Malaysia",
                lead_time_days=28,
                on_time_delivery_pct=97.0,
                quality_ppm=300,
                annual_spend_usd=510000.0,
                approved_alternatives=2,
                risk_flags=[],
            ),
            SupplierRecord(
                name="Kerala Forge Works",
                category="Forged valves",
                country="India",
                lead_time_days=56,
                on_time_delivery_pct=91.0,
                quality_ppm=1400,
                annual_spend_usd=180000.0,
                approved_alternatives=1,
                risk_flags=["capacity constrained"],
            ),
            SupplierRecord(
                name="Mitsuba Automation",
                category="PLC and control panels",
                country="Japan",
                lead_time_days=62,
                on_time_delivery_pct=96.0,
                quality_ppm=420,
                annual_spend_usd=320000.0,
                approved_alternatives=2,
                risk_flags=[],
            ),
            SupplierRecord(
                name="Delhi Metals Co",
                category="Copper busbars",
                country="India",
                lead_time_days=24,
                on_time_delivery_pct=94.0,
                quality_ppm=520,
                annual_spend_usd=210000.0,
                approved_alternatives=1,
                risk_flags=["new supplier"],
            ),
        ],
        inventory=[
            InventoryItem(
                sku="VALVE-16-A105",
                description="16 inch forged gate valve",
                category="Forged valves",
                supplier_name="Helios Cast & Forge",
                on_hand_qty=18,
                reorder_point_qty=24,
                safety_stock_qty=14,
                daily_demand_qty=0.9,
                lead_time_days=42,
                unit_cost_usd=3850.0,
                criticality="mission-critical",
            ),
            InventoryItem(
                sku="PLC-S7-IO48",
                description="PLC I/O module 48 point",
                category="Automation",
                supplier_name="BluePeak Controls",
                on_hand_qty=21,
                reorder_point_qty=18,
                safety_stock_qty=12,
                daily_demand_qty=0.7,
                lead_time_days=55,
                unit_cost_usd=2250.0,
                criticality="high",
            ),
            InventoryItem(
                sku="BUSBAR-CU-40",
                description="Copper busbar 40 mm",
                category="Electrical",
                supplier_name="Copperline Metals",
                on_hand_qty=220,
                reorder_point_qty=160,
                safety_stock_qty=90,
                daily_demand_qty=4.0,
                lead_time_days=28,
                unit_cost_usd=92.0,
                criticality="high",
            ),
        ],
        purchase_orders=[
            PurchaseOrder(
                po_number="PO-AF-24017",
                supplier_name="Helios Cast & Forge",
                sku="VALVE-16-A105",
                quantity=30,
                due_in_days=19,
                value_usd=115500.0,
                status="delayed",
                expedite_possible=True,
            ),
            PurchaseOrder(
                po_number="PO-AF-24028",
                supplier_name="BluePeak Controls",
                sku="PLC-S7-IO48",
                quantity=16,
                due_in_days=34,
                value_usd=36000.0,
                status="in_transit",
                expedite_possible=False,
            ),
            PurchaseOrder(
                po_number="PO-AF-24044",
                supplier_name="Copperline Metals",
                sku="BUSBAR-CU-40",
                quantity=140,
                due_in_days=12,
                value_usd=12880.0,
                status="released",
                expedite_possible=True,
            ),
        ],
        demand_signals=[
            DemandSignal(sku="VALVE-16-A105", next_30_day_demand_qty=35, next_90_day_demand_qty=82, confidence_pct=81.0),
            DemandSignal(sku="PLC-S7-IO48", next_30_day_demand_qty=14, next_90_day_demand_qty=38, confidence_pct=74.0),
            DemandSignal(sku="BUSBAR-CU-40", next_30_day_demand_qty=110, next_90_day_demand_qty=290, confidence_pct=79.0),
        ],
        incidents=[
            Incident(
                title="Valve body machining NCR still open",
                severity="high",
                supplier_name="Helios Cast & Forge",
                sku="VALVE-16-A105",
                description="Dimensional deviation on the last incoming batch is still under supplier review.",
                days_open=8,
            ),
            Incident(
                title="Hamburg port congestion affecting controls shipment",
                severity="medium",
                supplier_name="BluePeak Controls",
                sku="PLC-S7-IO48",
                description="Forwarder expects a 5 to 7 day delay on vessel unloading and customs clearance.",
                days_open=3,
            ),
        ],
        ask="Which materials threaten project delivery, and what actions should procurement and planning take this week?",
    )


# ---------------------------------------------------------------------------
# helios — Offshore Engineering
# ---------------------------------------------------------------------------


def _helios() -> AgentRequest:
    return AgentRequest(
        company=CompanyProfile(
            company_name="Helios Offshore",
            sector="Offshore Engineering",
            active_projects=2,
            planner_horizon_days=120,
            target_service_level_pct=97.0,
        ),
        suppliers=[
            SupplierRecord(
                name="NorthCable Subsea",
                category="Subsea cables",
                country="Norway",
                lead_time_days=180,
                on_time_delivery_pct=92.0,
                quality_ppm=410,
                annual_spend_usd=4200000.0,
                approved_alternatives=1,
                risk_flags=["weather window critical"],
            ),
            SupplierRecord(
                name="DeepDive ROV Systems",
                category="ROV connectors",
                country="UK",
                lead_time_days=84,
                on_time_delivery_pct=89.0,
                quality_ppm=820,
                annual_spend_usd=860000.0,
                approved_alternatives=0,
                risk_flags=["single source", "small batch"],
            ),
            SupplierRecord(
                name="Coastline Marine Coatings",
                category="Marine epoxy",
                country="Netherlands",
                lead_time_days=35,
                on_time_delivery_pct=95.0,
                quality_ppm=280,
                annual_spend_usd=240000.0,
                approved_alternatives=2,
                risk_flags=[],
            ),
            SupplierRecord(
                name="Aberdeen Steel Fab",
                category="Offshore structural",
                country="UK",
                lead_time_days=140,
                on_time_delivery_pct=86.0,
                quality_ppm=1100,
                annual_spend_usd=2900000.0,
                approved_alternatives=1,
                risk_flags=["welder shortage"],
            ),
        ],
        inventory=[
            InventoryItem(
                sku="CABLE-66KV-SUB",
                description="66kV subsea export cable per metre",
                category="Subsea cables",
                supplier_name="NorthCable Subsea",
                on_hand_qty=4800,
                reorder_point_qty=5000,
                safety_stock_qty=2400,
                daily_demand_qty=42.0,
                lead_time_days=180,
                unit_cost_usd=180.0,
                criticality="mission-critical",
            ),
            InventoryItem(
                sku="CONN-ROV-12P",
                description="ROV 12-pin wet-mate connector",
                category="ROV connectors",
                supplier_name="DeepDive ROV Systems",
                on_hand_qty=22,
                reorder_point_qty=28,
                safety_stock_qty=12,
                daily_demand_qty=0.4,
                lead_time_days=84,
                unit_cost_usd=4800.0,
                criticality="high",
            ),
        ],
        purchase_orders=[
            PurchaseOrder(
                po_number="PO-HE-31022",
                supplier_name="NorthCable Subsea",
                sku="CABLE-66KV-SUB",
                quantity=3500,
                due_in_days=45,
                value_usd=630000.0,
                status="in_transit",
                expedite_possible=False,
            ),
            PurchaseOrder(
                po_number="PO-HE-31108",
                supplier_name="DeepDive ROV Systems",
                sku="CONN-ROV-12P",
                quantity=18,
                due_in_days=22,
                value_usd=86400.0,
                status="delayed",
                expedite_possible=True,
            ),
        ],
        demand_signals=[
            DemandSignal(sku="CABLE-66KV-SUB", next_30_day_demand_qty=1500, next_90_day_demand_qty=4200, confidence_pct=72.0),
            DemandSignal(sku="CONN-ROV-12P", next_30_day_demand_qty=8, next_90_day_demand_qty=24, confidence_pct=68.0),
        ],
        incidents=[
            Incident(
                title="Cable lay vessel weather window slipping",
                severity="critical",
                supplier_name="NorthCable Subsea",
                sku="CABLE-66KV-SUB",
                description="North Sea forecast pushing the cable-lay window from week 18 to week 21.",
                days_open=4,
            ),
        ],
        ask="Where is the offshore campaign most exposed in the next 60 days?",
    )


# ---------------------------------------------------------------------------
# northwind — Heavy Engineering (hydro + steel)
# ---------------------------------------------------------------------------


def _northwind() -> AgentRequest:
    return AgentRequest(
        company=CompanyProfile(
            company_name="Northwind Heavy Engineering",
            sector="Heavy Engineering",
            active_projects=2,
            planner_horizon_days=180,
            target_service_level_pct=96.5,
        ),
        suppliers=[
            SupplierRecord(
                name="Andritz Hydro",
                category="Hydro turbines",
                country="Austria",
                lead_time_days=420,
                on_time_delivery_pct=94.0,
                quality_ppm=180,
                annual_spend_usd=6800000.0,
                approved_alternatives=0,
                risk_flags=["single source", "long lead"],
            ),
            SupplierRecord(
                name="ThyssenKrupp Specialty Plate",
                category="Alloy plate",
                country="Germany",
                lead_time_days=110,
                on_time_delivery_pct=92.0,
                quality_ppm=320,
                annual_spend_usd=1500000.0,
                approved_alternatives=2,
                risk_flags=[],
            ),
            SupplierRecord(
                name="Bharat Heavy Electricals",
                category="Generators",
                country="India",
                lead_time_days=300,
                on_time_delivery_pct=88.0,
                quality_ppm=520,
                annual_spend_usd=4100000.0,
                approved_alternatives=1,
                risk_flags=["capacity constrained"],
            ),
            SupplierRecord(
                name="Voith Industrial Services",
                category="Penstock fabrication",
                country="Germany",
                lead_time_days=240,
                on_time_delivery_pct=91.0,
                quality_ppm=410,
                annual_spend_usd=2200000.0,
                approved_alternatives=1,
                risk_flags=["transport over-dimensional"],
            ),
        ],
        inventory=[
            InventoryItem(
                sku="RUNNER-FRANCIS-110",
                description="Francis turbine runner 110 MW",
                category="Hydro turbines",
                supplier_name="Andritz Hydro",
                on_hand_qty=0,
                reorder_point_qty=1,
                safety_stock_qty=0,
                daily_demand_qty=0.005,
                lead_time_days=420,
                unit_cost_usd=2200000.0,
                criticality="mission-critical",
            ),
            InventoryItem(
                sku="PLATE-SA516-65",
                description="SA-516 Gr 65 alloy plate / tonne",
                category="Alloy plate",
                supplier_name="ThyssenKrupp Specialty Plate",
                on_hand_qty=120,
                reorder_point_qty=80,
                safety_stock_qty=40,
                daily_demand_qty=1.6,
                lead_time_days=110,
                unit_cost_usd=2400.0,
                criticality="high",
            ),
        ],
        purchase_orders=[
            PurchaseOrder(
                po_number="PO-NW-50011",
                supplier_name="Andritz Hydro",
                sku="RUNNER-FRANCIS-110",
                quantity=2,
                due_in_days=210,
                value_usd=4400000.0,
                status="released",
                expedite_possible=False,
            ),
            PurchaseOrder(
                po_number="PO-NW-50034",
                supplier_name="ThyssenKrupp Specialty Plate",
                sku="PLATE-SA516-65",
                quantity=80,
                due_in_days=65,
                value_usd=192000.0,
                status="in_transit",
                expedite_possible=True,
            ),
        ],
        demand_signals=[
            DemandSignal(sku="RUNNER-FRANCIS-110", next_30_day_demand_qty=0, next_90_day_demand_qty=2, confidence_pct=88.0),
            DemandSignal(sku="PLATE-SA516-65", next_30_day_demand_qty=46, next_90_day_demand_qty=140, confidence_pct=83.0),
        ],
        incidents=[
            Incident(
                title="Andritz runner blade lead time slipped 4 weeks",
                severity="high",
                supplier_name="Andritz Hydro",
                sku="RUNNER-FRANCIS-110",
                description="Foundry capacity constrained; OEM has revised RFE date by 28 days.",
                days_open=11,
            ),
        ],
        ask="What's protecting the hydro commissioning window, and where is the next slip likely to come from?",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


_TENANT_SLICES: Dict[str, Callable[[], AgentRequest]] = {
    "arcforge": _arcforge,
    "helios": _helios,
    "northwind": _northwind,
}

# Memoised per tenant — this function sits on nearly every hot path
# (vendor intel, expediting, logistics, sourcing suggestions, simulations),
# and rebuilding the full Pydantic tree per call is pure waste: the slices
# are static. Treat the returned object as IMMUTABLE — use model_copy()
# if you need to modify it (see api_demo in main.py).
_MEMO: Dict[str, AgentRequest] = {}


def build_demo_request(tenant_id: str = "arcforge") -> AgentRequest:
    """Return the (cached, shared) demo scenario for the given tenant.

    Falls back to arcforge for unknown tenant_ids so legacy (pre-auth)
    callers keep working. Do not mutate the result.
    """
    key = tenant_id if tenant_id in _TENANT_SLICES else "arcforge"
    cached = _MEMO.get(key)
    if cached is None:
        cached = _TENANT_SLICES[key]()
        _MEMO[key] = cached
    return cached
