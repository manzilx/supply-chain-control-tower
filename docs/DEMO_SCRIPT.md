# Demo script

A ~12-minute walkthrough of the Control Tower. Every `make demo` boot resets to
the same seeded state, so the steps below land on the same data each time.

## Before you present

```bash
make stop && make demo        # clean slate; ~1 min
make status                   # both services "up"
```

- Open <http://127.0.0.1:3001> and sign in as **Northwind Procurement Head** —
  Northwind has the richest data (4 projects, 89 BOM lines, 8 sourced POs).
- Click through once before the audience joins. The first visit to each page
  compiles it under `next dev`; after that pages load instantly.
- **AI**: with `DEEPSEEK_API_KEY` in `.env`, briefs and chat are LLM-written.
  Without it every AI surface still works on deterministic templates (labelled
  `DETERMINISTIC`) — safe for offline demos.
- If anything gets messy mid-demo, `make demo` again resets everything.

## The flow

### 1. Overview — "one screen for the whole portfolio" (2 min)
`/overview`
- Portfolio ring, budget vs committed vs awarded, projects by phase.
- Scroll: overall risk gauge, top risks (single-source exposure on Andritz
  Hydro, the spiral case held at JNPT customs), ranked actions, AI brief.
- Bottom: **This Week** — the auto-generated weekly plan with "Open BOM"
  buttons that jump straight to the blocker.
- Mention **⌘K** — jump to any project, BOM line, vendor, PR or PO.

### 2. Projects → BOM → procurement plan (1.5 min)
`/projects` → **Mahadev Hydro 220 MW**
- 12 milestones; **BOM** tab: 70 lines tied to milestones, long-lead flags.
- **Procurement Plan** tab: what must be ordered by when to hit each milestone.
- **Process** tab: SCM process map + risk register for the project.

### 3. Sourcing — PR → RFQ → quotes → award → PO (2 min)
`/sourcing` → open **RFQ-00015** (130 MVA generator transformer)
- Three quotes side by side; engine ranks on price + lead time + reliability.
- Award rationale is recorded; the PO is generated automatically.
- Point out awards that overrode the engine pick (e.g. RFQ-00014, GIS bay to
  Hitachi Energy over Siemens Energy) — the override note is kept in the award
  rationale.

### 4. Commercial — savings and overruns (1 min)
`/commercial`
- $466K saved against budget, but net **+0.2% over**: the rebar line came in
  8% over estimate (steel price move) and the generator transformer 3% over.
  Overruns are flagged before they hit the bottom line.

### 5. Expediting + logistics — "what's going to slip" (2 min)
`/expediting`
- Queue ranked by predicted slip probability; escalate / nudge / watch.
- **Draft Email** on an escalated PO → tone-aware vendor follow-up; then
  **Mark follow-up sent** to log it.
- `/logistics`: shipments in flight; **Advance shipment** moves one a stage live.

### 6. What-if simulator (1.5 min)
`/simulate`
- Type: **Andritz Hydro slips 30 days** → 4 orders slide, value at risk,
  cost delta, affected milestones, mitigations, one-click follow-up.
- Or click a suggested card (customs hold, milestone move).

### 7. AI Command Center (1.5 min)
`/agent` (or the **Copilot** button on any page)
- Ask: *"Which POs are most likely to slip and what should I do?"*
- The agent calls tools (expedite queue, vendor intel, commercial) and shows
  every call it made beneath the answer.

### 8. Governance — approvals and audit (1 min)
`/approvals`
- A buyer has proposed **GE Vernova Hydro** as an alternate source for the
  single-source Andritz exposure. Buyers can't onboard vendors on their own —
  approve it here and it appears in `/vendors` with a scorecard.
- `/audit`: every PR, quote, award and approval with who / when.
- Optional: sign out and sign in as **Northwind Senior Buyer** or **Viewer** to
  show role-based access (viewers see no write buttons).

## Other tenants

Each tenant sees only its own data. **Helios Offshore** (offshore wind,
FPSO, subsea) has $47.6M awarded with a gas-compressor overrun and its own
pending approval (Oceaneering Connectors). **Arcforge Engineering** covers
thermal and substation projects.
