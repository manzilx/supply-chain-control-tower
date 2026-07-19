# Hardening loop log

`/loop 15m` — one bounded perf/UX/reliability/stability improvement per cycle, verified locally + deployed.

> ⚠️ **Fly deploy blocked**: `fly auth` token expired (needs interactive `fly auth login`).
> Local changes are built + verified each cycle; they'll batch-deploy once you re-auth.
> Run `fly auth login` in a terminal, then I'll push everything pending.

| Cycle | Area | Change | Local | Fly |
|---|---|---|---|---|
| 1 | Reliability | Cache invalidation moved to mutation **commit-end** via `@invalidates_cache` decorator (was firing at start → stale-read window). Verified: new vendor visible on 15s-cached endpoint immediately after write. | ✅ built + verified | ⏳ pending auth |
| 1 | Stability | Frontend error boundaries — `app/error.tsx` (per-route recovery card) + `app/global-error.tsx` (root shell fallback). A render crash now degrades gracefully instead of white-screening. | ✅ built (tsc + next build clean) | ⏳ pending auth |
| 2 | Performance | Alerts feed cache re-keyed from `(tenant_id, user_id, role)` → `(tenant_id, can_decide)`. The feed depends only on whether the viewer can decide approvals, not identity — so users of the same tenant/role now share one cached fan-out instead of each recomputing every 30s poll. Verified: 2nd decider served in 0.4ms vs 3.2ms cold (~8x), identical content; role-gating + tenant isolation intact. | ✅ built + verified | ⏳ pending auth |
| 3 | UI/UX + stability | Branded `app/not-found.tsx` — unmatched routes & dead entity links now render a styled 404 with quick-links + ⌘K tip instead of Next's bare default. Completes the graceful-states set (route error boundary + global error + 404). Verified: bad route → 404 status + branded body; real routes unaffected. | ✅ built + verified | ⏳ pending auth |
| 4 | UI/UX | Mobile navigation — sidebar was `hidden lg:flex`, leaving the app **unnavigable below 1024px**. Added a hamburger + slide-out drawer (`components/shell/mobile-nav.tsx`, `lg:hidden`) and lifted the nav list to `lib/nav.ts` as a single source of truth for both sidebar + drawer. Verified: component in shipped bundle, shell renders 200, both consumers import `lib/nav`. | ✅ built + verified | ⏳ pending auth |
| 5 | Reliability | Global fetch timeout — base `request()` helper had no timeout, so an unreachable/hung backend = infinite spinner. Added a 45s AbortController ceiling (covers every JSON call; SSE stream untouched) + clean errors for timeout & network failure. Verified: happy path 200s, timeout logic in bundle, normal calls return data. | ✅ built + verified | ⏳ pending auth |

## 10X five-cycle loop (local)

Shipped locally across cycles 1–5:

- **CI** — GitHub Actions workflow for backend + frontend checks
- **JWT prod guard** — `validate_jwt_secret_for_production()` fails fast on default/missing secret when `APP_ENV=prod`
- **Vendor gate** — `POST /api/vendors` routes through `gate_vendor` (buyer → pending, head → auto-apply)
- **Write-through persist** — critical stores (approvals, audit, vendors) flush to `STATE_DIR` on mutation + restore on startup
- **AI propose-vendor** — closed loop: agent tool `propose_vendor_onboarding` + `POST /api/ai/propose-vendor` → approval → head approve → vendor materialises + audit

**Fly redeploy still blocked** on interactive `fly auth login` (token expired). Run `fly auth login`, then batch-deploy pending hardening cycles.

## Tighten loop (Grok plans → Composer executes, 5 iters)

| Iter | Area | Change | Status |
|---|---|---|---|
| 1 | Incomplete wiring | `/pos` now uses `fetchSourcingPos` (live tenant POs) instead of legacy `scenario.purchase_orders`. Loading/error/empty states; RFQ + vendor links; real status filter. | ✅ |
| 2 | Bug (auth) | All 7 TBE routes now require `current_user` + `tenant_id` on `get_rfq`/`get_quotes`. | ✅ |
| 3 | UX / reliability | Notifications error+Retry · `streamChat` 45s first-byte + 401 clear · audit CSV via authed `downloadAuditCsv` | ✅ |
| 4 | Incomplete wiring | Admin tenant `<select>` in top-bar; `sct:tenant-changed` refetches `useAsync` hooks | ✅ |
| 5 | Consistency | Retire legacy M1 nav/chrome (Inventory/Actions/Scenario off nav; tenant-centric top bar; `/scenario` escape hatch) | ✅ |

**Loop complete (5/5).** Leftover backlog: audit tenant isolation · `/risks` still store-backed · nav-hidden `/actions`/`/inventory` routes · ⌘K may still index hidden routes · Fly redeploy still needs `fly auth login`.

## Think-harder loop (dynamic)

Self-paced. Next hard fix first: **audit tenant isolation** (global ring buffer, no `tenant_id`, unauthenticated `/api/audit*`).

| Tick | Focus | Status |
|---|---|---|
| TH-1 | Audit: schema + emit + query + routes + call-site `tenant_id` | ✅ |
| TH-2 | `/risks` → live tenant alerts (replace store-backed register) | ✅ |
| TH-3 | RBAC: enforce `require_perm` on write routes + hide write UI for viewers | ✅ |
| TH-4 | Shortcuts/`?`/⌘K Pages derived from `lib/nav.ts`; overview `/actions` → `/risks` | ✅ |

**Think-harder loop stopped** after 4 hard ticks. Remaining: Fly redeploy (`fly auth login`), optional delete of nav-hidden `/actions`/`/inventory` routes, audit ring-buffer still process-global (reads filtered).

## 10X features loop (dynamic · Grok Advisor → Composer executor)

Focus: multiply usefulness of shipped modules (close action loops), not polish or M8 greenfield.

| Tick | Feature | 10X move | Status |
|---|---|---|---|
| 10X-1 | TBE + Award | Award CTA uses TBE combined rank, not commercial-only #1 | ✅ |
| 10X-2 | Weekly Plan | Items get href + Do-it actions (executable queue) | ✅ |
| 10X-3 | Expediting | Log follow-up sent → audit + slip nudge | ✅ |
| 10X-4 | Logistics | Advance stage UI on shipment cards | ✅ |
| 10X-5 | BOM / Plan | Engineering unblock (autofill + spec request) | ✅ |

**10X features loop complete (5/5).** Grok advised → Composer executed. Theme: close action loops on shipped modules (award, weekly plan, expediting, logistics, BOM). Remaining outside scope: Fly redeploy, bulk PR launcher, approvals payload preview.





## Tighten loop (5 iterations, local)

Grok planned/reviewed → Composer/agent executed. Focus: existing-feature polish (not M8 greenfield).

| Cycle | Tighten | Change |
|---|---|---|
| 1 | Agent tenancy | All agent tools pass `tenant_id` from `get_tool_user()`; weekly_plan scopes projects |
| 2 | Approvals UX | Vendor result links, empty-state/tip copy, approve toast deep-links to vendor |
| 3 | Persist | `flush_critical()` also snaps `sourcing.json` (PR/RFQ/quote/award survive crashes) |
| 4 | Vendor modal | Role-aware copy + “Submit for approval” for buyers |
| 5 | Alerts | Confirmed vendor_onboarding pending appears in head alert feed (test) |
