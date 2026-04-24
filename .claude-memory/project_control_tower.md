---
name: Supply Chain Control Tower project
description: TypeScript/React + FastAPI control tower for engineering/EPC procurement, built in milestones (M1–M6) under .start/
type: project
originSessionId: a40f33a9-c482-4542-bc2d-1d7d2e106a3b
---
User is building a **Supply Chain Control Tower** for engineering / EPC / industrial procurement at `/Users/manzils/Documents/New project/.start/`.

- Backend: FastAPI (`.start/app/`) with in-memory stores, port 8010
- Frontend: Next.js 14 App Router + Tailwind + Recharts (`.start/frontend/`), usually lands on port 3001 because 3000 is often taken
- Roadmap lives in `.start/Plan.md` — 5 modules (Project Procurement Planner, Vendor & Sourcing Intelligence, Expediting & Logistics, Commercial & Risk, AI Command Center), 7 milestones
- Sidebar nav groups: Plan (Projects), Sourcing, Monitor (Overview/Risks/Actions), Operate (Vendors/Inventory/POs), Intelligence (Agent/Scenario)

**Milestone status (as of 2026-04-20):**
- M1 shell + risk dashboard: done
- M2 projects + BOM + procurement plan: done
- M3 sourcing PR→RFQ→Quote→Award→PO: done
- M4 vendor intelligence + expediting: next
- M5 logistics + commercial + risk simulations: not started
- M6 AI command center (chat + tool-calling): not started

**Why:** User's spec is ambitious (multi-module product aiming to replace a procurement manager). MVP cut is: project material planning, vendor scorecards, PO tracker, expediting assistant, risk dashboard, AI-generated weekly action plan.

**How to apply:** When continuing work, check Plan.md first; keep milestones additive (new modules, not rewrites). Use the in-memory stores for now — no DB yet. Claude API planned as primary LLM with OpenAI fallback (default decision).

**Gotchas:**
- `python-multipart` required (for BOM CSV upload)
- Backend CORS uses regex for any localhost port
- Dev port usually 3001; Safari is the user's browser
- Frontend reads `NEXT_PUBLIC_API_BASE` (http://127.0.0.1:8010)
