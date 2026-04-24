# Supply Chain Control Tower — Build Plan

TypeScript + React frontend (Next.js 14 App Router) plus an expanded FastAPI backend, structured to eventually replace a procurement manager for engineering / EPC / industrial projects.

The existing `.start/frontend/` (Next.js 14 + TS) and `.start/app/` (FastAPI risk analyzer) are the starting point, not the finish line. This document maps the full product vision into a pragmatic build order.

---

## 1. Product vision

A five-module, AI-first control tower for project procurement:

| # | Module | Owns |
|---|---|---|
| 1 | **Project Procurement Planner** | BOMs / MTOs / drawings / specs / WBS → procurement packages linked to project milestones; long-lead detection; missing-spec flags |
| 2 | **Vendor & Sourcing Intelligence** | Approved vendor DB, capability tags, multi-dimensional scorecards, single-source / concentration risk, alternate suggestions |
| 3 | **Expediting & Logistics Control Tower** | PR→PO lifecycle, follow-ups (email/portal/WhatsApp), delivery milestone tracking, slippage prediction, freight-mode decisions, bottleneck flags |
| 4 | **Commercial & Risk Manager** | Quoted vs budget vs PO, savings/overruns, LD risk, cash-flow impact, what-if simulations, contract obligations, audit trail |
| 5 | **AI Command Center** | Natural-language control, autonomous sub-agents (sourcing / expediting / vendor-risk / logistics / commercial / reporting), decision recommendations with reasoning, approval thresholds |

**Managerial layer on top** (threaded through every module): priority-setting across projects, buyer workload, escalation filtering, negotiation memory, auto-KPI reviews.

---

## 2. Current state vs target

**Backend today** (`.start/app/`): risk analysis only.
- `GET /api/demo`, `POST /api/analyze` + OpenAI brief
- Models: `CompanyProfile`, `SupplierRecord`, `InventoryItem`, `PurchaseOrder`, `DemandSignal`, `Incident`, `RiskRecord`, `RecommendedAction`, `WatchMetric`

**Frontend today** (`.start/frontend/`): single-page scenario editor.
- JSON textareas → `/api/analyze` → summary cards. No nav, no drill-downs, no chat.

**Gap for target product**
- Data model: missing `Project`, `Milestone`, `BOMItem`, `PurchaseRequisition`, `RFQ`, `Quote`, `Award`, `Contract`, `ShipmentEvent`, `Document`, `Action`, `Approval`, `VendorScorecard`, `AuditEvent`, `ChatTurn`
- Endpoints: missing everything beyond `/analyze`
- Intelligence: risk engine is deterministic & shallow; no simulations, no expediting, no sourcing, no commercial
- Integrations: none. ERP / P6 / PLM / email / portals / freight all absent
- Governance: no auth, roles, audit log, approvals, policy rules
- UI: no shell, one route, no tables/filters/charts/chat

---

## 3. MVP scope (your call)

Per your own MVP cut — the minimum that demonstrates the product shape end-to-end:

1. **Project material planning** — upload a BOM (CSV), attach it to a project with milestones, auto-build a procurement plan with long-lead flags and missing-spec warnings.
2. **Vendor scorecards** — multi-component score (OTD, quality, price, responsiveness, claims, risk), concentration/single-source detection, alternate suggestions.
3. **PO tracker** — PR → RFQ → Quote → Award → PO → Delivery, each item visible from requisition to receipt.
4. **Expediting assistant** — auto-detect slippage, draft follow-up emails, escalate by criticality.
5. **Risk dashboard** — rolled up from all of the above, with what-if simulations on 2–3 dimensions (vendor slip, customs hold, alternate vendor).
6. **AI-generated weekly action plan** — natural-language agent over the whole dataset that outputs a prioritized action list with reasoning.

Explicitly **out of MVP**: real ERP/P6/PLM connectors, WhatsApp/Teams delivery, role-based auth, approval workflows, contract parsing, multi-tenancy, autonomous agent orchestration beyond one main agent with tool-calls. These come after the product shape is validated.

---

## 4. Architecture

### 4.1 Backend (`.start/app/`)

Keep FastAPI. Promote the current single-file layout into packages so the five modules map cleanly:

