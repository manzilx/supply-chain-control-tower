<!-- converted from Project_Control_Tower_User_Manual.docx -->


PROCUREMENT INTELLIGENCE  ·  V 1 . 0
Project Control
Tower
User Manual

AI-assisted procurement cockpit for engineering, EPC, and project-driven industrial work — one place for BOMs, vendor scorecards, sourcing, expediting, logistics, commercials, risk, and an AI agent that ties them together.

MAY  2026  ·  RELEASE  1.0
For procurement managers, buyers, expediters, and project sponsors

CONTENTS
Table of Contents

PART 1
# What this app does
The Control Tower is an AI-assisted procurement cockpit for engineering, EPC, and project-driven industrial work. It is built around the observation that, on a capital project, procurement is the function that decides whether milestones are hit. Every signal that matters — BOM completeness, vendor reliability, quote competitiveness, expediting urgency, logistics dwell, commercial variance — lives in one place, and the AI synthesises the picture rather than simply summarising it.
Five modules, all wired together, plus an AI Command Center on top of them:


PART 2
# Quick start
From a fresh clone, two commands take you to a live, fully-seeded demo:
Then open http://127.0.0.1:3001/ in your browser. First page you’ll see is the Overview.
## Other commands

PART 3
# Navigation
The left sidebar groups pages into the four phases of procurement work, plus an Intelligence section for the AI surfaces.
The top bar shows the active scenario (company + sector), an overall risk score, and the Load Demo / Run Analysis buttons. When tenancy lands, it will also show the active user and tenant.

PART 4
# The pages
What follows is a tour of every page in the application — what’s on it, what it’s for, and how to use it.
## 4.1  Overview
The dashboard. The first page you see, and the one to start a daily review from.
### What’s on it
- Overall risk score (0–100) computed from rolled-up top risks.
- Watch metrics — current OTD, open incidents, value at risk, lead-time pressure.
- Top recommended actions (P1 / P2 / P3 with owners and rationale).
- AI executive prose brief — Grok-generated when XAI_API_KEY is set, otherwise a deterministic summary.
### How to use it
- Refresh the score and metrics by clicking Run Analysis in the top bar.
- The recommended actions are a trimmed slice of the Weekly Plan, surfaced to non-procurement stakeholders.
- The prose brief is written to be readable by a project sponsor or GM, not just a buyer.
## 4.2  Projects
Each project (for example, Mahadev Hydro 220 MW) has three tabs: Overview, BOM, and Procurement Plan.
### Project / Overview tab
- Client, site, sector, currency, start date.
- Milestone timeline — every milestone with phase (engineering / procurement / fabrication / delivery / installation / commissioning) and required-on-site date, with a visual indicator of past vs future.
- “Explain project” button (top right) — calls AI for a what-should-I-know brief.
### BOM tab
The Bill of Materials grid. Every line carries: code, description, quantity, UoM, unit cost, supplier, lead time, need-by date, milestone code, spec doc reference, drawing reference, and status.
Statuses

