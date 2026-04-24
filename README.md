# Engineering Supply Chain Agent

Fresh `.start/` workspace for an AI-assisted supply chain cockpit aimed at engineering, EPC, industrial manufacturing, and project-driven operations teams.

This version now uses a scalable split architecture:

- `app/` is a FastAPI backend with typed schemas and deterministic risk analysis
- `frontend/` is a TypeScript + React app built with Next.js App Router

## What it does

- Accepts structured supply-chain inputs for suppliers, inventory, purchase orders, demand, and incidents
- Computes risk signals for stock gaps, supplier reliability, sole-source exposure, PO slips, and open incidents
- Produces prioritized actions for planning, procurement, expediting, supplier quality, and operations
- Adds an AI-style executive brief with an optional external model call when `OPENAI_API_KEY` is configured
- Provides a typed React dashboard that is easier to extend into ERP, WMS, supplier portal, and workflow integrations

## Project layout

```text
.start/
  app/
    main.py
    analytics.py
    ai_assist.py
    schemas.py
    sample_data.py
  frontend/
    app/
    components/
    lib/
    package.json
    tsconfig.json
  requirements.txt
```

## Run the backend

```bash
cd "/Users/manzils/Documents/New project/.start"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8010
```

Backend health: [http://127.0.0.1:8010/api/health](http://127.0.0.1:8010/api/health)

## Run the frontend

```bash
cd "/Users/manzils/Documents/New project/.start/frontend"
npm install
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8010 npm run dev
```

Open [http://127.0.0.1:3000](http://127.0.0.1:3000).

## Optional AI model

The backend works without any external model. To enable a live AI brief, set:

```bash
export OPENAI_API_KEY=your_key
export OPENAI_MODEL=gpt-4o-mini
```

Optional base URL override for compatible providers:

```bash
export OPENAI_BASE_URL=https://api.openai.com/v1
```

## Why this front-end structure scales better

- Typed API contracts live in `frontend/lib/types.ts`
- Network calls are isolated in `frontend/lib/api.ts`
- UI concerns are split into reusable React components under `frontend/components/`
- The backend remains API-only, which makes it easier to add auth, persistence, background jobs, and multiple clients later

## Suggested next steps

- Add CSV or ERP ingestion for supplier masters, PO aging, and inventory snapshots
- Persist scenarios in SQLite or Postgres
- Add role-based workflows for buyers, planners, and supplier quality engineers
- Add authentication and saved workspaces for different projects or plants
- Connect the action engine to email, Slack, or Teams for daily control-tower summaries