```
app/
  main.py                    ← FastAPI app, router mount, CORS
  core/
    config.py, db.py, auth.py (stub), audit.py
  schemas/
    project.py, bom.py, vendor.py, sourcing.py, po.py,
    expediting.py, logistics.py, commercial.py, risk.py,
    chat.py, common.py
  modules/
    planning/   ← BOM parse, procurement-plan builder, long-lead detection
    vendors/    ← scorecard engine, alternates, concentration
    sourcing/   ← PR→RFQ→Quote→Award→PO lifecycle
    expediting/ ← slippage detection, follow-up drafting, escalation
    logistics/  ← shipment events, mode decisions, bottleneck flags
    commercial/ ← budget vs quoted vs PO, savings, LD risk
    risk/       ← unified risk engine + what-if simulator
    agent/      ← chat loop, tool-call registry, sub-agent dispatch
  integrations/
    erp_stub.py, p6_stub.py, email_stub.py   ← adapter interfaces only in MVP
  storage/
    memory_store.py    ← in-memory/JSON-file persistence for MVP
                         (SQLite/Postgres slot-in later)
```

**Persistence** — in-memory + JSON file snapshot for MVP. Every module writes through `storage/` so swapping to SQLAlchemy + Postgres is a one-module change. Do **not** spend MVP cycles on schema migrations.

**LLM usage** — wrap all model calls in `modules/agent/llm.py`. Default provider: Claude (Anthropic SDK) with prompt caching on the system prompt + vendor/project context. Keep the OpenAI fallback that exists today. Tool-calling is how the agent reads data (`get_vendors`, `list_open_pos`, `simulate_risk`, etc.) rather than stuffing everything into the prompt.

### 4.2 Frontend (`.start/frontend/`)

Next.js 14 App Router with nested routes per module. One client-side `StoreProvider` context holding the full dataset (vendors, projects, POs, risks, etc.); TanStack Query for server fetches and cache invalidation once the data set exceeds a few hundred rows.

Styling: **Tailwind CSS** + a handful of custom components. Tables are the primary UI — hand-rolled CSS won't keep up. No UI kit yet; add shadcn/ui if we hit a wall on dialogs/popovers.

Charts: **Recharts** (risk gauge, supply-vs-demand, scorecard radar, PR-to-PO cycle time, vendor OTD trend).

### 4.3 App shell

```
┌────────────────┬───────────────────────────────────────────┐
│ Projects ▾     │ Top bar: active project • scenario •      │
│   Overview     │ connection • user • approvals queue       │
│   BOM / Plan   ├───────────────────────────────────────────┤
│                │                                           │
│ Sourcing       │                                           │
│   PRs          │           Active view                     │
│   RFQs         │                                           │
│   Quotes       │                                           │
│   POs          │                                           │
│                │                                           │
│ Vendors        │                                           │
│ Expediting     │                                           │
│ Logistics      │                                           │
│ Inventory      │                                           │
│ Commercial     │                                           │
│ Risk           │                                           │
│ Actions        │                                           │
│ Agent          │                                           │
│ Contracts      │                                           │
│ Audit          │                                           │
│ Settings       │                                           │
└────────────────┴───────────────────────────────────────────┘
```

---

## 5. Data model additions (MVP slice)

New Pydantic schemas — additive to what `schemas.py` already has:

```python
Project           project_id, name, client, site, start, milestones[]
Milestone         code, name, required_on_site_date, phase
BOMItem           project_id, parent_item_id, level, code, description,
                  quantity, uom, spec_doc_id?, drawing_id?, long_lead_days?,
                  planned_need_date, status  # spec_missing | planned | requisitioned | ordered | delivered
Document          doc_id, kind (drawing|spec|GA|QAP|ITP|MDR|test_cert|MOM),
                  title, url, version, uploaded_at
PurchaseRequisition  pr_no, project_id, bom_item_id, qty, need_by, buyer, status
RFQ               rfq_no, pr_no, vendors[], issued_at, due_at, status
Quote             rfq_no, vendor, line_items[], total, lead_time_days,
                  incoterm, validity, attachments[]
Award             rfq_no, vendor, rationale, approved_by?
PurchaseOrder+    (extend current) pr_no, project_id, award_id,
                  budget_value, quoted_value, variation_orders[],
                  incoterm, payment_terms
ShipmentEvent     po_no, kind (manufacturing|dispatch|transit|customs|site),
                  at, location, note
VendorScorecard   vendor, window, otd_pct, quality_ppm, price_index,
                  responsiveness, claims_count, risk_flags[], composite_score
Contract          contract_id, vendor, scope, obligations[],
                  incoterm, ld_clause, warranty, inspection_clause
Action            id, title, priority P1|P2|P3, owner, due_in_days,
                  origin (module), confidence, rationale, status
Approval          action_id, threshold_rule, required_role, status, decided_by
ChatTurn          turn_id, role, content, tool_calls[], created_at
AuditEvent        actor, action, target, before, after, at
```

