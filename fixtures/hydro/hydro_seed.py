"""Synthetic data set for an EPC hydroelectric project — Mahadev Hydro 220 MW.

A 2 × 110 MW run-of-river / pondage plant in the Sutlej basin, Himachal Pradesh,
under a 32-month construction window. The data set is sized to exercise every
module of the Control Tower:

- Long-lead detection (turbine runner, generator stator, GIS, transformer)
- Missing-spec flags (a few BOM items deliberately have no spec_doc_id)
- Multi-vendor sourcing (multiple suppliers per category)
- Single-source exposure (Andritz Hydro = sole turbine supplier)
- Expediting queue (POs with predicted slippage)
- Logistics tracker (mix of in-transit / customs / delivered shipments)
- Commercial summary (budget vs quoted vs PO with savings + overruns)
- Risk simulations (vendor slip, customs hold, alternate vendor)

Usage
-----

    from fixtures.hydro.hydro_seed import build_hydro_demo

    demo = build_hydro_demo()
    # demo.project, demo.milestones, demo.bom_items, demo.suppliers,
    # demo.inventory, demo.purchase_orders, demo.demand_signals, demo.incidents

Or load it into the running backend (see load_hydro.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import List

from app.schemas import (
    BOMItem,
    DemandSignal,
    Incident,
    InventoryItem,
    Milestone,
    Project,
    PurchaseOrder,
    SupplierRecord,
)


PROJECT_ID = "HYD-MAHADEV-220"
TENANT_ID = "arcforge"  # for M7 multi-tenant; ignore until M7.2 ships


# ---------------------------------------------------------------------------
# Container
# ---------------------------------------------------------------------------


@dataclass
class HydroDemo:
    project: Project
    milestones: List[Milestone]
    bom_items: List[BOMItem]
    suppliers: List[SupplierRecord]
    inventory: List[InventoryItem]
    purchase_orders: List[PurchaseOrder]
    demand_signals: List[DemandSignal]
    incidents: List[Incident]


# ---------------------------------------------------------------------------
# Project + milestones
# ---------------------------------------------------------------------------


def _project() -> Project:
    return Project(
        project_id=PROJECT_ID,
        name="Mahadev Hydro 220 MW (2x110)",
        client="Northern Hills Power Corporation",
        site="Sutlej Basin, Himachal Pradesh, IN",
        sector="Hydropower EPC",
        currency="USD",
        start_date=date(2025, 4, 1),
        milestones=_milestones(),
    )


def _milestones() -> List[Milestone]:
    return [
        Milestone(code="M01", name="Mobilization complete",            phase="engineering",  required_on_site_date=date(2025, 6, 30)),
        Milestone(code="M02", name="Diversion tunnel breakthrough",    phase="fabrication",  required_on_site_date=date(2025, 9, 30)),
        Milestone(code="M03", name="Cofferdam complete",               phase="fabrication",  required_on_site_date=date(2025, 12, 15)),
        Milestone(code="M04", name="First concrete dam",               phase="fabrication",  required_on_site_date=date(2026, 2, 28)),
        Milestone(code="M05", name="Powerhouse foundation complete",   phase="fabrication",  required_on_site_date=date(2026, 4, 30)),
        Milestone(code="M06", name="Penstock RFE",                     phase="delivery",     required_on_site_date=date(2026, 8, 31)),
        Milestone(code="M07", name="Spiral case erection",             phase="installation", required_on_site_date=date(2026, 11, 30)),
        Milestone(code="M08", name="Generator stator stack",           phase="installation", required_on_site_date=date(2027, 1, 31)),
        Milestone(code="M09", name="Transformer charging",             phase="installation", required_on_site_date=date(2027, 5, 15)),
        Milestone(code="M10", name="GIS energization",                 phase="installation", required_on_site_date=date(2027, 6, 30)),
        Milestone(code="M11", name="Wet commissioning Unit-1",         phase="commissioning",required_on_site_date=date(2027, 9, 30)),
        Milestone(code="M12", name="COD (Commercial Operation Date)",  phase="commissioning",required_on_site_date=date(2027, 12, 31)),
    ]


# ---------------------------------------------------------------------------
# Suppliers
# ---------------------------------------------------------------------------


def _suppliers() -> List[SupplierRecord]:
    return [
        # --- Turbine OEMs (single-source exposure for major rotating equipment)
        SupplierRecord(
            name="Andritz Hydro",
            category="Hydro turbine and accessories",
            country="Austria",
            lead_time_days=540,
            on_time_delivery_pct=87.0,
            quality_ppm=420,
            annual_spend_usd=14_200_000,
            approved_alternatives=0,  # sole-source for turbine package
            risk_flags=["sole source", "long lead", "FX exposure EUR"],
        ),
        SupplierRecord(
            name="Voith Hydro Shanghai",
            category="Hydro turbine ancillaries",
            country="China",
            lead_time_days=300,
            on_time_delivery_pct=82.0,
            quality_ppm=920,
            annual_spend_usd=2_950_000,
            approved_alternatives=1,
            risk_flags=["customs delays observed", "geopolitical risk"],
        ),
        # --- Generator + Transformer OEMs
        SupplierRecord(
            name="BHEL Hyderabad",
            category="Generators",
            country="India",
            lead_time_days=540,
            on_time_delivery_pct=78.0,
            quality_ppm=1450,
            annual_spend_usd=8_900_000,
            approved_alternatives=1,
            risk_flags=["capacity constrained Q3", "labour disputes 2024 history"],
        ),
        SupplierRecord(
            name="BHEL Bhopal",
            category="Power transformers",
            country="India",
            lead_time_days=450,
            on_time_delivery_pct=84.0,
            quality_ppm=1100,
            annual_spend_usd=4_300_000,
            approved_alternatives=2,
            risk_flags=[],
        ),
        SupplierRecord(
            name="Siemens Energy",
            category="Excitation and protection",
            country="Germany",
            lead_time_days=300,
            on_time_delivery_pct=94.0,
            quality_ppm=240,
            annual_spend_usd=790_000,
            approved_alternatives=1,
            risk_flags=[],
        ),
        SupplierRecord(
            name="CG Power",
            category="Distribution transformers and IPB",
            country="India",
            lead_time_days=300,
            on_time_delivery_pct=88.0,
            quality_ppm=620,
            annual_spend_usd=820_000,
            approved_alternatives=2,
            risk_flags=[],
        ),
        SupplierRecord(
            name="Hyundai Electric",
            category="Power transformers",
            country="South Korea",
            lead_time_days=420,
            on_time_delivery_pct=92.0,
            quality_ppm=380,
            annual_spend_usd=0,
            approved_alternatives=2,
            risk_flags=["FX exposure KRW"],
        ),
        # --- GIS Switchgear
        SupplierRecord(
            name="Hitachi Energy",
            category="GIS Switchgear",
            country="Switzerland",
            lead_time_days=360,
            on_time_delivery_pct=91.0,
            quality_ppm=290,
            annual_spend_usd=3_700_000,
            approved_alternatives=2,
            risk_flags=[],
        ),
        SupplierRecord(
            name="ABB India",
            category="MV switchgear and protection",
            country="India",
            lead_time_days=240,
            on_time_delivery_pct=93.0,
            quality_ppm=320,
            annual_spend_usd=1_120_000,
            approved_alternatives=2,
            risk_flags=[],
        ),
        # --- Cables
        SupplierRecord(
            name="Polycab",
            category="Power cables",
            country="India",
            lead_time_days=150,
            on_time_delivery_pct=96.0,
            quality_ppm=180,
            annual_spend_usd=950_000,
            approved_alternatives=3,
            risk_flags=[],
        ),
        SupplierRecord(
            name="KEI Industries",
            category="Control and instrumentation cables",
            country="India",
            lead_time_days=120,
            on_time_delivery_pct=95.0,
            quality_ppm=210,
            annual_spend_usd=240_000,
            approved_alternatives=3,
            risk_flags=[],
        ),
        SupplierRecord(
            name="Havells Cables",
            category="Cable trays and accessories",
            country="India",
            lead_time_days=90,
            on_time_delivery_pct=97.0,
            quality_ppm=140,
            annual_spend_usd=240_000,
            approved_alternatives=3,
            risk_flags=[],
        ),
        SupplierRecord(
            name="Prysmian",
            category="HV cables and terminations",
            country="Italy",
            lead_time_days=300,
            on_time_delivery_pct=89.0,
            quality_ppm=290,
            annual_spend_usd=580_000,
            approved_alternatives=1,
            risk_flags=["FX exposure EUR"],
        ),
        SupplierRecord(
            name="NKT",
            category="HV cables and terminations",
            country="Denmark",
            lead_time_days=330,
            on_time_delivery_pct=92.0,
            quality_ppm=240,
            annual_spend_usd=0,
            approved_alternatives=1,
            risk_flags=[],
        ),
        # --- Penstock and structural steel
        SupplierRecord(
            name="Jindal SAW",
            category="Penstock and large diameter pipe",
            country="India",
            lead_time_days=480,
            on_time_delivery_pct=81.0,
            quality_ppm=1380,
            annual_spend_usd=6_400_000,
            approved_alternatives=1,
            risk_flags=["weld NCR history", "long lead"],
        ),
        SupplierRecord(
            name="SLP Industries",
            category="Hydromechanical equipment",
            country="India",
            lead_time_days=300,
            on_time_delivery_pct=85.0,
            quality_ppm=820,
            annual_spend_usd=1_180_000,
            approved_alternatives=1,
            risk_flags=[],
        ),
        SupplierRecord(
            name="Texmaco Rail",
            category="Hydromechanical equipment",
            country="India",
            lead_time_days=300,
            on_time_delivery_pct=83.0,
            quality_ppm=1050,
            annual_spend_usd=420_000,
            approved_alternatives=1,
            risk_flags=["new vendor"],
        ),
        SupplierRecord(
            name="ISGEC Heavy Engineering",
            category="Hydromechanical and gates",
            country="India",
            lead_time_days=365,
            on_time_delivery_pct=87.0,
            quality_ppm=720,
            annual_spend_usd=2_440_000,
            approved_alternatives=2,
            risk_flags=[],
        ),
        # --- Civil consumables
        SupplierRecord(
            name="UltraTech Cement",
            category="OPC and PPC cement",
            country="India",
            lead_time_days=30,
            on_time_delivery_pct=98.0,
            quality_ppm=80,
            annual_spend_usd=2_750_000,
            approved_alternatives=4,
            risk_flags=[],
        ),
        SupplierRecord(
            name="Ambuja Cements",
            category="OPC and PPC cement",
            country="India",
            lead_time_days=30,
            on_time_delivery_pct=97.0,
            quality_ppm=120,
            annual_spend_usd=1_060_000,
            approved_alternatives=4,
            risk_flags=[],
        ),
        SupplierRecord(
            name="ACC Limited",
            category="Cement and fly ash",
            country="India",
            lead_time_days=30,
            on_time_delivery_pct=96.0,
            quality_ppm=140,
            annual_spend_usd=210_000,
            approved_alternatives=4,
            risk_flags=[],
        ),
        SupplierRecord(
            name="Tata Steel",
            category="TMT rebar and structural",
            country="India",
            lead_time_days=60,
            on_time_delivery_pct=95.0,
            quality_ppm=180,
            annual_spend_usd=4_680_000,
            approved_alternatives=3,
            risk_flags=[],
        ),
        SupplierRecord(
            name="JSW Steel",
            category="Structural steel and plates",
            country="India",
            lead_time_days=90,
            on_time_delivery_pct=93.0,
            quality_ppm=240,
            annual_spend_usd=2_830_000,
            approved_alternatives=3,
            risk_flags=[],
        ),
        SupplierRecord(
            name="Fosroc",
            category="Construction chemicals",
            country="India",
            lead_time_days=60,
            on_time_delivery_pct=94.0,
            quality_ppm=320,
            annual_spend_usd=216_000,
            approved_alternatives=2,
            risk_flags=[],
        ),
        # --- Cranes, HVAC, fire, instruments
        SupplierRecord(
            name="Konecranes",
            category="EOT and bridge cranes",
            country="Finland",
            lead_time_days=300,
            on_time_delivery_pct=92.0,
            quality_ppm=210,
            annual_spend_usd=1_280_000,
            approved_alternatives=1,
            risk_flags=["FX exposure EUR"],
        ),
        SupplierRecord(
            name="Demag Cranes",
            category="EOT and bridge cranes",
            country="Germany",
            lead_time_days=300,
            on_time_delivery_pct=89.0,
            quality_ppm=320,
            annual_spend_usd=485_000,
            approved_alternatives=1,
            risk_flags=[],
        ),
        SupplierRecord(
            name="Voltas",
            category="HVAC plant",
            country="India",
            lead_time_days=180,
            on_time_delivery_pct=90.0,
            quality_ppm=540,
            annual_spend_usd=310_000,
            approved_alternatives=2,
            risk_flags=[],
        ),
        SupplierRecord(
            name="Blue Star",
            category="Precision air conditioning",
            country="India",
            lead_time_days=150,
            on_time_delivery_pct=92.0,
            quality_ppm=410,
            annual_spend_usd=144_000,
            approved_alternatives=2,
            risk_flags=[],
        ),
        SupplierRecord(
            name="HD Fire Protect",
            category="Fire protection",
            country="India",
            lead_time_days=180,
            on_time_delivery_pct=88.0,
            quality_ppm=620,
            annual_spend_usd=292_000,
            approved_alternatives=2,
            risk_flags=[],
        ),
        SupplierRecord(
            name="Tyco Fire Protection",
            category="Fire detection and alarm",
            country="USA",
            lead_time_days=180,
            on_time_delivery_pct=91.0,
            quality_ppm=380,
            annual_spend_usd=128_000,
            approved_alternatives=2,
            risk_flags=[],
        ),
        SupplierRecord(
            name="Emerson Process",
            category="DCS and vibration monitoring",
            country="USA",
            lead_time_days=240,
            on_time_delivery_pct=94.0,
            quality_ppm=210,
            annual_spend_usd=1_248_000,
            approved_alternatives=2,
            risk_flags=[],
        ),
        SupplierRecord(
            name="Schneider Electric",
            category="MCC and metering",
            country="France",
            lead_time_days=180,
            on_time_delivery_pct=92.0,
            quality_ppm=290,
            annual_spend_usd=722_000,
            approved_alternatives=3,
            risk_flags=[],
        ),
        SupplierRecord(
            name="Endress+Hauser",
            category="Field instruments",
            country="Switzerland",
            lead_time_days=150,
            on_time_delivery_pct=95.0,
            quality_ppm=180,
            annual_spend_usd=184_000,
            approved_alternatives=2,
            risk_flags=[],
        ),
        SupplierRecord(
            name="Kirloskar Brothers",
            category="Cooling water pumps",
            country="India",
            lead_time_days=240,
            on_time_delivery_pct=86.0,
            quality_ppm=720,
            annual_spend_usd=890_000,
            approved_alternatives=2,
            risk_flags=[],
        ),
    ]


# ---------------------------------------------------------------------------
# Inventory — operating spares + project-staged consumables
# ---------------------------------------------------------------------------


def _inventory() -> List[InventoryItem]:
    return [
        # Cement (high-volume staging — kept at safe cover to avoid swamping risk register)
        InventoryItem(
            sku="CEM-OPC53-BULK",
            description="OPC 53 grade cement bulk (tonne)",
            category="Civil consumables",
            supplier_name="UltraTech Cement",
            on_hand_qty=3200,
            reorder_point_qty=2200,
            safety_stock_qty=1500,
            daily_demand_qty=85.0,
            lead_time_days=30,
            unit_cost_usd=98,
            criticality="high",
        ),
        InventoryItem(
            sku="CEM-PPC-BULK",
            description="PPC cement bulk (tonne)",
            category="Civil consumables",
            supplier_name="Ambuja Cements",
            on_hand_qty=1480,
            reorder_point_qty=1200,
            safety_stock_qty=600,
            daily_demand_qty=42.0,
            lead_time_days=30,
            unit_cost_usd=88,
            criticality="medium",
        ),
        InventoryItem(
            sku="REBAR-FE550-16",
            description="TMT rebar Fe 550 16 mm",
            category="Civil consumables",
            supplier_name="Tata Steel",
            on_hand_qty=1080,
            reorder_point_qty=900,
            safety_stock_qty=400,
            daily_demand_qty=18.0,
            lead_time_days=60,
            unit_cost_usd=720,
            criticality="high",
        ),
        InventoryItem(
            sku="REBAR-FE550-25",
            description="TMT rebar Fe 550 25 mm",
            category="Civil consumables",
            supplier_name="Tata Steel",
            on_hand_qty=720,
            reorder_point_qty=600,
            safety_stock_qty=280,
            daily_demand_qty=12.0,
            lead_time_days=60,
            unit_cost_usd=720,
            criticality="high",
        ),
        InventoryItem(
            sku="STRUCT-PLATE-12",
            description="Structural steel plate 12 mm IS 2062",
            category="Civil consumables",
            supplier_name="JSW Steel",
            on_hand_qty=265,
            reorder_point_qty=220,
            safety_stock_qty=100,
            daily_demand_qty=4.5,
            lead_time_days=90,
            unit_cost_usd=1180,
            criticality="medium",
        ),
        # Welding consumables for penstock erection
        InventoryItem(
            sku="WELD-E7018",
            description="Welding electrode E7018 4 mm (kg)",
            category="Welding consumables",
            supplier_name="Polycab",
            on_hand_qty=1900,
            reorder_point_qty=1500,
            safety_stock_qty=700,
            daily_demand_qty=42.0,
            lead_time_days=30,
            unit_cost_usd=4.2,
            criticality="high",
        ),
        InventoryItem(
            sku="WELD-WIRE-ER70S6",
            description="MIG welding wire ER70S-6 1.2 mm (kg)",
            category="Welding consumables",
            supplier_name="Polycab",
            on_hand_qty=1380,
            reorder_point_qty=1100,
            safety_stock_qty=450,
            daily_demand_qty=28.0,
            lead_time_days=45,
            unit_cost_usd=3.8,
            criticality="high",
        ),
        # Mechanical spares (operating)
        InventoryItem(
            sku="LUB-TURB-OIL-46",
            description="Turbine lube oil ISO VG 46 (litre)",
            category="Lubricants and chemicals",
            supplier_name="Voith Hydro Shanghai",
            on_hand_qty=2400,
            reorder_point_qty=1800,
            safety_stock_qty=900,
            daily_demand_qty=12.0,
            lead_time_days=90,
            unit_cost_usd=6.4,
            criticality="mission-critical",
        ),
        InventoryItem(
            sku="GASKET-MIV-SET",
            description="Inlet butterfly valve gasket set",
            category="Spares - turbine",
            supplier_name="Voith Hydro Shanghai",
            on_hand_qty=1,
            reorder_point_qty=2,
            safety_stock_qty=1,
            daily_demand_qty=0.05,
            lead_time_days=180,
            unit_cost_usd=8200,
            criticality="mission-critical",
        ),
        InventoryItem(
            sku="BRG-GUIDE-SET",
            description="Generator guide bearing pad set",
            category="Spares - generator",
            supplier_name="BHEL Hyderabad",
            on_hand_qty=1,
            reorder_point_qty=2,
            safety_stock_qty=1,
            daily_demand_qty=0.02,
            lead_time_days=210,
            unit_cost_usd=42000,
            criticality="mission-critical",
        ),
        InventoryItem(
            sku="BRG-THRUST-PAD",
            description="Generator thrust bearing pad",
            category="Spares - generator",
            supplier_name="BHEL Hyderabad",
            on_hand_qty=2,
            reorder_point_qty=3,
            safety_stock_qty=2,
            daily_demand_qty=0.03,
            lead_time_days=210,
            unit_cost_usd=18500,
            criticality="mission-critical",
        ),
        InventoryItem(
            sku="SEAL-SHAFT-LAB",
            description="Main shaft labyrinth seal",
            category="Spares - turbine",
            supplier_name="Andritz Hydro",
            on_hand_qty=1,
            reorder_point_qty=2,
            safety_stock_qty=1,
            daily_demand_qty=0.02,
            lead_time_days=300,
            unit_cost_usd=34000,
            criticality="mission-critical",
        ),
        InventoryItem(
            sku="SERVO-ACT-SPARE",
            description="Wicket gate servo actuator spare",
            category="Spares - turbine",
            supplier_name="Voith Hydro Shanghai",
            on_hand_qty=0,
            reorder_point_qty=1,
            safety_stock_qty=1,
            daily_demand_qty=0.01,
            lead_time_days=240,
            unit_cost_usd=128000,
            criticality="mission-critical",
        ),
        InventoryItem(
            sku="EXC-CARDS-SET",
            description="Excitation system controller card set",
            category="Spares - electrical",
            supplier_name="Siemens Energy",
            on_hand_qty=2,
            reorder_point_qty=2,
            safety_stock_qty=1,
            daily_demand_qty=0.02,
            lead_time_days=180,
            unit_cost_usd=18500,
            criticality="high",
        ),
        InventoryItem(
            sku="PROT-RELAY-7UM",
            description="Generator protection numerical relay",
            category="Spares - protection",
            supplier_name="ABB India",
            on_hand_qty=1,
            reorder_point_qty=2,
            safety_stock_qty=1,
            daily_demand_qty=0.01,
            lead_time_days=180,
            unit_cost_usd=14200,
            criticality="high",
        ),
        InventoryItem(
            sku="SF6-GAS-CYL",
            description="SF6 gas cylinder 50 kg",
            category="Spares - GIS",
            supplier_name="Hitachi Energy",
            on_hand_qty=4,
            reorder_point_qty=6,
            safety_stock_qty=3,
            daily_demand_qty=0.05,
            lead_time_days=120,
            unit_cost_usd=4800,
            criticality="high",
        ),
        InventoryItem(
            sku="HV-CAB-TERM-220",
            description="220 kV cable termination kit spare",
            category="Spares - HV cable",
            supplier_name="Prysmian",
            on_hand_qty=0,
            reorder_point_qty=1,
            safety_stock_qty=1,
            daily_demand_qty=0.01,
            lead_time_days=210,
            unit_cost_usd=82000,
            criticality="high",
        ),
        InventoryItem(
            sku="FLT-OIL-TURB",
            description="Turbine lube oil filter element",
            category="Spares - mechanical",
            supplier_name="Voith Hydro Shanghai",
            on_hand_qty=8,
            reorder_point_qty=10,
            safety_stock_qty=4,
            daily_demand_qty=0.18,
            lead_time_days=60,
            unit_cost_usd=380,
            criticality="medium",
        ),
        InventoryItem(
            sku="INST-PT-HART",
            description="Pressure transmitter HART 4-20 mA",
            category="Field instruments",
            supplier_name="Endress+Hauser",
            on_hand_qty=12,
            reorder_point_qty=10,
            safety_stock_qty=5,
            daily_demand_qty=0.18,
            lead_time_days=120,
            unit_cost_usd=1480,
            criticality="medium",
        ),
        InventoryItem(
            sku="INST-RTD-PT100",
            description="RTD PT100 4-wire mineral insulated",
            category="Field instruments",
            supplier_name="Endress+Hauser",
            on_hand_qty=22,
            reorder_point_qty=15,
            safety_stock_qty=8,
            daily_demand_qty=0.32,
            lead_time_days=90,
            unit_cost_usd=180,
            criticality="medium",
        ),
        InventoryItem(
            sku="HV-CB-SF6",
            description="SF6 circuit breaker spare pole",
            category="Spares - GIS",
            supplier_name="Hitachi Energy",
            on_hand_qty=0,
            reorder_point_qty=1,
            safety_stock_qty=1,
            daily_demand_qty=0.005,
            lead_time_days=300,
            unit_cost_usd=145000,
            criticality="mission-critical",
        ),
        InventoryItem(
            sku="CW-PUMP-IMPEL",
            description="CW pump impeller spare",
            category="Spares - mechanical",
            supplier_name="Kirloskar Brothers",
            on_hand_qty=1,
            reorder_point_qty=2,
            safety_stock_qty=1,
            daily_demand_qty=0.02,
            lead_time_days=180,
            unit_cost_usd=24000,
            criticality="high",
        ),
        InventoryItem(
            sku="HVAC-COMP-SPARE",
            description="Precision AC compressor spare",
            category="HVAC spares",
            supplier_name="Blue Star",
            on_hand_qty=1,
            reorder_point_qty=1,
            safety_stock_qty=1,
            daily_demand_qty=0.02,
            lead_time_days=120,
            unit_cost_usd=8400,
            criticality="medium",
        ),
        InventoryItem(
            sku="FIRE-CO2-CYL-45",
            description="CO2 fire cylinder 45 kg recharge",
            category="Fire protection",
            supplier_name="HD Fire Protect",
            on_hand_qty=12,
            reorder_point_qty=8,
            safety_stock_qty=4,
            daily_demand_qty=0.04,
            lead_time_days=90,
            unit_cost_usd=820,
            criticality="medium",
        ),
        InventoryItem(
            sku="CABLE-CTRL-SPARE",
            description="Control cable 16C 1.5 sq.mm spare drum",
            category="Cables",
            supplier_name="KEI Industries",
            on_hand_qty=2400,
            reorder_point_qty=2000,
            safety_stock_qty=800,
            daily_demand_qty=42.0,
            lead_time_days=90,
            unit_cost_usd=8.5,
            criticality="medium",
        ),
    ]


# ---------------------------------------------------------------------------
# Demand signals — driven by upcoming construction milestones
# ---------------------------------------------------------------------------


def _demand_signals() -> List[DemandSignal]:
    return [
        DemandSignal(sku="CEM-OPC53-BULK",  next_30_day_demand_qty=2550,  next_90_day_demand_qty=8400,  confidence_pct=88.0),
        DemandSignal(sku="CEM-PPC-BULK",    next_30_day_demand_qty=1260,  next_90_day_demand_qty=4200,  confidence_pct=82.0),
        DemandSignal(sku="REBAR-FE550-16",  next_30_day_demand_qty=540,   next_90_day_demand_qty=1820,  confidence_pct=80.0),
        DemandSignal(sku="REBAR-FE550-25",  next_30_day_demand_qty=360,   next_90_day_demand_qty=1240,  confidence_pct=78.0),
        DemandSignal(sku="STRUCT-PLATE-12", next_30_day_demand_qty=135,   next_90_day_demand_qty=480,   confidence_pct=72.0),
        DemandSignal(sku="WELD-E7018",      next_30_day_demand_qty=1260,  next_90_day_demand_qty=4400,  confidence_pct=85.0),
        DemandSignal(sku="WELD-WIRE-ER70S6",next_30_day_demand_qty=840,   next_90_day_demand_qty=2920,  confidence_pct=82.0),
        DemandSignal(sku="LUB-TURB-OIL-46", next_30_day_demand_qty=360,   next_90_day_demand_qty=1100,  confidence_pct=70.0),
        DemandSignal(sku="INST-PT-HART",    next_30_day_demand_qty=6,     next_90_day_demand_qty=18,    confidence_pct=68.0),
        DemandSignal(sku="INST-RTD-PT100",  next_30_day_demand_qty=10,    next_90_day_demand_qty=32,    confidence_pct=72.0),
        DemandSignal(sku="CABLE-CTRL-SPARE",next_30_day_demand_qty=1260,  next_90_day_demand_qty=4400,  confidence_pct=80.0),
    ]


# ---------------------------------------------------------------------------
# Purchase orders — currently in flight, mixed statuses
# ---------------------------------------------------------------------------


def _purchase_orders() -> List[PurchaseOrder]:
    return [
        # Critical long-lead, in-transit, expedite-able
        PurchaseOrder(
            po_number="PO-25-0118",
            supplier_name="Andritz Hydro",
            sku="TG-RUNNER-01",
            quantity=2,
            due_in_days=84,
            value_usd=5_700_000,
            status="in_transit",
            expedite_possible=False,
        ),
        PurchaseOrder(
            po_number="PO-25-0119",
            supplier_name="Andritz Hydro",
            sku="TG-WICKET-01",
            quantity=2,
            due_in_days=72,
            value_usd=2_360_000,
            status="in_transit",
            expedite_possible=False,
        ),
        PurchaseOrder(
            po_number="PO-25-0124",
            supplier_name="Andritz Hydro",
            sku="TG-SPIRAL-01",
            quantity=2,
            due_in_days=58,
            value_usd=3_240_000,
            status="delayed",
            expedite_possible=True,
        ),
        PurchaseOrder(
            po_number="PO-25-0131",
            supplier_name="BHEL Hyderabad",
            sku="GE-STATOR-01",
            quantity=2,
            due_in_days=132,
            value_usd=7_900_000,
            status="released",
            expedite_possible=False,
        ),
        PurchaseOrder(
            po_number="PO-25-0132",
            supplier_name="BHEL Hyderabad",
            sku="GE-ROTOR-01",
            quantity=2,
            due_in_days=144,
            value_usd=6_240_000,
            status="released",
            expedite_possible=False,
        ),
        PurchaseOrder(
            po_number="PO-25-0140",
            supplier_name="BHEL Bhopal",
            sku="TR-GT-130MVA",
            quantity=2,
            due_in_days=210,
            value_usd=4_300_000,
            status="released",
            expedite_possible=False,
        ),
        PurchaseOrder(
            po_number="PO-25-0151",
            supplier_name="Hitachi Energy",
            sku="GIS-220-BAY",
            quantity=4,
            due_in_days=192,
            value_usd=3_580_000,
            status="released",
            expedite_possible=True,
        ),
        # Penstock — very high risk; weld NCR history
        PurchaseOrder(
            po_number="PO-25-0162",
            supplier_name="Jindal SAW",
            sku="HM-PEN-PIPE",
            quantity=1500,
            due_in_days=42,
            value_usd=6_300_000,
            status="delayed",
            expedite_possible=True,
        ),
        PurchaseOrder(
            po_number="PO-25-0167",
            supplier_name="ISGEC Heavy Engineering",
            sku="HM-INTGT-01",
            quantity=2,
            due_in_days=12,
            value_usd=840_000,
            status="in_transit",
            expedite_possible=True,
        ),
        PurchaseOrder(
            po_number="PO-25-0172",
            supplier_name="ISGEC Heavy Engineering",
            sku="HM-SPLGT-01",
            quantity=3,
            due_in_days=88,
            value_usd=1_530_000,
            status="released",
            expedite_possible=True,
        ),
        # On track / received civil
        PurchaseOrder(
            po_number="PO-25-0188",
            supplier_name="UltraTech Cement",
            sku="CEM-OPC53-BULK",
            quantity=8400,
            due_in_days=21,
            value_usd=823_200,
            status="in_transit",
            expedite_possible=False,
        ),
        PurchaseOrder(
            po_number="PO-25-0189",
            supplier_name="Tata Steel",
            sku="REBAR-FE550-16",
            quantity=1800,
            due_in_days=18,
            value_usd=1_296_000,
            status="released",
            expedite_possible=True,
        ),
        PurchaseOrder(
            po_number="PO-25-0192",
            supplier_name="JSW Steel",
            sku="CV-STRUCT-ST",
            quantity=600,
            due_in_days=72,
            value_usd=708_000,
            status="planned",
            expedite_possible=False,
        ),
        PurchaseOrder(
            po_number="PO-25-0201",
            supplier_name="Polycab",
            sku="CB-13-MV",
            quantity=4500,
            due_in_days=110,
            value_usd=324_000,
            status="planned",
            expedite_possible=False,
        ),
        PurchaseOrder(
            po_number="PO-25-0205",
            supplier_name="Konecranes",
            sku="CR-EOT-PWR",
            quantity=1,
            due_in_days=68,
            value_usd=1_280_000,
            status="released",
            expedite_possible=True,
        ),
        # Already received
        PurchaseOrder(
            po_number="PO-24-0992",
            supplier_name="Demag Cranes",
            sku="CR-INT-BRG",
            quantity=1,
            due_in_days=-14,
            value_usd=485_000,
            status="received",
            expedite_possible=False,
        ),
        PurchaseOrder(
            po_number="PO-24-0998",
            supplier_name="Texmaco Rail",
            sku="HM-DIVGT-01",
            quantity=1,
            due_in_days=-32,
            value_usd=165_000,
            status="received",
            expedite_possible=False,
        ),
    ]


# ---------------------------------------------------------------------------
# Incidents — open issues affecting the project
# ---------------------------------------------------------------------------


def _incidents() -> List[Incident]:
    return [
        # --- Lower-severity, varied open-day count for risk diversity
        Incident(
            title="Customs paperwork follow-up on Konecranes shipment",
            severity="low",
            description=(
                "Routine BIS form re-submission needed for Konecranes hoist shipment. "
                "Clearing agent has copies; expected resolution within 5 working days."
            ),
            supplier_name="Konecranes",
            sku="CR-EOT-PWR",
            days_open=2,
        ),
        Incident(
            title="Kirloskar shop visit pending — CW pump witness test",
            severity="medium",
            description=(
                "Witness test at Kirloskar Pune was rescheduled twice; client QA team "
                "to visit week of June 2. No schedule impact yet but slipping into the "
                "transformer charging milestone window if delayed further."
            ),
            supplier_name="Kirloskar Brothers",
            sku="CW-PUMP-VT",
            days_open=15,
        ),
        Incident(
            title="Polycab packaging discrepancy — drum count short",
            severity="low",
            description=(
                "Polycab shipment of 13.8 kV cable arrived with 38 drums vs 40 on "
                "packing list. Photographic evidence captured at gate; 2 missing "
                "drums being traced through Polycab dispatch records."
            ),
            supplier_name="Polycab",
            sku="CB-13-MV",
            days_open=4,
        ),
        Incident(
            title="UltraTech cement bag moisture — minor batch",
            severity="medium",
            description=(
                "Moisture content above spec in 220 bags from latest UltraTech "
                "delivery. Bags isolated and returned; no impact on pour schedule. "
                "Replacement dispatched."
            ),
            supplier_name="UltraTech Cement",
            sku="CEM-OPC53-BULK",
            days_open=1,
        ),
        # --- Original high/critical incidents
        Incident(
            title="Penstock weld NCR — segment 4 longitudinal seam",
            severity="high",
            description=(
                "QAP-mandated UT on segment 4 longitudinal seam returned class-D indications "
                "across 18% of the weld length. Jindal SAW requested 21-day extension for rework "
                "and re-inspection. Net 2-week slip threatens M06 RFE milestone."
            ),
            supplier_name="Jindal SAW",
            sku="HM-PEN-PIPE",
            days_open=12,
        ),
        Incident(
            title="Spiral case shipment held at JNPT customs",
            severity="critical",
            description=(
                "Spiral case shipment ex-Linz (Andritz Hydro) held at JNPT awaiting BIS "
                "compliance certification clarification. Container demurrage accruing at "
                "USD 240/day per box (3 boxes). Escalated to clearing agent + Andritz."
            ),
            supplier_name="Andritz Hydro",
            sku="TG-SPIRAL-01",
            days_open=8,
        ),
        Incident(
            title="BHEL Hyderabad capacity advisory — Q3 stator slot",
            severity="high",
            description=(
                "BHEL Hyderabad notified that two slots in their Q3 production schedule were "
                "reassigned to a higher-priority NTPC order. Our generator stator FAT date may "
                "slip 4-6 weeks. Need formal reschedule confirmation by month-end."
            ),
            supplier_name="BHEL Hyderabad",
            sku="GE-STATOR-01",
            days_open=4,
        ),
        Incident(
            title="GIS Bay-3 voltage transformer off-spec (Routine test)",
            severity="medium",
            description=(
                "Hitachi Energy reported voltage transformer in Bay-3 lineup failed routine "
                "test for ratio error (0.32% vs 0.20% IS limit). Replacement VT being "
                "manufactured; expected 6-week impact at the bay-level only."
            ),
            supplier_name="Hitachi Energy",
            sku="GIS-220-BAY",
            days_open=18,
        ),
        Incident(
            title="Cement supply disrupted — UltraTech Daund kiln shutdown",
            severity="medium",
            description=(
                "Unscheduled kiln shutdown at UltraTech Daund affecting OPC supply for 10 days. "
                "Switching 30% volume to Ambuja Cements as approved alternate. No site impact "
                "expected given current on-hand of 620 t."
            ),
            supplier_name="UltraTech Cement",
            sku="CEM-OPC53-BULK",
            days_open=3,
        ),
        Incident(
            title="EOT crane main hoist gearbox vibration in FAT",
            severity="high",
            description=(
                "Konecranes FAT (factory acceptance test) flagged main hoist gearbox "
                "vibration above ISO 10816 zone B limits at 75% load. Bearing replacement "
                "underway; FAT re-attempt scheduled. M07 milestone at risk by ~3 weeks."
            ),
            supplier_name="Konecranes",
            sku="CR-EOT-PWR",
            days_open=6,
        ),
    ]


# ---------------------------------------------------------------------------
# BOM (loaded from the bundled CSV so the same data feeds both
# /bom/upload testing and direct in-memory injection)
# ---------------------------------------------------------------------------


def _bom_items() -> List[BOMItem]:
    import csv
    import io
    import os

    here = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(here, "bom_hydro.csv")
    with open(csv_path, "r", encoding="utf-8-sig") as fh:
        text = fh.read()

    rows = list(csv.DictReader(io.StringIO(text)))
    items: List[BOMItem] = []
    for r in rows:
        def opt(k):
            v = (r.get(k) or "").strip()
            return v or None

        def opt_int(k):
            v = (r.get(k) or "").strip()
            return int(float(v)) if v else None

        def opt_float(k):
            v = (r.get(k) or "").strip()
            return float(v) if v else None

        def opt_date(k):
            v = (r.get(k) or "").strip()
            return date.fromisoformat(v) if v else None

        items.append(
            BOMItem(
                bom_item_id=opt("bom_item_id") or f"{PROJECT_ID}-AUTO",
                project_id=PROJECT_ID,
                code=r["code"].strip(),
                description=r["description"].strip(),
                category=opt("category"),
                quantity=float(r["quantity"]),
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
        )
    return items


# ---------------------------------------------------------------------------
# Public builder
# ---------------------------------------------------------------------------


def build_hydro_demo() -> HydroDemo:
    return HydroDemo(
        project=_project(),
        milestones=_milestones(),
        bom_items=_bom_items(),
        suppliers=_suppliers(),
        inventory=_inventory(),
        purchase_orders=_purchase_orders(),
        demand_signals=_demand_signals(),
        incidents=_incidents(),
    )


if __name__ == "__main__":
    demo = build_hydro_demo()
    print(f"Project        : {demo.project.name}")
    print(f"Milestones     : {len(demo.milestones)}")
    print(f"BOM items      : {len(demo.bom_items)}")
    print(f"Suppliers      : {len(demo.suppliers)}")
    print(f"Inventory      : {len(demo.inventory)}")
    print(f"Purchase orders: {len(demo.purchase_orders)}")
    print(f"Demand signals : {len(demo.demand_signals)}")
    print(f"Incidents      : {len(demo.incidents)}")
    long_lead = [b for b in demo.bom_items if (b.long_lead_days or 0) >= 365]
    print(f"Long-lead items (>= 365 d): {len(long_lead)}")
    missing_spec = [b for b in demo.bom_items if not b.spec_doc_id]
    print(f"Missing-spec items        : {len(missing_spec)}")