What you can do
- Upload CSV (top right) — bulk-replace or extend the BOM. Required headers: code, description, quantity. Optional: bom_item_id (provide to overwrite-in-place), category, uom, unit_cost_usd, supplier_name, spec_doc_id, drawing_id, long_lead_days, planned_need_date, milestone_code.
- Filter by status (All / Planned / Spec Missing / Ordered / Delivered) and search by code or description.
- Create PR — every row has a button that drops a Purchase Requisition pre-filled from the BOM line into the Sourcing workbench.
- Long-lead items are highlighted: lead time ≥ 90 days in yellow, ≥ 365 days in red.
### Procurement Plan tab
The auto-generated plan that groups BOM items by milestone.
- Each milestone has a procurement package — count of items, total value, earliest need date.
- Long-lead flags fire when need_date − today ≤ long_lead_days.
- Missing-spec flags fire when spec_doc_id is empty.
- Summary KPIs at the top: total BOM lines, packages, long-lead count, missing-spec count, total value.
## 4.3  Sourcing — PR → RFQ → Quote → Award → PO
The procurement workflow surface. Each sub-page is a workbench for one stage of the cycle.
### Purchase Requisitions
- List of all PRs sorted by created date, newest first.
- Each PR shows: PR number, project, code, description, quantity, need-by date, buyer, strategy, status, linked RFQ / Award / PO.
- Click any PR to see its full detail page with downstream lineage.
Create a PR — from the BOM tab’s “Create PR” button, or via API.
### RFQs (Requests for Quotation)
- List of RFQs by status: open · quotes_received · evaluated · awarded · cancelled.
- Click any RFQ for the detail page, which shows: PR link, code, description, quantity, vendors invited, dates, status.
- “Add a Quote” form: vendor (from invited list), unit price, lead time, incoterm, validity, notes.
- Comparison section appears once 2 or more quotes are received — a weighted-score ranking (price / lead-time / reliability) with a recommended vendor and rationale.
- “Award” button: pick the winning quote and write a rationale, or let AI generate it.
### Quotes
Quotes are added under each RFQ, not as a separate top-level page. Each quote carries unit price, lead time, incoterm, validity, and optional notes. The comparison engine ranks all quotes for an RFQ by a composite score — a weighted blend of price index, lead-time index, and vendor reliability from the scorecard.
### Awards
Awards are the act of picking a winner. Each award automatically creates a Sourcing PO.
The rationale can be (a) user-provided, (b) AI-generated — Grok cites concrete price diffs, lead-time gaps, scorecard components, and risk flags when XAI_API_KEY is set, or (c) the comparison-engine string as a last resort.
### Sourcing POs
- List of POs created via the sourcing flow (distinct from legacy scenario POs).
- Each PO: po_no, vendor, code, description, quantity, value, incoterm, need-by, lead time, status (draft / released / in_transit / delivered).
- Click any PO for the timeline view — full event log from pr_created through po_created.
## 4.4  Vendors
### Vendors list
- Every vendor with their composite score (0–100) and grade (A–F).
- Columns: vendor, category, country, composite score, OTD %, quality PPM, annual spend, flags count, single-source exposure.
- Sortable. Click any vendor for the detail page.
### Vendor detail
- Full scorecard with a 6-dimension radar chart: delivery, quality, price, responsiveness, claims, risk.
- Each dimension shows score (0–100), grade, value, and a one-line note.
- Alternates — same-category vendors ranked by score, with a “why they’d be better” reason.
- Category concentration — what share of category spend goes to this vendor.
- Active risk flags — the flag list from the scorecard.
- AI risk briefing at the top: headline · 2–3 paragraph body · 3–5 item watchlist.
## 4.5  Expediting
The queue of in-flight POs ranked by slippage risk.
### What you see
- KPIs: total POs, count in each urgency bucket (escalate / nudge / watch / ok), total value at risk.
- Per-PO row: PO number, supplier, description, quantity, value, due-in-days, predicted slip days, slip probability %, urgency, reasons.
Urgency rules
### Draft a follow-up email
- Click any PO row to open the follow-up modal.
- Pick tone: standard · firm · urgent.
- Toggle Request documents (default on) and add extra context notes if needed.
- Click Draft. The modal fills with subject, recipient placeholder, body, requested-documents list.
- Copy and paste into your email client. The app does not send mail — it is a drafting aid.
## 4.6  Logistics
Shipment-level tracking once a PO has been issued.
- KPIs: total shipments, in-motion, at-bottleneck, delivered, value in motion.
- Per-shipment table with PO ref, vendor, origin, destination, value, mode (sea / air / road / rail / local), current stage, required-on-site, estimated arrival, bottleneck flag, slack days.
Stages, in order: manufacturing → ready_to_dispatch → dispatched → in_transit → at_port → at_customs → last_mile → delivered.
- Bottlenecks fire when a shipment dwells at a stage past its baseline (e.g. > 5 days at customs).
- Mode recommendation surfaces a recommended freight mode (often air, for late + high-value items), with cost multiplier and rationale.
## 4.7  Commercial
The financial roll-up — budget vs quoted vs awarded vs final PO, across all projects.
- Total budget, total awarded, total savings, savings %.
- Per-project breakdown: line count, totals, savings %, variance %, over-budget line count.
- Top savings — biggest favourable variances.
- Top overruns — biggest unfavourable variances.
How values flow in
- BOM unit_cost × quantity → budget_value.
- Winning quote total → quoted_value.
- Award awarded_value → awarded_value.
- Sourcing PO value → final_po_value.
- Savings = budget − awarded. Variance % = (awarded − budget) / budget.
## 4.8  Risks
The Risk Register — every risk surfaced by the current analysis.
### Risk types

- Filters: severity, type, free-text search.
- Each row has two per-risk AI actions: Mitigations (3 concrete actions, expanded inline) and Explain (full “what should I know” brief).
## 4.9  Simulate (what-if)
Stress-test the current state with one of three scenarios.