Most MVP endpoints return these read-only; a handful mutate (PR create, quote upload, award, action complete, chat message).

---

## 6. Endpoint surface (MVP)

Read:
```
GET  /api/projects                         list
GET  /api/projects/{id}                    detail w/ milestones
GET  /api/projects/{id}/bom                BOM tree
GET  /api/projects/{id}/procurement-plan   plan with long-lead & gaps
GET  /api/vendors                          list w/ composite score
GET  /api/vendors/{name}                   detail + scorecard components
GET  /api/vendors/{name}/alternates        by category
GET  /api/prs   /api/rfqs   /api/quotes   /api/pos
GET  /api/pos/{no}/timeline                PR→RFQ→Quote→Award→PO→Shipment
GET  /api/expediting/queue                 at-risk items w/ predicted slip
GET  /api/logistics/shipments              open shipments
GET  /api/inventory                        (existing, extended)
GET  /api/commercial/summary               budget vs quoted vs PO, savings
GET  /api/risk/overview                    rolls up all modules
GET  /api/actions                          prioritized action list
GET  /api/contracts                        with obligations
GET  /api/audit                            event log
```

Write:
```
POST /api/projects/{id}/bom/upload         CSV → BOMItem[]
POST /api/prs                              create PR from BOM line
POST /api/rfqs                             create RFQ from PR(s)
POST /api/quotes                           upload/attach quote
POST /api/rfqs/{no}/award                  pick vendor + rationale
POST /api/pos                              create PO from award
POST /api/expediting/{po}/followup        draft + (stub) send email
POST /api/actions/{id}/complete
POST /api/risk/simulate                    { scenario: "vendor_slip_2w" | "customs_hold" | "alt_vendor", target }
POST /api/chat                             { message, history, project_id? } → reply + tool_calls_used
```

All write endpoints emit an `AuditEvent`.

---

## 7. Agent design

One primary agent (`AI Command Center`) with five virtual sub-agents as **prompt personas + tool sets**, not separate services. Keeps MVP tractable.

| Sub-agent | Tools it can call |
|---|---|
| Sourcing | `get_prs`, `get_vendors`, `get_alternates`, `draft_rfq`, `compare_quotes`, `recommend_award` |
| Expediting | `get_open_pos`, `predict_slip`, `draft_followup_email`, `escalate` |
| Vendor-risk | `get_vendor_scorecard`, `get_concentration`, `flag_single_source` |
| Logistics | `get_shipments`, `recommend_mode`, `flag_bottleneck` |
| Commercial | `get_budget_vs_actual`, `get_savings`, `get_cashflow_impact` |
| Reporting | `build_weekly_plan`, `draft_escalation_email`, `summarize_mom` |

The main agent routes user requests to the right sub-persona with its tool allowlist. Every recommendation returned includes: `why`, `expected_impact`, `confidence`, `supporting_data_refs[]` — enforced as a Pydantic return schema so the UI can render it consistently.

**Approval thresholds** (post-MVP): action metadata carries `auto_execute: bool` derived from a policy table (e.g., value < $5k AND vendor is approved AND not sole-source → auto). Anything else queues an `Approval` record.

---

## 8. Integrations — seams now, wiring later

MVP ships with **adapter stubs** that return deterministic demo data. Real wiring is a milestone per system.

```
integrations/
  erp/        sap_stub.py oracle_stub.py       ← returns mocked POs/GRNs/invoices
  planning/   p6_stub.py msproject_stub.py     ← milestones, required-on-site dates
  engineering/ plm_stub.py dms_stub.py         ← BOMs, drawings, specs
  comms/      email_stub.py whatsapp_stub.py   ← send + receive callbacks
  logistics/  freight_stub.py                  ← shipment events
  finance/    ap_stub.py                       ← invoice status, payment delays
```

Each stub implements the same interface real adapters will. MVP demo uses stubs; swapping in real systems doesn't touch any module code.

---

## 9. Milestones

Each milestone is independently shippable.

