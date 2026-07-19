# Mahadev Hydro — synthetic test fixture

Synthetic data set for testing the Control Tower against a realistic EPC
hydroelectric project: **Mahadev Hydro 220 MW (2 × 110 MW Francis), Sutlej
basin, Himachal Pradesh, IN**.

## What's in the box

| File | Purpose |
|---|---|
| `bom_hydro.csv` | 70-line multi-category BOM, ready for `POST /api/projects/{id}/bom/upload` |
| `hydro_seed.py` | Python module: project + 12 milestones + 70 BOM items + 35 suppliers + 25 inventory items + 17 POs + 11 demand signals + 6 incidents |
| `load_hydro.py` | CLI loader — `inject` into in-memory stores or `upload-bom` to a live backend |

## Coverage matrix

The fixture is sized to exercise every module:

| Module | What it sees |
|---|---|
| Procurement plan / long-lead | 13 items with `long_lead_days ≥ 365` (turbine runner = 540 d, generator stator = 540 d, GT transformer = 450 d, GIS = 360 d, penstock = 480 d) |
| Missing-spec flag | 8 BOM items deliberately have no `spec_doc_id` |
| Vendor scorecards | 35 suppliers across 18 categories with realistic OTD %, quality PPM, spend, alternates, risk flags |
| Single-source detection | Andritz Hydro is sole-source for the entire turbine package — flagged with `risk_flags: ["sole source", "long lead", "FX exposure EUR"]` |
| Expediting queue | 17 POs at mixed stages (planned / released / in_transit / delayed / received), 8 marked `expedite_possible: True` |
| Logistics tracker | POs with `due_in_days` ranging from −32 (received) to +210 (released) |
| Commercial summary | BOM unit costs roll up to a realistic ~USD 70 M project value across 70 line items |
| Risk simulator | At-risk vendors (Jindal SAW penstock, Andritz spiral case, BHEL stator slot reassignment) modelled as incidents |
| AI Command Center | Mix of projects/POs/vendors gives the agent enough surface to demonstrate weekly plan + tool-calls |

## Numbers

```
Project        : Mahadev Hydro 220 MW (2x110)
Milestones     : 12   (M01 mobilization → M12 COD)
BOM items      : 70   (Hydromechanical 10, Turbine 10, Generator 6,
                       Transformer 4, GIS 3, Switchgear 3, Bus duct 1,
                       Cables 7, C&I 8, Cooling water 4, Lubrication 1,
                       Cranes 2, Fire 3, HVAC 2, Civil 6)
Suppliers      : 35
Inventory      : 25   (operating spares + project-staged consumables)
POs in flight  : 17
Demand signals : 11
Incidents      : 6    (1 critical, 4 high, 2 medium)
Long-lead items: 13   (≥ 365 days)
Missing specs  : 8
```

## Usage

### A. CSV upload to a running backend

The simplest path — exercises the real `/api/projects/{id}/bom/upload` route.
The project must already exist in the store first (the seeded demo project
uses ID `HYD-MAHADEV-220`, but you'll need to add it manually since the
shipped backend hardcodes its own demo IDs).

```bash
# from the repo root
python -m fixtures.hydro.load_hydro upload-bom http://127.0.0.1:8010 HYD-MAHADEV-220
```

### B. Direct in-memory injection (for in-process testing)

Use this when you want every module's store populated without going through
HTTP. Must run in the same Python process as the running app — easiest is
to attach an ipython shell to uvicorn, or write a one-shot script that
imports the loader before `app.main:app` starts serving:

```bash
python -m fixtures.hydro.load_hydro inject
```

This pushes the project + BOM into `app.planning._projects` and
`app.planning._bom_items` directly. Suppliers / inventory / POs / incidents
are appended to the `AgentRequest` returned by `build_demo_request()` — note
that those four are rebuilt on every `GET /api/demo` call from
`sample_data.py`, so for true persistence wire a module-level cache or seed
your own tenant store (relevant once M7.2 lands).

### C. Programmatic access from a test or script

```python
from fixtures.hydro.hydro_seed import build_hydro_demo

demo = build_hydro_demo()
print(demo.project.name)        # Mahadev Hydro 220 MW (2x110)
print(len(demo.bom_items))      # 70
long_lead = [b for b in demo.bom_items if (b.long_lead_days or 0) >= 365]
```

## Design notes

- **Currency**: USD. Real Indian hydro projects price internally in INR and
  externally in USD; demo uses USD throughout for compatibility with the
  schema.
- **Supplier names**: real publicly known hydro EPC suppliers
  (Andritz, Voith, BHEL, Hitachi Energy, Polycab, Tata Steel, ...).
  Spend / OTD / quality numbers are illustrative, not the real firms'
  performance data — invented for demo realism.
- **Spec & drawing IDs**: invented (`SPC-XX-NNN-RN`, `DRG-XX-NNN-RN`) and
  carry no real document references.
- **Milestone dates**: 32-month construction window, mobilization 2025-04-01,
  COD 2027-12-31. Calibrated so that the M07 (spiral case erection) and M08
  (stator stack) milestones have realistic 4-6 month buffers from their
  long-lead supplier delivery dates — i.e. the simulator can plausibly find
  recoverable slack.
- **Incidents**: the six incidents are deliberately chosen to overlap with
  POs in the queue (penstock weld NCR ↔ PO-25-0162; spiral case customs ↔
  PO-25-0124; stator slot reassignment ↔ PO-25-0131) so the AI agent can
  cross-reference them during weekly-plan generation.

## CSV format reference

Required headers: `code`, `description`, `quantity`.

Optional headers (all consumed by the parser): `bom_item_id`, `category`,
`uom`, `unit_cost_usd`, `supplier_name`, `spec_doc_id`, `drawing_id`,
`long_lead_days`, `planned_need_date` (ISO `YYYY-MM-DD`), `milestone_code`.

Items without `spec_doc_id` are imported with status `spec_missing`;
otherwise `planned`.