### Using it
- Pick scenario from the dropdown.
- Pick target — vendor name, PO number, or BOM code depending on scenario.
- For alt_vendor, pick the alternate vendor.
- Click Run simulation.
You get back: headline, severity badge, cost delta, schedule delta, affected items table, milestone impacts, mitigations, and an AI executive narrative (when Grok is on).
## 4.10  Weekly Plan
The AI command center’s flagship output — a prioritised action list for the week.
- Headline summarising the week.
- KPI snapshot — 6 tiles for open POs, value at risk, escalations, missing specs, vendor reliability, schedule pressure.
- AI synthesis (when Grok is on): a 2-paragraph narrative woven across the whole plan.
- Items table: priority (P1/P2/P3) · category · title · why · expected impact · owner · due-in-days · confidence % · supporting refs.
Where items come from: missing-spec BOM items → P1 planning; escalation-tier expediting POs → P1 expediting; single-source flags → P2 vendor_risk; bottlenecked shipments → P2 logistics; significant overruns → P3 commercial.
## 4.11  AI Command Center (chat)
The conversational interface to everything.
### Using it
- Type a question, press Enter or click Send.
- Suggestions appear on first load — e.g. “Show me this week’s plan” or “Draft an urgent follow-up for PO-24017.”
- “New chat” clears the conversation.
### What the agent can call (15 tools)

Two modes: Grok plans tool calls dynamically when XAI_API_KEY is set; otherwise a deterministic keyword router picks tools and formats results. The source label above each reply tells you which path produced it.
Output format: markdown-rendered prose at the top, structured React tables below for known tool outputs (priority pills, urgency colours, currency formatting), and a collapsed tool-call audit at the bottom for verification.
## 4.12  Inventory
The operational inventory list — SKUs you stock for projects.
- Per row: SKU, description, category, supplier, on-hand, reorder point, safety stock, daily demand, lead time, unit cost, criticality (low / medium / high / mission-critical).
- Filter by criticality, supplier, or category.
- Items at or below reorder point are flagged visually.
- Items with a positive 30-day shortage feed the Risk register as inventory_gap risks.
## 4.13  Scenario editor
A raw JSON editor over the full active scenario — company, suppliers, inventory, POs, demand signals, incidents, ask.
- Each section is its own prettified-JSON textarea.
- Edit, click Save scenario to update the in-memory store, then Run Analysis in the top bar.
- Changes are in-memory only. They reset on backend restart.

PART 5
# AI features
Every AI feature has two paths: Grok-powered when XAI_API_KEY is set, and deterministic fallback when it isn’t (or when a Grok call fails). Each response carries a source field so you can see which path produced it.
## 5.1  Setup
Copy .env.example to .env, set XAI_API_KEY=xai-…, then run make stop && make demo. The orchestrator auto-sources .env before launching the backend and frontend.
## 5.2  UI surfaces
## 5.3  API surfaces

