# Supply Chain Control Tower — Build Status & Plan

AI-assisted procurement cockpit for engineering / EPC / industrial projects.
Next.js 14 (App Router, TypeScript) frontend + FastAPI backend, multi-tenant, deployed on Fly.io.

- **Live:** https://scm-towerx.fly.dev/  ·  **Local:** `docker compose --env-file .env.production up -d` → https://localhost/
- **Stack:** FastAPI · Pydantic · in-memory stores + JSON snapshot persistence · Next.js 14 · Tailwind · framer-motion · Recharts · Grok 4.1 (xAI) with deterministic fallback · SAP CPI (mock) · Caddy / nginx reverse proxy · single uvicorn worker.

---

## 1. Status at a glance

| Milestone | Scope | Status |
|---|---|---|
| **M1** | Shell + risk dashboard | ✅ shipped |
| **M2** | Projects + BOM + procurement plan | ✅ shipped |
| **M3** | Sourcing: PR → RFQ → Quote → Award → PO | ✅ shipped |
| **M4** | Vendor intelligence + expediting | ✅ shipped |
| **M5** | Logistics + commercial + simulations | ✅ shipped |
| **M6** | AI command center (chat + tool calling, weekly plan) | ✅ shipped |
| **M7.1** | Auth + tenants (persona login, JWT) | ✅ shipped |
| **M7.2** | Tenant-scoped stores + route protection (RBAC) | ✅ shipped |
| **M7.3** | Approvals workflow (gated high-risk writes) | ✅ shipped |
| **Post-M7** | Portfolio cockpit · command palette · ingestion engine · streaming AI · performance + reliability hardening | ✅ shipped (5 hardening cycles ⏳ pending Fly redeploy) |

---

## 2. Multi-tenant + RBAC model

Three seeded tenants, five roles, fifteen personas (persona-picker login, no passwords — JWT, 8h TTL).

| Tenant | Sector | Anchor projects |
|---|---|---|
| **arcforge** | Power Systems EPC | Riverbank 2×660 MW · Tanjore CCGT · Sundarpur 765 kV · Meridian CCGT (in-flight) |
| **helios** | Offshore Engineering | North Sea Substation · Dogger Bank Wind · Hawthorn FPSO · Valhall Tie-In (in-flight) |
| **northwind** | Heavy Engineering | Mahadev Hydro 220 MW (70-line BOM) · Polaris Steel Mill · Granite Ridge Cement · Kavi Hydro (in-flight) |

| Role | Capabilities |
|---|---|
| admin | everything + cross-tenant switch |
| procurement_head | read all · PR/RFQ/award/PO · **approval:decide** |
| buyer | read all · create PR/RFQ/quote/award (gated above thresholds) |
| expeditor | read all · follow-ups · shipment events |
| viewer | read-only |

Every domain object carries `tenant_id`; cross-tenant reads return 404; cross-tenant writes are rejected. Verified end-to-end.

---

## 3. Module inventory (what's built)

**Plan** — Projects, milestones, BOM (status: spec_missing/planned/requisitioned/ordered/delivered), procurement plan (long-lead + missing-spec flags), **blended completion %** (40% milestones · 40% BOM delivered · 20% spend committed), in-flight projects seeded at ~55%.

**Ingest** — Universal Excel/CSV import engine: multi-sheet classification (projects/BOM/suppliers), fuzzy column mapping + one AI-assist pass, row-by-row validation, preview→commit staging, tenant-safe.

**Sourcing** — Full PR → RFQ → Quote → Award → PO lifecycle, quote comparison, technical bid evaluation (TBE), auto-drafted PO + AI award rationale.

**Approvals (M7.3)** — Governance gate on high-risk writes: PO ≥ $50k, single-source/override award, quote > budget×1.10. Buyer's gated action → pending approval; head/admin self-approves (auto-approved, audited). Committers replay the frozen payload on approval.

**Vendors** — 6-axis scorecards (delivery/quality/price/responsiveness/claims/risk), category concentration, alternates, single-source exposure, runtime "add vendor" with live composite, AI risk briefings.

