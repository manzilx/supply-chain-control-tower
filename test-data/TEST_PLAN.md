# Control Tower — Test Data Pack

Comprehensive QA pack covering every feature in the Supply Chain Control Tower.

## What's in this directory

### Reference + scenarios

| File | What it's for |
|---|---|
| `control-tower-test-pack.xlsx` | Multi-sheet workbook: README, Personas, Projects, BOM library (3 sheets), Suppliers, **58 test scenarios**, coverage matrix, **Edge + Status CSVs**, API reference. Open this first. |
| `TEST_PLAN.md` | This file — quick reference. |
| `_build_pack.py` | Regeneration script. Edit constants + rerun. |

### Bulk BOM uploads (per main project)

| File | Lines | Categories covered |
|---|---|---|
| `bom-arcforge-PRJ-RB-660.csv` | 38 | Forged valves, controls, electrical, piping, civil, fire, HVAC, instrumentation, cooling, rotating equipment |
| `bom-helios-PRJ-NS-OSS.csv` | 32 | Subsea cables, offshore structural, marine epoxy, ROV gear, GIS, mooring, marine equipment |
| `bom-northwind-HYD-MAHADEV-220.csv` | 69 | Hydro turbines, generators, penstocks, GIS, civil/dam, transmission, governor, cooling, lubrication |

### Edge-case + status-mix uploads

| File | Purpose | Target |
|---|---|---|
| `bom-edge-malformed.csv` | 12 rows · 6 bad. Tests row-level error reporting (missing code, bad qty/cost/date/lead, unknown status, special chars, quoted commas, unicode). | Any greenfield project |
| `bom-edge-minimal.csv` | 5 rows · only `code,description,quantity`. Proves the required-fields-only path. | Any greenfield |
| `bom-status-mix-PRJ-RB-660.csv` | 9 rows · 5 delivered + 1 ordered + 3 planned. **Drives Riverbank to in-flight.** | `PRJ-RB-660` |
| `bom-status-mix-PRJ-HE-FPSO.csv` | 9 rows · 5 delivered + 1 ordered + 3 planned. **Drives FPSO to in-flight.** | `PRJ-HE-FPSO` |
| `bom-status-mix-PRJ-NW-STEEL.csv` | 9 rows · 5 delivered + 1 ordered + 3 planned. **Drives Polaris Steel to in-flight.** | `PRJ-NW-STEEL` |

### CSV format

Required: `code, description, quantity`. All other columns optional. Two new columns supported as of this release:

- **`status`** — `spec_missing | planned | requisitioned | ordered | delivered`. Unknown values warn + fall back to default. Case-insensitive.
- **`parent_item_id`** — for nesting BOM items under a parent (hierarchy).

When `status` is absent, status defaults to `spec_missing` (no spec_doc_id) or `planned` (spec_doc_id set).

## Environments

- **Local**: `https://localhost/` (Docker Compose stack, self-signed cert)
- **Fly**: `https://scm-towerx.fly.dev/` (Let's Encrypt, public)

## Quick start (5-minute smoke test)

1. **Sign in** — open the Fly URL, pick any persona from the **Personas** sheet (e.g. `arcforge-admin-01`).
2. **Press ⌘K** — type `helios` or `runner` to verify the command palette works.
3. **Open Overview** — confirm the donut, spend rollup, schedule + activity panels render.
4. **Open Projects** — confirm 4 cards per tenant, one in-flight at ~55% (amber).
5. **Open the in-flight project** (Meridian / Valhall / Kavi) → check the completion breakdown + BOM mix of delivered/ordered/planned.
6. **Switch persona** to a different tenant — confirm the data fully changes.

## Upload a BOM (5 minutes)

1. Sign in as **`arcforge-head-01`** (or admin).
2. Open project **Riverbank 2x660 MW Power Plant** → **BOM** tab.
3. Click **CSV format (expand)** → drop in `bom-arcforge-PRJ-RB-660.csv`.
4. Observe `rows_parsed=38`, `rows_accepted=38`, new lines appear with their statuses.
5. Switch to **Procurement Plan** tab — packages should now include the long-lead + missing-spec flags from the upload.

Repeat for **`helios-head-01` → PRJ-NS-OSS** and **`northwind-head-01` → HYD-MAHADEV-220**.

## Test priority

| Priority | What it covers | Count |
|---|---|---|
| **P1** | Core flows — auth, tenant isolation, portfolio, palette, project detail, BOM upload (incl. error path + status-mix), full PR→RFQ→Award→PO chain, vendor intel, expediting, logistics, commercial, weekly plan, audit, RBAC, cross-tenant denial | ~28 scenarios |
| **P2** | Polish + advanced — skeletons, prefetch, TBE, simulations, AI features, SAP submission, mode recommender, exports, minimal-CSV path, unknown-status warning, case-insensitive status | ~26 scenarios |
| **P3** | Optional / external — webhooks, integrations health | ~4 scenarios |

## Watch-the-metric-react demo (3 minutes)

The cleanest way to show the completion metric responding in real time:

1. Sign in as **`arcforge-head-01`** → Overview. Note the donut + bucket distribution.
2. Open **PRJ-RB-660** (Riverbank) → BOM tab → upload **`bom-status-mix-PRJ-RB-660.csv`**.
3. Wait 10s (portfolio cache TTL), reload `/overview`.
4. Riverbank should have moved from the **Planning (0%)** bucket to the **In progress (25-70%)** bucket; donut average climbs.
5. Repeat for `helios-head-01` → `PRJ-HE-FPSO` and `northwind-head-01` → `PRJ-NW-STEEL`.

By the end every tenant has 2 in-flight projects instead of 1.

## Direct API testing

Get a token:
```bash
TOK=$(curl -ksS -X POST https://scm-towerx.fly.dev/api/auth/login \
  -H 'content-type: application/json' \
  -d '{"user_id":"arcforge-admin-01"}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')
```

Try each endpoint from the **API Reference** sheet:
```bash
curl -sS https://scm-towerx.fly.dev/api/portfolio/summary -H "Authorization: Bearer $TOK" | python3 -m json.tool
curl -sS https://scm-towerx.fly.dev/api/search/index     -H "Authorization: Bearer $TOK" | python3 -m json.tool | head -40
curl -sS https://scm-towerx.fly.dev/api/projects/progress -H "Authorization: Bearer $TOK" | python3 -m json.tool
```

Cross-tenant denial check (should return 404):
```bash
curl -sS -o /dev/null -w "%{http_code}\n" \
  https://scm-towerx.fly.dev/api/projects/HYD-MAHADEV-220 \
  -H "Authorization: Bearer $TOK"
# expect: 404 (arcforge admin cannot read northwind's hydro project)
```

## Regenerating the pack

```bash
cd test-data
python3 _build_pack.py
```

The build script is self-contained. Edit constants at the top (`BOM_*`, `SUPPLIERS`, `SCENARIOS`, `APIS`, `PROJECTS`, `ROLES`) to extend the pack.
