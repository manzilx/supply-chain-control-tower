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
| `make demo` | Full boot: kill stale procs → start backend with hydro fixture → seed PR→RFQ→Quote→Award→PO → start frontend |
| `make backend-only` | Backend + seed, skip frontend (`./scripts/demo.sh --no-fe`) |
| `make fe-only` | Frontend dev server only (assumes backend already up) |
| `make seed` | Re-run the sourcing workflow seeder against a live backend |
| `make stop` | Kill backend + frontend cleanly |
| `make status` | Show which services are up + their PIDs |
| `make logs` | Tail all three log files (Ctrl-C to exit) |

Lower-level: `./scripts/demo.sh [stop|status|logs|seed|--no-seed|--no-fe]`.

Logs land in `.logs/` and PIDs in `.pids/` (both gitignored).

## What gets seeded

`make demo` lands the app in a fully-populated state:

- **3 projects**: Mahadev Hydro 220 MW (2×110 Francis), Riverbank 2×660 MW thermal, North Sea Offshore Substation
- **70 BOM items** on the hydro project across 15 categories (HM, turbine, generator, transformer, GIS, switchgear, cables, C&I, cooling water, lubrication, cranes, fire, HVAC, civil)
- **35 suppliers** with realistic OTD% / quality PPM / spend / single-source flags
- **28 inventory SKUs** (capital spares thin, consumables safe-cover)
- **15 PRs · 15 RFQs (3 quotes each) · 15 awards · 15 sourcing POs · 33 shipments** — full sourcing lifecycle
- **6 incidents** spanning critical / high / medium / low
- **21 risks** across 5 types (supplier_reliability, inventory_gap, incident, po_slip, single_source) on `/risks`
- **$22.7 M** in committed PO value across two projects on `/commercial`

## AI

Every AI feature routes through **Grok 4.1 fast reasoning** (xAI) when `XAI_API_KEY` is set, with a deterministic fallback if the key is missing or the call fails. Each response carries a `source: "grok" | "deterministic"` field so you can see which path produced the output.

**Activate:**

```bash
cp .env.example .env
# edit .env, set XAI_API_KEY=xai-...
make stop && make demo    # scripts/demo.sh auto-sources .env before starting
```

`.env` is gitignored. The orchestrator (`scripts/demo.sh`) auto-loads it before launching the backend + frontend, so child processes pick up every variable.

**What turns on with the key:**

| Surface | What Grok generates |
|---|---|
| `/agent` chat | Tool-calling responses (`source: "grok"`) |
| `/overview` | Executive prose brief |
| `/risks` | Per-risk mitigations (Mitigations button), per-risk Explain brief |
| `/simulate` | 2-paragraph executive narrative on every simulation result |
| `/weekly-plan` | Synthesized narrative over the rule-based plan |
| `/vendors/[name]` | AI risk briefing with headline · body · watchlist |
| `/projects/[id]` | Project Explain brief |
| Award rationale | Cited rationale on every PO awarded via the sourcing flow |
| Follow-up emails | Tone-aware PO-specific email body |
| BOM auto-fill (POST) | Category + supplier suggestions for sparse rows |
| Spec request (POST) | Email to engineering for missing-spec BOM items |
| `<ExplainButton />` | "What should I know about this" brief for PO/vendor/risk/project/RFQ/PR |

Configurable env vars (all live in `.env`):

| Var | Default | Purpose |
|---|---|---|
| `XAI_API_KEY` | _(required to enable Grok)_ | xAI API key |
| `XAI_MODEL` | `grok-4-1-fast-reasoning` | Model ID |
| `XAI_BASE_URL` | `https://api.x.ai/v1` | API base |
| `XAI_REASONING_EFFORT` | _(unset)_ | `low` or `high` to override reasoning depth |

## Deployment

Three paths, all from the same codebase. Pick one.

### Path A — Docker Compose on a VM (recommended for self-hosting)

Universal. Works on any cloud VM (AWS EC2, Hetzner, DigitalOcean, your laptop). Caddy auto-issues Let's Encrypt TLS. State persists across restarts in a Docker volume.

```bash
# One-time
cp .env.production.example .env.production
# edit .env.production — set HOSTNAME (or `localhost` for testing),
# JWT_SECRET (mandatory — `openssl rand -hex 32`), XAI_API_KEY, ALLOWED_ORIGINS, etc.

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
fly secrets set XAI_API_KEY=xai-... ALLOWED_ORIGIN_REGEX='https://your-app\.fly\.dev'

fly deploy
```

Edit `fly.toml` to change region, VM size, or auto-stop behaviour. The combined Dockerfile (`Dockerfile.combined`) is what Fly builds.

### Path C — Plain `make demo` (local dev only)

Already documented above. Don't expose this to the internet — no TLS, no CORS hardening, `next dev` instead of `next start`.

---

## Production hardening notes

| Concern | How it's handled |
|---|---|
| **State persistence** | Every in-memory store snapshots to JSON every 120 s (configurable via `SNAPSHOT_INTERVAL_SECONDS`). On boot, the FastAPI startup hook restores the latest snapshot from `STATE_DIR` (default `/data`). Survives restarts. Manual snapshot: `POST /api/admin/snapshot`. |
| **CORS** | `ALLOWED_ORIGINS` env (comma-separated) + optional `ALLOWED_ORIGIN_REGEX`. Dev mode defaults to any-localhost. Prod mode (`APP_ENV=prod`) requires explicit allowlist. |
| **TLS** | Caddy auto-issues Let's Encrypt for non-localhost `HOSTNAME` (path A). Fly terminates TLS at the edge (path B). |
| **Health probes** | `/healthz` (liveness) and `/readyz` (readiness, includes snapshot status). Both registered for Docker, K8s, Fly. |
| **Process model** | Backend: uvicorn with `UVICORN_WORKERS=1` (state is process-local in-memory; do not scale workers without moving state to a shared store first). Frontend: Next.js standalone output (`next start` via `server.js`). Both run as non-root user `app` (uid 1000). |
| **Secrets** | `JWT_SECRET` (mandatory in prod — backend refuses the dev default), `XAI_API_KEY`, SAP CPI vars. `.env.production` (gitignored) for Compose; `fly secrets set` for Fly. Never bake into images. |
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
│   ├── agent.py                   AI command center (Grok + deterministic)
│   ├── agent_tools.py             15 tool definitions
│   ├── ai_assist.py               executive brief (Grok)
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

- All persistence is **in-memory** — every cold boot reseeds from `fixtures/`. Project + BOM persist via the planning store's import-time `_seed()`; sourcing workflow (PRs/RFQs/awards/POs) is HTTP-seeded post-startup and resets when the backend restarts.
- Backend port `8010`, frontend port `3001` (memory note: 3000 is often taken by the user's other project).
- LLM calls go to xAI's OpenAI-compatible chat-completions endpoint; tool-calling shape mirrors OpenAI (`tools` with `type: function`, results returned as `role: tool`).

## Milestones

- ✅ M1: Shell + risk dashboard
- ✅ M2: Projects + BOM + procurement plan
- ✅ M3: Sourcing — PR → RFQ → Quote → Award → PO
- ✅ M4: Vendor intelligence + expediting
- ✅ M5: Logistics + commercial + simulations
- ✅ M6: AI command center (chat + tool calling, weekly plan)
- ✅ M7: Tenant scoping + RBAC + approvals (M7.1 persona login + JWT, M7.2 tenant-scoped RBAC, M7.3 approvals workflow)

See `Plan.md` for the full roadmap.