PART 6
# Common workflows
Six end-to-end stories. Each is the standard happy path; deviations and exceptions are flagged inline.
## Workflow A  ·  From BOM upload to first PO
- Open the project page at /projects/<id>.
- Click the BOM tab.
- Click Upload CSV (top right), pick your BOM CSV.
- Wait for the import report: rows accepted / rejected / errors.
- Open the Procurement Plan tab to verify long-lead and missing-spec items are flagged correctly.
- For each long-lead item, click Create PR on the BOM row.
- Open the PR detail page and click Issue RFQ. Pick 2–3 vendors (suggestions pre-filled from category + scorecard).
- Wait for vendor responses, or log them yourself via Add Quote.
- Once 2+ quotes are in, the Comparison section ranks them.
- Click Award on the winning quote — accept the AI rationale or write your own.
- A Sourcing PO is auto-created and appears in /sourcing/pos.
## Workflow B  ·  Slipping PO → follow-up email
- Open /expediting.
- Sort by urgency. Work the escalate rows first.
- Click a PO row to open the follow-up modal.
- Pick tone — urgent for escalate, firm for nudge, standard for watch.
- Toggle Request documents on; add extra context if needed.
- Click Draft email. Body is generated, citing slip signals and asking for concrete commitments.
- Copy subject + body, paste into your email client, send.
- Optionally log a shipment event on the matching shipment so the slip is tracked.
## Workflow C  ·  Weekly review (15-minute routine)
- Open /overview. Read the AI prose brief, glance at the risk score and watch metrics.
- Open /weekly-plan. Read the AI synthesis card.
- For each P1 action, assign or confirm the owner. The card shows current owner and due-in-days.
- Open /risks. For any new critical risks, click Mitigations.
- Open /agent and ask follow-ups (“show me long-lead items threatening turbine commissioning”) — let the agent pull data across modules.
## Workflow D  ·  What-if a vendor slips
- Open /simulate.
- Pick scenario vendor_slip_2w.
- Pick the target supplier.
- Optionally set custom_slip_days.
- Click Run simulation.
- Read the AI executive narrative card — it explains the impact in plain prose.
- Review the milestone impacts table.
- Review the mitigations.
- If the impact is unacceptable, run alt_vendor for the same target to see the cost of switching.
## Workflow E  ·  Vendor risk review
- Open /vendors.
- Sort by composite score ascending — work the bottom of the list first.
- Click a vendor for the detail page.
- Read the AI risk briefing at the top.
- Read the watchlist.
- Check the alternates — is there a stronger same-category vendor to shift volume to?
- If single-source exposure: run alt_vendor in /simulate to estimate the switching cost.
## Workflow F  ·  Filling sparse BOM data (AI auto-fill)
- Open the BOM tab of a project with rows missing category or supplier.
- Call POST /api/projects/{id}/bom/autofill via curl or any API client.
- Review the suggestions: code, current values, suggested category, suggested supplier, reason.
- To apply, re-upload a CSV with the suggested values + the existing bom_item_ids so rows overwrite in place.
Note: a UI for this is on the roadmap — the API works today.

PART 7
# Configuration & operations
## 7.1  Environment variables
## 7.2  Where state lives
Everything is in-memory. The backend rebuilds its state from app/sample_data.py + fixtures/hydro/ on every boot. After a restart, the project + BOM are restored automatically; the sourcing workflow (PRs, RFQs, awards, POs) needs make seed to re-walk.
## 7.3  Logs and PIDs
- .logs/backend.log — uvicorn (warnings and above).
- .logs/frontend.log — Next.js dev output.
- .logs/seed.log — last sourcing seeder run.
- .pids/backend.pid · .pids/frontend.pid — used by make stop / make status.
## 7.4  Files you might edit

PART 8
# Troubleshooting
Nine of the most common symptoms, and how to resolve each.

PART 9
# Glossary
EPC and supply-chain terms used throughout the manual.


