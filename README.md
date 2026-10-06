# Supply Chain Control Tower

AI-assisted control tower for engineering / EPC procurement. FastAPI backend (`app/`) + Next.js 14 frontend (`frontend/`).

## Quick start

```bash
make install   # one-time: .venv + frontend deps
make demo      # boot everything (clean → backend → seed → frontend)
```

Then open [http://127.0.0.1:3001](http://127.0.0.1:3001).

**For day-to-day users**: read [`docs/USER_MANUAL.md`](docs/USER_MANUAL.md) — covers every page, every feature, common workflows, and a glossary of EPC/procurement terms.

```
backend  http://127.0.0.1:8010/api/health
frontend http://127.0.0.1:3001/
```

## All targets

| Command | Does |
|---|---|
| `make demo` | Full boot: kill stale procs → reset `.data/` → start backend with hydro fixture → seed PR→RFQ→Quote→Award→PO → start frontend |
| `make backend-only` | Backend + seed, skip frontend (`./scripts/demo.sh --no-fe`) |
| `make fe-only` | Frontend dev server only (assumes backend already up) |
| `make seed` | Re-run the sourcing workflow seeder against a live backend (adds a second copy — `make demo` for a clean slate) |
| `make stop` | Kill backend + frontend cleanly |
| `make status` | Show which services are up + their PIDs |
| `make logs` | Tail all three log files (Ctrl-C to exit) |

Lower-level: `./scripts/demo.sh [stop|status|logs|seed|--no-seed|--no-fe|--keep-state]`.

Logs land in `.logs/` and PIDs in `.pids/` (both gitignored).

## What gets seeded

`make demo` resets `.data/` and lands the app in the same fully-populated state on every boot (use `./scripts/demo.sh --keep-state` to resume the last snapshot instead). Three tenants, four projects each — pick any persona on `/login`, no password:

| Tenant | Projects | BOM lines | Sourced POs | Awarded | Savings |
|---|---|---|---|---|---|
| **Northwind Heavy Engineering** (richest — start here) | Mahadev Hydro 220 MW, Polaris Steel Mill, Granite Ridge Cement, Kavi Hydro overhaul | 89 | 8 | $18.4 M | $466 K (rebar + transformer overruns flagged) |
| **Helios Offshore** | North Sea Offshore Substation, Dogger Bank Wind 480 MW, Hawthorn FPSO, Valhall Bravo tie-in | 23 | 6 | $47.6 M | $1.1 M (compressor + J-tube overruns flagged) |
| **Arcforge Engineering** | Riverbank 2×660 MW, Tanjore CCGT, Sundarpur 765 kV, Meridian CCGT | 27 | 7 | $4.3 M | $140 K |

Every tenant also gets ~38 scored vendors, a 23–25 line expediting queue, 7–8 live risk alerts, shipments in flight on `/logistics`, and the full PR → RFQ → 3 quotes → Award → PO trail on `/sourcing`.

Walkthrough for presenters: [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md).

## Signing in

`make demo` sets `DEMO_LOGIN=1`, which keeps the passwordless persona picker above. **Any other deployment requires passwords** — leave `DEMO_LOGIN` unset and:

1. Set `JWT_SECRET` (`openssl rand -hex 32`). The backend refuses to start without it when passwords are on.
2. Give each person a password from a shell on the server (min 12 chars; stored hashed in `STATE_DIR/credentials.json`, mode 0600):
   ```bash
   python -m app.credentials northwind-head-01
   ```
3. They sign in on `/login` with their email (or user ID) and password. Five wrong passwords lock that login for 5 minutes.

Switching between tenants is limited to user IDs listed in `PLATFORM_ADMINS` (comma-separated); a tenant's own admin stays in their tenant. In demo mode every admin can still switch.

## AI

Every AI feature routes through **DeepSeek** (`deepseek-v4-flash`) when `DEEPSEEK_API_KEY` is set. If the key is missing or a call fails, the app uses deterministic templates. Each response carries `source: "deepseek" | "deterministic"`.

**Activate:**

In the running app: sign in as an **admin** persona → **SAP / Integrations** → paste `DEEPSEEK_API_KEY` → Save key. The key is stored under `STATE_DIR` (gitignored) and is never returned by the API. It overrides any `.env` key, survives `make demo`'s state reset, and is one key for the whole server — every tenant's admin can see the hint and replace or clear it.

Or via env (still supported):

```bash
cp .env.example .env
# edit .env, set DEEPSEEK_API_KEY=sk-...
make stop && make demo    # scripts/demo.sh auto-sources .env before starting
```

`.env` is gitignored. The orchestrator (`scripts/demo.sh`) auto-loads it before launching the backend + frontend, so child processes pick up every variable.

**Check it's live:** ask the `/agent` page anything, then:

```bash
TOKEN=$(curl -s -X POST localhost:8010/api/auth/login -H 'content-type: application/json' \
  -d '{"user_id":"northwind-head-01"}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')
curl -s localhost:8010/api/ai/status -H "Authorization: Bearer $TOKEN"
```

`"enabled": true` with `stats.calls` rising and `stats.errors` at 0 means DeepSeek is answering. AI panels also label their source (`DEEPSEEK` vs `DETERMINISTIC`). A bad key or unreachable API shows up as `stats.errors` climbing while every surface quietly keeps working on templates.

Model replies are treated as untrusted: a reply with the wrong shape (off-list enum, list where text was expected, non-JSON) falls back to the deterministic answer for that panel instead of erroring.

**What turns on with the key:**

| Surface | What the LLM generates |
|---|---|
| `/agent` chat | Tool-calling responses (`source: "deepseek"`), including pending approvals and GRN queue |
| `/overview` | Executive prose brief |
| `/risks` | Per-risk mitigations (Mitigations button), per-risk Explain brief |
| `/simulate` | 2-paragraph executive narrative on every simulation result |
| `/weekly-plan` | Synthesized narrative over the rule-based plan (now includes approval + GRN P1s) |
| `/vendors/[name]` | AI risk briefing with headline · body · watchlist |
| `/projects/[id]` | Project Explain brief |
| `/store/grn-triage` | Explain this GRN (never auto-matches or posts stock) |
| Award rationale | Cited rationale on every PO awarded via the sourcing flow |
| Follow-up emails | Tone-aware PO-specific email body |
| BOM auto-fill (POST + UI) | Category + supplier suggestions for sparse rows |
| Spec request (POST) | Email to engineering for missing-spec BOM items |
| `<ExplainButton />` | "What should I know about this" brief for PO/vendor/risk/project/RFQ/PR/GRN |

Configurable env vars (all live in `.env`):

| Var | Default | Purpose |
|---|---|---|
| `DEEPSEEK_API_KEY` | _(required to enable AI)_ | DeepSeek API key |
| `DEEPSEEK_MODEL` | `deepseek-v4-flash` | Model ID (`deepseek-v4-pro` for heavier jobs) |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | API base |


## Deployment

Three paths, all from the same codebase. Pick one.

### Path A — Docker Compose on a VM (recommended for self-hosting)

Universal. Works on any cloud VM (AWS EC2, Hetzner, DigitalOcean, your laptop). Caddy auto-issues Let's Encrypt TLS. State persists across restarts in a Docker volume.

```bash
# One-time
cp .env.production.example .env.production
# edit .env.production — set HOSTNAME (or `localhost` for testing),
# JWT_SECRET (mandatory — `openssl rand -hex 32`), DEEPSEEK_API_KEY, ALLOWED_ORIGINS, etc.

docker compose --env-file .env.production up -d --build
```

That's it. Caddy listens on 80/443, proxies `/api/*` and `/healthz` to the backend container, everything else to the frontend container. Both services run as non-root, restart on failure, and snapshot their state to the `state` volume every 120 s.

To inspect:

```bash
docker compose ps                    # service status
docker compose logs -f backend       # tail logs
curl https://yourdomain.com/healthz  # liveness probe
```

### Path B — Fly.io single-container (cheapest cloud path)

One VM hosts backend + frontend + nginx via `supervisord`. Free-tier eligible: 256-512 MB RAM, 1 GB volume, Let's Encrypt managed by Fly.

```bash
# One-time
fly auth login
fly launch --no-deploy --copy-config --name <your-app>
fly volumes create state -r <region> -s 1
fly secrets set DEEPSEEK_API_KEY=sk-... ALLOWED_ORIGIN_REGEX='https://your-app\.fly\.dev'

fly deploy
```

Edit `fly.toml` to change region, VM size, or auto-stop behaviour. The combined Dockerfile (`Dockerfile.combined`) is what Fly builds.

### Path C — Plain `make demo` (local dev only)

Already documented above. Don't expose this to the internet — no TLS, no CORS hardening, `next dev` instead of `next start`.

---

## Production hardening notes

| Concern | How it's handled |
|---|---|
| **State persistence** | Every in-memory store snapshots to JSON every 120 s (configurable via `SNAPSHOT_INTERVAL_SECONDS`); approvals, audit, vendors and sourcing also write through on every change. Writes are atomic. On boot the latest snapshot is restored from `STATE_DIR` (default `/data`) store by store — a damaged file or record is skipped and copied aside as `<file>.corrupt-<time>` (see `/api/health` → `snapshot.last_restore`). Manual snapshot: `POST /api/admin/snapshot`. |
| **CORS** | `ALLOWED_ORIGINS` env (comma-separated) + optional `ALLOWED_ORIGIN_REGEX`. Dev mode defaults to any-localhost. Prod mode (`APP_ENV=prod`) requires explicit allowlist. |
| **TLS** | Caddy auto-issues Let's Encrypt for non-localhost `HOSTNAME` (path A). Fly terminates TLS at the edge (path B). |
| **Health probes** | `/healthz` (liveness) and `/readyz` (readiness, includes snapshot status). Both registered for Docker, K8s, Fly. |
| **Process model** | Backend: uvicorn with `UVICORN_WORKERS=1` (state is process-local in-memory; do not scale workers without moving state to a shared store first). Frontend: Next.js standalone output (`next start` via `server.js`). Both run as non-root user `app` (uid 1000). |
| **Secrets** | `JWT_SECRET` (mandatory in prod — backend refuses the dev default), `DEEPSEEK_API_KEY`, SAP CPI vars. `.env.production` (gitignored) for Compose; `fly secrets set` for Fly. Never bake into images. |
| **SAP inbound webhook** | `POST /api/integrations/sap/event` needs `X-CPI-Token` = `SAP_WEBHOOK_TOKEN`; with no token set it only works in demo mode (otherwise 503). Send `event_id` as document + year + item (e.g. `5000001234-2026-0001`) so CPI retries apply once; replays are ignored, reversals (negative GR qty) are accepted, over-receipts are recorded and flagged. |
| **Audit log** | Bounded per tenant (10,000 events each), so one busy tenant can't evict another's history. |
| **Logs** | Both services write to stdout/stderr (12-factor). Caddy + nginx + supervisord all log to stdout. |
| **Restart policy** | `restart: unless-stopped` (Compose), `auto_restart` (supervisord), Fly's machine restart on health failure. |

---

## Project layout

```text
.
├── Makefile                       one-line entry to every workflow
├── scripts/
│   └── demo.sh                    orchestrator
├── app/                           FastAPI backend
│   ├── main.py                    routes
│   ├── schemas.py                 Pydantic models
│   ├── agent.py                   AI command center (DeepSeek + deterministic)
│   ├── agent_tools.py             20 tool definitions
│   ├── ai_assist.py               executive brief (DeepSeek)
│   ├── analytics.py               risk engine
│   ├── planning.py                projects, BOM, procurement plan
│   ├── sourcing.py                PR → RFQ → Quote → Award → PO
│   ├── vendor_intel.py            scorecards + concentration
│   ├── expediting.py              slip prediction + follow-ups
│   ├── logistics.py               shipments + mode recommender
│   ├── commercial.py              budget vs awarded
│   ├── simulations.py             3 what-if scenarios
│   └── weekly_plan.py             AI command-center weekly plan
├── frontend/                      Next.js 14 App Router
└── fixtures/
    ├── hydro/                     Mahadev Hydro synthetic data
    │   ├── bom_hydro.csv          70-line BOM
    │   ├── hydro_seed.py          project + 12 milestones + 35 suppliers + 25 inventory + 17 POs + 6 incidents
    │   ├── serve_with_hydro.py    boot wrapper that injects the fixture
    │   └── load_hydro.py          CLI loader
    └── seed_sourcing.py           walks 14 BOM items through PR → RFQ → Quote → Award → PO
```

## Architecture notes

- All persistence is **in-memory**, snapshotted to `.data/` — `make demo` wipes it and reseeds from `fixtures/`. Project + BOM persist via the planning store's import-time `_seed()`; sourcing workflow (PRs/RFQs/awards/POs) is HTTP-seeded post-startup and resets when the backend restarts.
- Backend port `8010`, frontend port `3001` (memory note: 3000 is often taken by the user's other project).
- LLM calls go to DeepSeek's OpenAI-compatible chat-completions endpoint; tool-calling shape mirrors OpenAI (`tools` with `type: function`, results returned as `role: tool`).

## Milestones

- ✅ M1: Shell + risk dashboard
- ✅ M2: Projects + BOM + procurement plan
- ✅ M3: Sourcing — PR → RFQ → Quote → Award → PO
- ✅ M4: Vendor intelligence + expediting
- ✅ M5: Logistics + commercial + simulations
- ✅ M6: AI command center (chat + tool calling, weekly plan)
- ✅ M7: Tenant scoping + RBAC + approvals (M7.1 persona login + JWT, M7.2 tenant-scoped RBAC, M7.3 approvals workflow)

See `Plan.md` for the full roadmap.