**Expediting** — Slip-probability queue, urgency tiers, AI follow-up emails (tone-aware).

**Logistics** — Shipment tracking by stage, bottleneck flags, freight-mode recommender.

**Commercial** — Budget vs quoted vs awarded roll-up, savings/overruns, per-project.

**Monitor** — Portfolio cockpit (`/overview`): completion donut, spend rollup, schedule risk, live activity. **Alerts feed** (bell + drawer) across approvals/schedule/vendor/commercial/expediting/engineering. Weekly plan, risks, actions, full audit trail with entity tracing + CSV export.

**Intelligence** — AI Copilot (⌘J slide-out, page-aware, **SSE streaming with live tool status**), agent chat with tool calling, what-if simulations, `/api/ai/status` health.

**Cross-cutting UX** — Command palette (⌘K fuzzy search over all entities), toast system, keyboard nav (g-then-key + `?` help), skeleton loaders, hover-prefetch, graceful error/404 states, mobile navigation drawer.

---

## 4. Performance & reliability hardening (recent)

| # | Area | Change |
|---|---|---|
| — | Performance | Memoized per-tenant demo scenario · TTL-cached analytics (expedite/shipments/commercial/vendors/search/weekly-plan/explain) · orjson responses · gzip at proxy · `X-Process-Time-Ms` header |
| 1 | Reliability | Cache invalidation moved to mutation **commit-end** (`@invalidates_cache`) — closes the stale-read window |
| 1 | Stability | Frontend error boundaries (route + global) — no white-screen on render crash |
| 2 | Performance | Alerts feed cache re-keyed `(tenant, can_decide)` — same-tenant deciders share one fan-out (~8x) |
| 3 | UI/UX | Branded 404 (`not-found.tsx`) |
| 4 | UI/UX | Mobile navigation drawer (app was unnavigable < 1024px) + shared `lib/nav` source of truth |
| 5 | Reliability | 45s `AbortController` timeout on every JSON call — hang → clean error, not infinite spinner |

> ⏳ Cycles 1–5 are built + verified on local Docker; **pending one `fly auth login` to batch-deploy** to scm-towerx.fly.dev.

---

## 5. Deployment

- **Path A — Docker Compose on a VM (recommended):** Caddy auto-TLS, state volume, `docker compose --env-file .env.production up -d --build`.
- **Path B — Fly.io single container (current live):** `Dockerfile.combined` + supervisord (uvicorn + next + nginx), `state` volume at `/data`, `fly deploy`.
- **Persistence:** in-memory stores snapshot to JSON every 120s (`projects/sourcing/tbe/logistics/audit/sap_cpi/vendors/approvals.json`) and restore on boot. Survives restarts.
- **Process model:** `UVICORN_WORKERS=1` (mandatory — state is process-local; comments in 5 config files guard against scaling).
- **Secrets:** `JWT_SECRET` (mandatory in prod), `XAI_API_KEY` (enables Grok; deterministic fallback otherwise), SAP CPI vars.

---

## 6. Next / known gaps

- **Deploy the 5 pending hardening cycles** once Fly auth is restored (`fly auth login`).
- **Vendor onboarding** is wired: `gate_vendor` on `POST /api/vendors`, AI tool `propose_vendor_onboarding`, and `POST /api/ai/propose-vendor` (buyer propose → head approve → vendor + audit).
- **Write-through** flushes critical stores (approvals, audit, vendors, sourcing) on mutation; `restore_all()` on startup.
- **Agent tools** are tenant-scoped via the chat request user (`get_tool_user()`).
- Move cache invalidation to commit-end with try/finally already done (cycle 1); consider a shared store (Redis/SQLite) before scaling beyond one worker.
- M8 candidates: ERP/P6 connectors, contract parsing, WhatsApp outbound, real auth (SSO), approval chains, per-row ACLs, encryption at rest.

---

_Test pack: `test-data/` (workbook + uploadable CSVs + TEST_PLAN.md). Live data export: `test-data/control-tower-synthetic-data.xlsx`. Hardening detail: `HARDENING_LOG.md`._