### M1 — Control Tower shell + risk dashboard (existing data)
- Tailwind, app-router shell, sidebar, top bar, `StoreProvider`
- Routes: Overview, Risks, Vendors, Inventory, POs, Actions, Agent, Scenario
- Reuses current `/api/analyze`; no new backend
- **Exit:** navigable control tower over today's demo data

### M2 — Projects, BOM, Procurement Plan
- Backend: `Project`, `Milestone`, `BOMItem`, `Document` schemas; `/api/projects*`, BOM CSV upload, procurement-plan builder (long-lead + missing-spec detection)
- Frontend: `/projects`, `/projects/[id]`, `/projects/[id]/bom`, `/projects/[id]/plan`
- Sample BOM CSV + 2 demo projects in `sample_data.py`
- **Exit:** upload a BOM, see a project's procurement plan with long-lead flags

### M3 — Sourcing: PR → RFQ → Quote → Award → PO
- Backend: PR/RFQ/Quote/Award endpoints, quote-compare helper, award rationale generator
- Frontend: Sourcing workbench (`/sourcing/*`), PO detail timeline
- Agent tools: `draft_rfq`, `compare_quotes`, `recommend_award`
- **Exit:** create a PR from a BOM line, issue RFQ to multiple vendors, compare quotes, award, PO draft appears

### M4 — Vendor Intelligence + Expediting
- Backend: scorecard engine (OTD/PPM/price/response/claims/risk), alternates, concentration; slippage predictor; follow-up email drafter
- Frontend: Vendor detail drawer with radar chart; Expediting queue; email draft modal
- Agent tools: `get_vendor_scorecard`, `get_alternates`, `predict_slip`, `draft_followup_email`
- **Exit:** vendor scorecards live, expediting queue shows predicted slips with drafted emails

### M5 — Logistics + Commercial + Risk simulations
- Backend: shipment events, mode recommender, budget-vs-actual, savings, 3 what-if simulators (vendor slip 2w, customs hold, alternate vendor)
- Frontend: Logistics tracker, Commercial summary, Risk `/simulate` form
- **Exit:** end-to-end visibility from PO to site receipt, run a what-if, see impact on project dates + cost

### M6 — AI Command Center (weekly plan + chat with reasoning)
- Backend: `/api/chat` with tool-calling to all modules; `build_weekly_plan` tool
- Frontend: `/agent` chat view with streaming; every recommendation card renders `why/impact/confidence/data`
- **Exit:** user asks "show long-lead items threatening turbine commissioning" or "draft escalation emails for red items" and gets a correct, sourced answer + auto-weekly-plan

### M7+ — Post-MVP (flagged, not scheduled)
Contract parsing · real ERP/P6/PLM connectors · WhatsApp/Teams outbound · role-based auth · approval workflows · multi-project priority balancer · negotiation memory store · autonomous scheduled sub-agents · multi-tenant

---

## 10. Tradeoffs / calls worth flagging

| Choice | Why |
|---|---|
| Monorepo, keep `.start/` layout | Already set up; no reason to reshape |
| JSON-file persistence for MVP | Zero ops; swap to Postgres at M5 or when multi-user |
| Claude-first LLM with OpenAI fallback | Better tool-calling + prompt caching; existing OpenAI path stays |
| Sub-agents as personas, not processes | Real multi-agent orchestration is a separate project |
| Tailwind, no component library | Table-heavy UI; shadcn/ui added only if dialogs/popovers block us |
| Adapter stubs for all external systems | Lets us demo the product shape without vendor procurement blocking |
| Audit log from day one | Cheap to add early, painful to retrofit; governance depends on it |
| Defer auth/roles to post-MVP | Single-tenant demo; adding NextAuth + RBAC is a week on its own |
| No real WhatsApp/email send in MVP | Provider accounts + deliverability are their own project |

---

## 11. Open questions

1. **Deployment target** — local dev only for now, or should M1 include a Vercel/Render deployment pipeline?
2. **LLM provider** — confirm Claude (Anthropic) as primary with OpenAI fallback? Or stay OpenAI-first?
3. **First integration to actually wire** — which external system matters most for *your* first real demo: SAP, P6, or email? (Drives post-MVP priority.)
4. **Persona bias** — if you had to pick one user to delight in MVP: project buyer, expeditor, or procurement head? Affects which screens get the polish budget.
5. **Data we can use** — any anonymized real BOM / PO / vendor data available, or stay on synthetic demo through MVP?
6. **Milestone appetite** — ship M1 and review, or M1→M4 before a check-in?

Answer these and M1 can start immediately.
