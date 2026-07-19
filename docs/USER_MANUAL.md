# Project Control Tower — User Manual

A user-facing guide to every page, every feature, and the common workflows that tie them together. If you're setting up a deployment, see the README. This document is for the people running the day-to-day procurement work.

---

## Contents

1. [What this app does](#what-this-app-does)
2. [Quick start](#quick-start)
3. [Navigation](#navigation)
4. [The pages](#the-pages)
   - [Overview](#overview)
   - [Projects](#projects)
   - [Sourcing — PR → RFQ → Quote → Award → PO](#sourcing)
   - [Vendors](#vendors)
   - [Expediting](#expediting)
   - [Logistics](#logistics)
   - [Commercial](#commercial)
   - [Risks](#risks)
   - [Simulate (what-if)](#simulate)
   - [Weekly Plan](#weekly-plan)
   - [AI Command Center (chat)](#agent)
   - [Inventory](#inventory)
   - [Scenario editor](#scenario)
5. [AI features](#ai-features)
6. [Common workflows](#common-workflows)
7. [Configuration & operations](#configuration)
8. [Troubleshooting](#troubleshooting)
9. [Glossary](#glossary)

---

## <a id="what-this-app-does"></a>1. What this app does

The Control Tower is an AI-assisted procurement cockpit for engineering, EPC, and project-driven industrial work. It's built around the idea that on an EPC project, procurement is the function that decides whether milestones are hit — so every signal (BOM, vendor performance, quotes, expediting, logistics, commercial roll-up) lives in one place, with AI that synthesises the picture rather than just summarising it.

Five modules, all wired together:

| Module | What it owns |
|---|---|
| **Planning** | Projects, milestones, BOM, procurement plan, long-lead detection, missing-spec flags |
| **Sourcing** | Purchase Requisitions → RFQs → Quotes → Awards → Sourcing POs |
| **Vendor Intelligence** | Multi-dimension scorecards, category concentration, single-source flags, alternates |
| **Expediting & Logistics** | Slippage prediction, follow-up email drafting, shipment stage tracking, mode recommender |
| **Commercial & Risk** | Budget vs quoted vs PO, savings/overruns, what-if simulations, AI risk briefings |

The **AI Command Center** sits on top of all five: a chat agent that can call tools across every module, plus per-page AI features (mitigations, briefings, narratives, explain buttons).

---

## <a id="quick-start"></a>2. Quick start

```bash
make install   # one-time: creates .venv, installs deps
make demo      # boots backend, seeds data, starts frontend
```

Then open **http://127.0.0.1:3001/** in your browser. The first page is the Overview.

That's it. `make demo` handles the whole boot sequence: kills stale processes, starts the FastAPI backend on port 8010 with the Mahadev Hydro fixture pre-loaded, runs the sourcing seeder (which walks 15 BOM items through the full PR→PO lifecycle), then starts the Next.js frontend on port 3001.

**Other commands you'll use:**

| Command | What it does |
|---|---|
| `make stop` | Cleanly kills backend + frontend |
| `make status` | Shows which services are up + their PIDs |
| `make logs` | Tails the three log files (Ctrl-C to exit) |
| `make seed` | Re-runs the sourcing seeder against a live backend (useful after the backend restarts and you lose in-memory state) |
| `make backend-only` | Backend + seed, skip frontend |
| `make fe-only` | Frontend only (assumes backend already up) |

---

## <a id="navigation"></a>3. Navigation

The left sidebar groups pages into 4 sections that map to how procurement work flows:

| Group | Pages |
|---|---|
| **Plan** | Projects |
| **Sourcing** | PRs, RFQs, Quotes, POs |
| **Monitor** | Overview, Risks, Actions |
| **Operate** | Vendors, Inventory, POs (legacy), Expediting, Logistics |
| **Intelligence** | Agent (chat), Weekly Plan, Simulate, Commercial, Scenario |

Top bar shows the **active scenario** (current company + sector), an **overall risk score**, **Load Demo** / **Run Analysis** buttons, and (when M7 lands) the active user + tenant.

---

## <a id="the-pages"></a>4. The pages

### <a id="overview"></a>Overview

The dashboard. What you see first.

**What's on it:**
- **Overall risk score** (0–100) computed from the rolled-up top risks
- **Watch metrics** — current OTD, open incidents, value at risk, lead-time pressure
- **Top recommended actions** (P1 / P2 / P3 with owners and rationale)
- **AI executive prose brief** — when `XAI_API_KEY` is set, this is Grok-generated; otherwise a deterministic summary

**How to use it:**
- The score and metrics refresh whenever you click **Run Analysis** in the top bar
- The recommended actions are the same pool that feeds the Weekly Plan, but trimmed to the most critical
- The prose brief is meant to be readable to a non-procurement stakeholder (project sponsor, GM)

---

### <a id="projects"></a>Projects

Each project (e.g. *Mahadev Hydro 220 MW*) has three tabs.

#### Project / Overview tab
- Client, site, sector, currency, start date
- Milestone timeline — each milestone with phase (engineering / procurement / fabrication / delivery / installation / commissioning), required-on-site date, and a visual indicator of past/future
- **Explain project** button (top right) — calls AI for a "what should I know" brief

#### BOM tab
The Bill of Materials grid. Every line carries: code, description, quantity, UoM, unit cost, supplier, lead time, need-by date, milestone code, spec doc reference, drawing reference, status.

**Statuses:**
- `spec_missing` — no spec_doc_id linked (red badge)
- `planned` — has spec, not yet requisitioned
- `requisitioned`, `ordered`, `delivered` — downstream lifecycle

**What you can do:**
- **Upload CSV** (top right) — bulk-replace or extend the BOM. The endpoint takes any CSV with required headers `code`, `description`, `quantity`. Optional columns: `bom_item_id` (provide to overwrite-in-place), `category`, `uom`, `unit_cost_usd`, `supplier_name`, `spec_doc_id`, `drawing_id`, `long_lead_days`, `planned_need_date` (ISO `YYYY-MM-DD`), `milestone_code`. Items without `spec_doc_id` are imported with status `spec_missing`.
- **Filter** by status (All / Planned / Spec Missing / Ordered / Delivered) and search by code or description
- **Create PR** — every row has a button that drops a Purchase Requisition pre-filled from the BOM line, into the Sourcing workbench
- Long-lead items are highlighted (lead time ≥ 90d shown in yellow; ≥ 365d in red)

#### Procurement Plan tab
The auto-generated plan that groups BOM items by milestone.

**What it shows:**
- Each milestone with a **package** (group of BOM items needed for it) — count, total value, earliest need date
- **Long-lead flags**: items where need date − today ≤ long_lead_days
- **Missing-spec flags**: items with no spec_doc_id
- Summary KPIs: total BOM lines, packages, long-lead count, missing-spec count, total value

**How to use it:**
- This is the planner's view of "what do I need to procure, by when, and what's at risk of not making the milestone"
- Spec gaps and long-lead pressure both feed the Weekly Plan as P1 actions automatically

---

### <a id="sourcing"></a>Sourcing — PR → RFQ → Quote → Award → PO

The procurement workflow surface. Each sub-page is a workbench for one stage.

#### PR (Purchase Requisition)
- List of all PRs sorted by created_at (newest first)
- Each PR shows: PR no, project, code, description, quantity, need-by, buyer, strategy (single_source / multi_source / rate_contract / emergency_buy), status, linked RFQ/Award/PO
- Click any PR for a detail page with the full lineage

**How to create a PR:**
- From the BOM tab (Create PR button)
- Or via API: `POST /api/prs` with `{project_id, bom_item_id, ...}` or freeform `{project_id, code, description, quantity, uom, need_by, milestone_code, budget_value_usd, buyer, strategy}`

#### RFQ (Request for Quotation)
- List of RFQs (open / quotes_received / evaluated / awarded / cancelled)
- Click any RFQ for the detail page:
  - PR link, code, description, quantity, vendors invited, issued/due dates, status
  - **Quotes** section: existing quotes from each invited vendor
  - **Add a Quote** form: vendor (from invited list), unit price, lead time, incoterm, validity, notes
  - **Comparison** section: appears once 2+ quotes are received — weighted score ranking (price / lead-time / reliability), recommended vendor with rationale
  - **Award** button: pick the winning quote, write a rationale (or let AI generate it)

**How to issue an RFQ:**
- From a PR detail page (Issue RFQ button)
- Or via API: `POST /api/rfqs` with `{pr_no, vendors: [...], due_in_days, notes}`

#### Quote
- Quotes are added under each RFQ (not a separate top-level page)
- Each quote: unit_price_usd, lead_time_days, incoterm, validity_days, optional notes
- The comparison engine ranks all quotes for an RFQ by **composite score** = weighted blend of price index (lowest = 1.0), lead-time index, vendor reliability score from the scorecard

#### Award
- Awards are the act of picking a winner. Each award creates a `Sourcing PO` automatically.
- The **rationale** field can be:
  - Provided by the user
  - Generated by AI (Grok cites concrete price diffs, lead-time gaps, scorecard components, risk flags) — automatic when `XAI_API_KEY` is set
  - Fallback to the comparison-engine string

#### Sourcing PO
- List of POs created via the sourcing flow (separate from legacy scenario POs)
- Each PO carries: po_no, vendor, code, description, quantity, value_usd, incoterm, need_by, lead_time_days, status (draft / released / in_transit / delivered)
- Click any PO for the **timeline** view — full event log (pr_created → rfq_issued → quote_received → evaluated → awarded → po_created)

---

### <a id="vendors"></a>Vendors

#### Vendors list
- All vendors with their **composite score** (0–100) and **grade** (A–F)
- Columns: vendor, category, country, composite score, OTD %, quality PPM, annual spend, flags count, single-source exposure (badge)
- Sortable. Click any vendor for the detail page.

#### Vendor detail
- Full scorecard with **6-dimension radar chart** (delivery / quality / price / responsiveness / claims / risk)
- Each dimension shows score (0–100), grade, value, and a one-line note
- **Alternates** — same-category vendors ranked by score with a "why they'd be better" reason
- **Category concentration** — what share of category spend goes to this vendor
- **Active risk flags** — list of flags from the scorecard
- **AI risk briefing** (top section) — when Grok is on: headline + 2-3 paragraph body + 3-5 item watchlist. Falls back to a deterministic summary otherwise.

#### Concentration
The Concentration view (linked from /vendors) shows category-level rollups: which categories have only one approved vendor, which have heavy concentration with the top supplier, total spend by category.

---

### <a id="expediting"></a>Expediting

The queue of in-flight POs ranked by slippage risk.

**What you see:**
- Summary KPIs: total POs, count in each urgency bucket (escalate / nudge / watch / ok), total value at risk
- Table of POs with: PO number, supplier, description, quantity, value, due-in-days, predicted slip days, slip probability (%), urgency, reasons (risk signals)
- Urgency rules:
  - `escalate` — high slip probability, high value, no expedite option
  - `nudge` — moderate slip risk, expedite still possible
  - `watch` — minor flags, no action needed yet
  - `ok` — on track

**Draft a follow-up email:**
- Click any PO row to open the follow-up modal
- Pick tone: `standard` / `firm` / `urgent`
- Optionally toggle "Request documents" and add extra context notes
- Click **Draft** — the modal fills with:
  - Subject line (with tone prefix)
  - Recipient placeholder (`procurement@vendor.com`)
  - Body — Grok-generated when key is set, otherwise a tone-aware template
  - Requested documents list
- Copy/paste into your email client. The app doesn't send mail; this is a drafting aid.

---

### <a id="logistics"></a>Logistics

Shipment-level tracking once a PO has been issued.

**What you see:**
- KPIs: total shipments, in-motion, at-bottleneck, delivered, value in motion
- Table per shipment with: PO ref, vendor, origin, destination, value, mode (sea / air / road / rail / local), current stage, required-on-site, estimated arrival, bottleneck flag, slack days

**Stages** (in order): manufacturing → ready_to_dispatch → dispatched → in_transit → at_port → at_customs → last_mile → delivered.

**Bottlenecks** are flagged when a shipment dwells at a stage longer than the typical baseline (e.g. >5 days at_customs).

**Mode recommendation** — for any shipment that's late or has tight slack, the **Recommend mode** button surfaces:
- Recommended mode (often `air` for late, high-value, time-critical)
- Cost multiplier vs current mode
- Transit days estimate
- Rationale citing slack days and required-on-site

**How to add a stage event:**
- Click any shipment row, click **Add event**
- Pick stage, location, optional note
- Endpoint: `POST /api/logistics/shipments/{po_ref}/events`

---

### <a id="commercial"></a>Commercial

The financial roll-up — budget vs quoted vs awarded vs final PO, across all projects.

**What you see:**
- Total budget, total awarded, total savings, savings %
- Per-project breakdown: line count, total budget, total awarded, savings %, variance %, over-budget line count
- **Top savings** — biggest favourable variances
- **Top overruns** — biggest unfavourable variances
- Each commercial line: project, code, vendor, budget, quoted, awarded, final PO value, savings, variance %, state (budget_only / quoted / awarded / delivered)

**How values flow in:**
- BOM unit_cost × quantity → budget_value
- Winning quote total_usd → quoted_value
- Award awarded_value_usd → awarded_value
- Sourcing PO value_usd → final_po_value
- Savings = budget − awarded; variance % = (awarded − budget) / budget

---

### <a id="risks"></a>Risks

The Risk Register — every risk surfaced by the current analysis.

**Risk types:**
- **inventory_gap** — projected 30-day demand exceeds on-hand + open orders
- **supplier_reliability** — supplier OTD < 92%, or PPM > 1000, or has risk flags, or 0 alternatives
- **single_source** — supplier is the only approved source AND annual spend ≥ $500k
- **po_slip** — PO due ≤14d with status planned/released, or currently delayed
- **incident** — open incident on file (carries severity directly)

**What you see per row:**
- Title, summary, type, severity (low / medium / high / critical), score (0–100), affected supplier or SKU, owner

**Filters:** severity, type, free-text search.

**Per-risk AI actions** (in the rightmost column):
- **Mitigations** — expands an inline panel with 3 concrete, named actions (Grok-generated or deterministic by type)
- **Explain** — full "what should I know" brief with headline, body, bullets, and source attribution

The register **diversifies by type** automatically — the engine takes up to 5 risks per type before topping up to 20, so inventory gaps don't crowd out supplier or single-source signals.

---

### <a id="simulate"></a>Simulate (what-if)

Stress-test the current state with one of three scenarios.

**Available scenarios:**

| Scenario | What it models |
|---|---|
| `vendor_slip_2w` | A named vendor slips by 14 days (default; configurable via `custom_slip_days`). Computes cost delta (expediting / freight upgrade) and which milestones move. |
| `customs_hold` | A named shipment held at customs for 14 days. Surfaces what gets delayed downstream. |
| `alt_vendor` | Switch a target item to an alternate vendor. Computes price delta + lead-time delta. Requires `alternate_vendor` param. |

**How to use:**
1. Pick scenario from dropdown
2. Pick **target** (vendor name, PO number, or BOM code depending on scenario)
3. For `alt_vendor`: also pick alternate from the dropdown
4. Click **Run simulation**

**What you get back:**
- **Headline** + severity badge
- KPIs: cost delta, schedule delta, affected items count
- **Affected items** table — each line with original need date and new expected date
- **Milestone impacts** table — milestone name + slip days
- **Mitigations** — 2-4 concrete actions to take
- **AI executive narrative** — when Grok is on: 2-paragraph narrative readable to the project sponsor

---

### <a id="weekly-plan"></a>Weekly Plan

The AI command center's flagship output — a prioritized action list for the week.

**What you see:**
- **Headline** — single sentence summary
- **KPI snapshot** — 6 tiles (open POs, value at risk, escalations, missing specs, vendor reliability, schedule pressure)
- **AI synthesis** (when Grok is on) — 2-paragraph narrative woven across the whole plan
- **Items table** — each action with priority (P1 / P2 / P3), category (planning / expediting / vendor_risk / logistics / commercial / sourcing), title, why, expected impact, owner, due-in-days, confidence %, supporting refs

**Where items come from:**
- Missing-spec BOM items → P1 planning actions
- Escalation-tier expediting POs → P1 expediting actions
- Single-source flags → P2 vendor_risk actions
- Bottlenecked shipments → P2 logistics actions
- Significant overruns → P3 commercial actions

The deterministic rules produce items; Grok synthesises the narrative on top.

---

### <a id="agent"></a>AI Command Center (chat)

The conversational interface to everything.

**How to use it:**
- Type a question; press Enter or click **Send**
- Suggestions on first load (Show me this week's plan, Which vendors are most likely to cause delays?, Draft an urgent follow-up for PO-24017, etc.)
- Click **New chat** to clear history

**What the agent can do** (via 15 tools):

| Tool | Purpose |
|---|---|
| `build_weekly_plan` | Returns the full weekly plan |
| `get_top_risks` | Risk register |
| `get_expedite_queue` | Slipping POs |
| `predict_slip` | Slip prediction for one PO |
| `draft_followup_email` | Composes a follow-up email |
| `get_vendor_scorecard` | One vendor's full scorecard |
| `list_vendors` | All vendors |
| `get_category_concentration` | Category-level concentration |
| `get_commercial_summary` | Budget vs awarded rollup |
| `get_logistics_queue` | Current shipments |
| `recommend_mode` | Freight mode recommendation |
| `get_procurement_plan` | Project's procurement plan |
| `list_projects` | All projects |
| `get_open_rfqs` / `get_open_prs` | Sourcing items in flight |
| `run_simulation` | What-if scenario |

**Two modes:**
- **Grok mode** (when `XAI_API_KEY` set): Grok plans tool calls dynamically, decides which to invoke, synthesises a response. Source shows `via Grok`.
- **Deterministic mode** (default): keyword-based router picks tools, formats result. Source shows `via Rule-based`.

**Output format:**
- Bubble at top: prose summary in markdown (bold, headers, lists, GFM tables all render)
- Below the bubble: **structured tables** auto-generated for known tool outputs:
  - `build_weekly_plan` → priority pills, full action grid
  - `get_expedite_queue` → urgency-coded grid
  - `list_vendors` → score grid
  - `get_top_risks` → severity pills
  - `get_open_prs` / `get_open_rfqs` → sourcing tables
- Below that: **tool call audit** (collapsed) — exact tool name + args + summary, expandable to show full JSON response

**Persona detection:**
The agent auto-detects which persona to label the response with (Sourcing / Expediting / Vendor-risk / Logistics / Commercial / Planning / Reporting / Control Tower). This is shown in the small uppercase label above each reply.

---

### <a id="inventory"></a>Inventory

The operational inventory list — SKUs you stock for projects.

**What you see per row:**
- SKU, description, category, supplier
- On-hand quantity, reorder point, safety stock, daily demand
- Lead time (days), unit cost
- Criticality (low / medium / high / mission-critical)

**How to use:**
- Filter by criticality, supplier, or category
- Items at-or-below reorder point are visually flagged
- Items with shortage_qty > 0 over the next 30 days feed the Risk register as `inventory_gap` risks

This page is read-only for now. To modify inventory, edit the scenario JSON (Scenario editor) or the `sample_data.py` / `fixtures/hydro/hydro_seed.py` seeders.

---

### <a id="scenario"></a>Scenario editor

A raw JSON editor over the full active scenario (company, suppliers, inventory, POs, demand signals, incidents, ask).

**When to use it:**
- Bulk-edit a snapshot before re-running analysis
- Inject test data not covered by the fixtures
- See the raw shape of every field used by the analyzer

**How to use it:**
- Each section is its own textarea with prettified JSON
- Edit, click **Save scenario** to update the in-memory store
- Then click **Run Analysis** in the top bar to refresh the dashboards

Note: scenario changes are in-memory only. They reset on backend restart.

---

## <a id="ai-features"></a>5. AI features

Every AI feature has two paths: **Grok-powered** (when `XAI_API_KEY` is set) and **deterministic fallback** (when it isn't, or when a Grok call fails). Each response carries a `source: "grok" | "deterministic"` field so you can see which path produced the output.

### Setup

```bash
cd /Users/manzils/supply-chain-control-tower
cp .env.example .env
# edit .env: set XAI_API_KEY=xai-...
make stop && make demo
```

`.env` is gitignored; `.env.example` documents every variable.

### Where AI surfaces in the UI

| Page | Feature |
|---|---|
| `/overview` | Executive prose brief at the top of the page |
| `/agent` | Tool-calling chat with markdown + structured table rendering |
| `/risks` | "Mitigations" toggle on every row → 3 concrete actions |
| `/risks` | "Explain" button on every row → headline + body + bullets |
| `/vendors/[name]` | AI risk briefing section above the scorecard |
| `/projects/[id]` | "Explain project" button (top right of header) |
| `/simulate` | 2-paragraph executive narrative below the simulation headline |
| `/weekly-plan` | AI synthesis card between KPI snapshot and items |
| Sourcing — award flow | Grok-generated award rationale (cited diffs) |
| Expediting — follow-up email | Grok-drafted email body (tone-aware) |

### AI features available via API

| Endpoint | What it does |
|---|---|
| `POST /api/explain` `{kind, id}` | "What should I know" brief for PO / vendor / risk / project / RFQ / PR |
| `POST /api/risks/mitigations` `RiskRecord` | 3 concrete mitigations for one risk |
| `GET /api/vendors/intel/{name}/briefing` | Full vendor briefing (headline + body + watchlist) |
| `POST /api/projects/{id}/bom/autofill` | Proposes category + supplier for sparse BOM rows |
| `POST /api/projects/{id}/bom/{bom_id}/spec-request` | Drafts an email to engineering for a missing-spec BOM item |
| `POST /api/chat` `{message, history}` | Conversational agent with tool-calling |

### Switching back to deterministic

Remove `XAI_API_KEY` from `.env` (or set it to empty) and restart. Every endpoint will flip to `source: "deterministic"` and use its templated fallback. The app continues to work fully — Grok adds polish, it isn't load-bearing.

---

## <a id="common-workflows"></a>6. Common workflows

### Workflow A — From BOM upload to first PO

1. Open the project at `/projects/HYD-MAHADEV-220`
2. Click **BOM** tab
3. Click **Upload CSV** (top right), pick your BOM CSV
4. Wait for the import report (rows accepted / rejected / errors)
5. Click the **Procurement Plan** tab — verify long-lead and missing-spec items are flagged correctly
6. For each long-lead item: click **Create PR** on the BOM row
7. Open the PR at `/sourcing/prs/PR-NNNNN`
8. Click **Issue RFQ** — pick 2-3 vendors (suggestions are pre-filled from category + scorecard)
9. Wait for vendors to quote (or use the **Add Quote** form to log received quotes)
10. Once 2+ quotes are in, the **Comparison** section ranks them by composite score
11. Click **Award** on the winning quote — accept the AI-generated rationale or write your own
12. A Sourcing PO is auto-created and appears in `/sourcing/pos`

### Workflow B — Slipping PO → follow-up email

1. Open `/expediting`
2. Sort by urgency; focus on the **escalate** rows
3. Click any PO row to open the follow-up modal
4. Pick tone (`urgent` for escalate, `firm` for nudge, `standard` for watch)
5. Toggle **Request documents** on (default)
6. Add extra context if you have something specific to flag
7. Click **Draft email**
8. The body is generated — Grok cites the slip signals and asks for concrete commitments
9. Copy the subject + body, paste into your email client, send
10. After sending, optionally log a shipment event on the corresponding shipment so the slip is tracked

### Workflow C — Weekly review (15-min routine)

1. Open `/overview` — read the AI prose brief, glance at the risk score and watch metrics
2. Open `/weekly-plan` — read the **AI synthesis** card (when Grok is on)
3. For each P1 action: assign or confirm the owner; the action card shows current owner and due-in-days
4. Open `/risks` — for any new critical risks, click **Mitigations** to see what to do
5. Open `/agent` — ask follow-up questions ("show me long-lead items threatening turbine commissioning") and let the agent pull data from across modules

### Workflow D — What-if a vendor slips

1. Open `/simulate`
2. Pick scenario `vendor_slip_2w`
3. Pick **target** = the supplier you're worried about (e.g. `Andritz Hydro`)
4. Optionally set `custom_slip_days` (default 14)
5. Click **Run simulation**
6. Read the **AI executive narrative** card (when Grok is on) — it explains the impact in plain prose
7. Review the **milestone impacts** table — which milestones move, by how many days
8. Review the **mitigations** list — these are pre-baked recovery actions
9. If the impact is unacceptable, run the `alt_vendor` scenario for the same target to see the cost of switching

### Workflow E — Vendor risk review

1. Open `/vendors`
2. Sort by **composite score** ascending — work the bottom of the list first
3. Click any vendor for the detail page
4. Read the **AI risk briefing** at the top — it summarises the scorecard, flags, recent POs, recent incidents
5. Read the **watchlist** — these are specific items to monitor
6. Check the **alternates** section — is there a stronger same-category vendor you should shift volume to?
7. If single-source exposure: use the **alt_vendor** simulation to estimate the switching cost

### Workflow F — Filling sparse BOM data (AI auto-fill)

1. Open the BOM tab of a project where rows are missing category or supplier
2. (For now via API) `POST /api/projects/{id}/bom/autofill`
3. Returns a list of suggestions per sparse row: code, current values, suggested category, suggested supplier, reason
4. Review suggestions
5. To apply: re-upload a CSV with the suggested values + the existing `bom_item_id`s

(A UI for this is on the roadmap; the API works today.)

---

## <a id="configuration"></a>7. Configuration & operations

### Env vars (.env)

| Variable | Default | Purpose |
|---|---|---|
| `XAI_API_KEY` | _(unset)_ | Required to enable Grok. Without it, all AI features fall back to deterministic templates. |
| `XAI_MODEL` | `grok-4-1-fast-reasoning` | Model ID. Override if xAI releases a newer version. |
| `XAI_BASE_URL` | `https://api.x.ai/v1` | xAI API endpoint. |
| `XAI_REASONING_EFFORT` | _(unset)_ | `low` or `high` to override Grok's default reasoning depth. |
| `BACKEND_PORT` | `8010` | Backend port. |
| `FRONTEND_PORT` | `3001` | Frontend port. |
| `ALLOWED_ORIGINS` | _(regex match for localhost)_ | CORS allowlist. |

### Where state lives

Everything is in-memory. The backend rebuilds its state from `app/sample_data.py` + `fixtures/hydro/` on every boot. After a restart, the project + BOM are restored automatically; the sourcing workflow (PRs, RFQs, awards, POs) needs `make seed` to re-walk.

### Logs

- `.logs/backend.log` — uvicorn logs (warnings + above)
- `.logs/frontend.log` — Next.js dev output
- `.logs/seed.log` — last sourcing seeder run

`make logs` tails all three.

### PIDs

- `.pids/backend.pid`, `.pids/frontend.pid` — written by the orchestrator, used by `make stop` and `make status`

### Files you might want to edit

| File | What's in it |
|---|---|
| `app/sample_data.py` | Legacy demo scenario (Arcforge, etc.) |
| `fixtures/hydro/hydro_seed.py` | Mahadev Hydro project, BOM, suppliers, inventory, POs, incidents |
| `fixtures/hydro/bom_hydro.csv` | The hydro BOM as a CSV (uploadable to other projects) |
| `fixtures/seed_sourcing.py` | The 14 BOM items walked through the full sourcing lifecycle |

---

## <a id="troubleshooting"></a>8. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `make demo` says backend timed out | Port 8010 was held by a stale process the cleanup missed | `lsof -ti :8010 \| xargs kill -9 ; make demo` |
| Frontend says "Failed to bootstrap scenario" | Backend not running, or CORS misconfigured | `make status` to check; `make logs` to inspect |
| Chat replies always say `source: "deterministic"` even though `XAI_API_KEY` is set | `.env` wasn't sourced before backend started, OR the key is invalid | `make stop && make demo`; check `.logs/backend.log` for `xai` errors |
| Awards return the template rationale (not Grok) | Same as above — Grok call failed silently and fell back | Verify key with `curl -H "Authorization: Bearer $XAI_API_KEY" https://api.x.ai/v1/models` |
| BOM upload returns "CSV must have headers: code, description, quantity" | Required columns missing | Check first row of CSV; column names must match exactly (case-sensitive) |
| RFQ "Comparison needs quotes" | Fewer than 2 quotes received | Add at least 2 via the Add Quote form |
| /sourcing pages empty after restart | In-memory sourcing state was lost | `make seed` to re-walk the 14 demo items |
| Risk score is 100/100 with all inventory_gap | An older boot before the analyzer cap was raised; should not happen with current code | `make stop && make demo` to pick up latest analyzer |
| "Next dev server keeps crashing" or "Cannot find module ./NNN.js" | Stale `.next/` cache from a `next build` run mixed with dev | `cd frontend && rm -rf .next && cd .. && make stop && make demo` |

---

## <a id="glossary"></a>9. Glossary

**BOM (Bill of Materials)** — The list of items engineering needs procurement to source for a project. Multi-level (assemblies → sub-assemblies → parts).

**PR (Purchase Requisition)** — Internal authorization that asks procurement to source a specific item. Created from a BOM line.

**RFQ (Request for Quotation)** — Sent to multiple vendors asking for price + lead time for one or more PR'd items.

**Quote** — A vendor's response to an RFQ: unit price, lead time, terms, validity.

**Award** — The act of selecting the winning quote. Triggers PO creation.

**PO (Purchase Order)** — The formal order to the vendor, derived from the award.

**OTD (On-Time Delivery %)** — Share of past POs delivered by their committed date.

**PPM (Parts Per Million)** — Quality defect rate. Lower is better.

**Composite Score (0–100)** — Weighted blend of a vendor's 6-dim performance (delivery / quality / price / responsiveness / claims / risk).

**Single-source exposure** — Only one approved vendor for a category with significant annual spend. A continuity risk.

**Long-lead item** — A BOM line whose vendor lead time exceeds a threshold (default 90 days for the planner; 365 for "critical long-lead"). Drives the procurement plan's milestone alignment.

**Missing spec** — A BOM line with no `spec_doc_id` linked. Procurement can't issue a PR without engineering releasing the spec first.

**Milestone** — A project schedule anchor with a required-on-site date and a phase (engineering / procurement / fabrication / delivery / installation / commissioning).

**Procurement plan** — Auto-generated grouping of BOM items by milestone, with long-lead and missing-spec flags surfaced.

**Expediting** — The practice of actively chasing vendors on in-flight POs to prevent slippage.

**Slip / Slippage** — How much later than committed a PO is expected to arrive.

**Bottleneck** — A logistics stage where a shipment is stuck longer than the baseline (e.g. >5 days at customs).

**Incoterm** — International commercial term defining who pays for and bears risk over which leg of shipment (EXW / FCA / FOB / CIF / CIP / DAP / DDP).

**Composite score → Grade** — A=80+, B=70+, C=60+, D=50+, F<50.

**EPC (Engineering, Procurement, Construction)** — The integrated delivery model for large capital projects (power plants, refineries, hydro, etc.).

**ICT (Inter-Connection Transformer)** — A power transformer connecting two grid voltage levels.

**LD (Liquidated Damages)** — Contractual penalty for delay, usually a % of contract value per day.

**FAT (Factory Acceptance Test)** — Tests at the vendor's factory before dispatch, witnessed by the buyer.

**RFE (Ready For Erection)** — A milestone meaning all materials for a structure/equipment are on site and erection can begin.

**Critical path** — The chain of activities that, if delayed, delays the whole project.