Project Control Tower  ·  User Manual  ·  Release 1.0  ·  May 2026
| Module | What it owns |
| --- | --- |
| Planning | Projects · milestones · BOM · procurement plan · long-lead detection · missing-spec flags |
| Sourcing | Purchase Requisitions → RFQs → Quotes → Awards → Sourcing POs |
| Vendor Intelligence | Multi-dimension scorecards · category concentration · single-source flags · alternates |
| Expediting & Logistics | Slippage prediction · follow-up email drafting · shipment stages · mode recommender |
| Commercial & Risk | Budget vs quoted vs PO · savings / overruns · what-if simulations · AI risk briefings |
| DESIGN PRINCIPLE
Every AI feature has two paths: Grok-generated when XAI_API_KEY is set, deterministic templates otherwise. The app continues to work fully without an API key — Grok adds polish, it isn’t load-bearing. |
| --- |
| Command | What happens |
| --- | --- |
| make install | One-time: creates .venv, installs Python + frontend deps. |
| make demo | Boots backend, seeds project + BOM + vendors, walks 15 BOM items through the full sourcing lifecycle, starts the frontend. |
| Command | Purpose |
| --- | --- |
| make stop | Cleanly kill backend + frontend. |
| make status | Show which services are up + their PIDs. |
| make logs | Tail all log files (Ctrl-C to exit). |
| make seed | Re-run the sourcing seeder against a live backend after a restart. |
| make backend-only | Backend + seed, skip the frontend. |
| make fe-only | Frontend only (assumes backend already up). |
| Group | Pages |
| --- | --- |
| Plan | Projects (Overview · BOM · Procurement Plan) |
| Sourcing | PRs · RFQs · Quotes · POs |
| Monitor | Overview · Risks · Actions |
| Operate | Vendors · Inventory · Expediting · Logistics |
| Intelligence | Agent (chat) · Weekly Plan · Simulate · Commercial · Scenario editor |
| Status | Meaning |
| --- | --- |
| spec_missing | No spec_doc_id linked — engineering hasn’t released the spec yet (red badge). |
| planned | Has spec, not yet requisitioned. |
| requisitioned | PR has been raised against this line. |
| ordered | Award + PO created. |
| delivered | PO received. |
| Urgency | Rule of thumb |
| --- | --- |
| escalate | High slip probability, high value, expedite not possible. |
| nudge | Moderate slip risk; expedite still possible. |
| watch | Minor flags; no action required yet. |
| ok | On track. |
| Type | Trigger |
| --- | --- |
| inventory_gap | Projected 30-day demand exceeds on-hand + open orders. |
| supplier_reliability | Supplier OTD < 92%, or PPM > 1000, or has risk flags, or 0 alternatives. |
| single_source | Sole approved source AND annual spend ≥ $500k. |
| po_slip | PO due ≤ 14d with status planned/released, or currently delayed. |
| incident | Open incident on file — carries severity directly. |
| DIVERSIFICATION
The risk register diversifies by type — the engine takes up to 5 risks per type before topping up to 20. Inventory gaps don’t crowd out supplier or single-source signals. |
| --- |
| Scenario | What it models |
| --- | --- |
| vendor_slip_2w | A named vendor slips by 14 days (configurable). Computes cost delta and milestone movement. |
| customs_hold | A named shipment is held at customs for 14 days. Surfaces downstream impact. |
| alt_vendor | Switch a target item to an alternate vendor. Computes price + lead-time delta. |
| Tool | Purpose |
| --- | --- |
| build_weekly_plan | Returns the full weekly plan. |
| get_top_risks | Risk register. |
| get_expedite_queue | Slipping POs. |
| predict_slip | Slip prediction for one PO. |
| draft_followup_email | Composes a follow-up email. |
| get_vendor_scorecard | One vendor’s full scorecard. |
| list_vendors | All vendors. |
| get_category_concentration | Category-level concentration. |
| get_commercial_summary | Budget vs awarded rollup. |
| get_logistics_queue | Current shipments. |
| recommend_mode | Freight mode recommendation. |
| get_procurement_plan | Project’s procurement plan. |
| list_projects | All projects. |
| get_open_rfqs / get_open_prs | Sourcing items in flight. |
| run_simulation | What-if scenario. |
| Page | Feature |
| --- | --- |
| /overview | Executive prose brief at the top of the page. |
| /agent | Tool-calling chat with markdown + structured table rendering. |
| /risks | “Mitigations” toggle on every row → 3 concrete actions. |
| /risks | “Explain” button on every row → headline + body + bullets. |
| /vendors/[name] | AI risk briefing section above the scorecard. |
| /projects/[id] | “Explain project” button (top right of header). |
| /simulate | 2-paragraph executive narrative below the simulation headline. |
| /weekly-plan | AI synthesis card between the KPI snapshot and items. |
| Sourcing / Award | Grok-generated rationale with cited diffs. |
| Expediting / Email | Grok-drafted email body (tone-aware). |
| Endpoint | Returns |
| --- | --- |
| POST /api/explain | Brief for PO / vendor / risk / project / RFQ / PR. |
| POST /api/risks/mitigations | Three concrete mitigations for one risk. |
| GET /api/vendors/intel/{name}/briefing | Vendor briefing (headline + body + watchlist). |
| POST /api/projects/{id}/bom/autofill | Suggested category + supplier for sparse BOM rows. |
| POST /api/projects/{id}/bom/{id}/spec-request | Email to engineering for a missing-spec BOM item. |
| POST /api/chat | Conversational agent with tool-calling. |
| FAILOVER
Remove XAI_API_KEY (or leave it blank) and every endpoint flips to source: "deterministic". The app continues to work in full — only the prose quality drops. |
| --- |
| Variable | Default | Purpose |
| --- | --- | --- |
| XAI_API_KEY | (unset) | Required to enable Grok. Without it, AI features fall back to deterministic. |
| XAI_MODEL | grok-4-1-fast-reasoning | Override if xAI releases a newer version. |
| XAI_BASE_URL | https://api.x.ai/v1 | xAI API endpoint. |
| XAI_REASONING_EFFORT | (unset) | Set to low or high to override Grok’s default reasoning depth. |
| BACKEND_PORT | 8010 | Backend port. |
| FRONTEND_PORT | 3001 | Frontend port. |
| ALLOWED_ORIGINS | regex localhost | CORS allowlist. |
| File | What’s in it |
| --- | --- |
| app/sample_data.py | Legacy demo scenario (Arcforge etc.). |
| fixtures/hydro/hydro_seed.py | Mahadev Hydro project, BOM, suppliers, inventory, POs, incidents. |
| fixtures/hydro/bom_hydro.csv | The hydro BOM as a CSV — uploadable to other projects. |
| fixtures/seed_sourcing.py | The 14 BOM items walked through the full sourcing lifecycle. |
| Symptom | Likely cause | Fix |
| --- | --- | --- |
| make demo says backend timed out | Port 8010 held by a stale process the cleanup missed. | lsof -ti :8010 | xargs kill -9 ; make demo |
| Frontend says “Failed to bootstrap scenario” | Backend not running or CORS misconfigured. | make status to check; make logs to inspect. |
| Chat always returns source: "deterministic" | .env wasn’t sourced before backend started, or key is invalid. | make stop && make demo; inspect .logs/backend.log for xAI errors. |
| Awards still show the template rationale | Grok call failed silently and fell back. | Verify key with curl -H "Authorization: Bearer $XAI_API_KEY" https://api.x.ai/v1/models |
| BOM upload says CSV must have headers | Required columns missing in row 1. | Column names must match exactly (case-sensitive): code, description, quantity. |
| RFQ says “Comparison needs quotes” | Fewer than 2 quotes received. | Add at least 2 via Add Quote. |
| /sourcing pages empty after restart | In-memory sourcing state lost. | make seed to re-walk the 14 demo items. |
| Risk score 100/100, all inventory_gap | Old build before analyzer diversification cap was raised. | make stop && make demo to pick up latest analyzer. |
| Cannot find module ./NNN.js | Stale .next/ cache from a prior next build mixed with dev mode. | cd frontend && rm -rf .next && cd .. && make stop && make demo |
| Term | Meaning |
| --- | --- |
| BOM | Bill of Materials — the list of items engineering needs procurement to source for a project. Multi-level: assemblies → sub-assemblies → parts. |
| PR | Purchase Requisition — internal authorisation asking procurement to source a specific item. Created from a BOM line. |
| RFQ | Request for Quotation — sent to multiple vendors asking for price + lead time for one or more PR’d items. |
| Quote | A vendor’s response to an RFQ: unit price, lead time, terms, validity. |
| Award | The act of selecting the winning quote. Triggers PO creation. |
| PO | Purchase Order — the formal order to the vendor, derived from the award. |
| OTD % | On-Time Delivery percentage — share of past POs delivered by their committed date. |
| PPM | Parts Per Million — quality defect rate. Lower is better. |
| Composite Score | Weighted blend of a vendor’s 6-dimension performance: delivery, quality, price, responsiveness, claims, risk. Range 0–100. |
| Single-source exposure | Only one approved vendor for a category with significant annual spend. A continuity risk. |
| Long-lead item | A BOM line whose lead time exceeds a threshold (default 90 days for the planner; 365+ days is “critical long-lead”). |
| Missing spec | A BOM line with no spec_doc_id linked. Procurement can’t issue a PR until engineering releases the spec. |
| Milestone | A project schedule anchor with a required-on-site date and phase (engineering / procurement / fabrication / delivery / installation / commissioning). |
| Procurement plan | Auto-generated grouping of BOM items by milestone, with long-lead and missing-spec flags surfaced. |
| Expediting | The practice of actively chasing vendors on in-flight POs to prevent slippage. |
| Slip / Slippage | How much later than committed a PO is expected to arrive. |
| Bottleneck | A logistics stage where a shipment is stuck longer than the baseline (e.g. > 5 days at customs). |
| Incoterm | International commercial term defining who pays for and bears risk over which leg of shipment: EXW · FCA · FOB · CIF · CIP · DAP · DDP. |
| Grade | Letter-grade rollup of composite score: A ≥ 80 · B ≥ 70 · C ≥ 60 · D ≥ 50 · F < 50. |
| EPC | Engineering, Procurement, Construction — the integrated delivery model for large capital projects (power plants, refineries, hydro). |
| ICT | Inter-Connection Transformer — a power transformer connecting two grid voltage levels. |
| LD | Liquidated Damages — contractual penalty for delay, usually a % of contract value per day. |
| FAT | Factory Acceptance Test — tests at the vendor’s factory before dispatch, witnessed by the buyer. |
| RFE | Ready For Erection — milestone meaning all materials for a structure / equipment are on site and erection can begin. |
| Critical path | The chain of activities that, if delayed, delays the whole project. |