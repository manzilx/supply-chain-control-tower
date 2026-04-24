"use client";

import { useEffect, useMemo, useState } from "react";

import { JsonEditor } from "@/components/json-editor";
import { PageHeader } from "@/components/page-header";
import { useStore } from "@/lib/store-context";
import { prettyJson } from "@/lib/format";
import type { AgentRequest, ScenarioDraft } from "@/lib/types";

function draftFromScenario(payload: AgentRequest): ScenarioDraft {
  return {
    companyName: payload.company.company_name,
    sector: payload.company.sector,
    activeProjects: String(payload.company.active_projects),
    horizonDays: String(payload.company.planner_horizon_days),
    serviceLevel: String(payload.company.target_service_level_pct),
    ask: payload.ask,
    suppliersJson: prettyJson(payload.suppliers),
    inventoryJson: prettyJson(payload.inventory),
    purchaseOrdersJson: prettyJson(payload.purchase_orders),
    demandSignalsJson: prettyJson(payload.demand_signals),
    incidentsJson: prettyJson(payload.incidents),
  };
}

function parseJsonArray<T>(value: string, field: string): T[] {
  try {
    const parsed = JSON.parse(value || "[]");
    if (!Array.isArray(parsed)) throw new Error("Expected an array");
    return parsed as T[];
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Invalid JSON";
    throw new Error(`${field}: ${msg}`);
  }
}

function buildPayload(draft: ScenarioDraft): AgentRequest {
  return {
    company: {
      company_name: draft.companyName.trim(),
      sector: draft.sector.trim(),
      active_projects: Number(draft.activeProjects) || 0,
      planner_horizon_days: Number(draft.horizonDays) || 0,
      target_service_level_pct: Number(draft.serviceLevel) || 0,
    },
    suppliers: parseJsonArray(draft.suppliersJson, "Suppliers"),
    inventory: parseJsonArray(draft.inventoryJson, "Inventory"),
    purchase_orders: parseJsonArray(draft.purchaseOrdersJson, "Purchase Orders"),
    demand_signals: parseJsonArray(draft.demandSignalsJson, "Demand Signals"),
    incidents: parseJsonArray(draft.incidentsJson, "Incidents"),
    ask: draft.ask.trim(),
  };
}

export function AgentWorkspace() {
  const { scenario, setScenario, analyze, status } = useStore();
  const initial = useMemo<ScenarioDraft | null>(() => (scenario ? draftFromScenario(scenario) : null), [scenario]);
  const [draft, setDraft] = useState<ScenarioDraft | null>(initial);
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    if (!draft && initial) setDraft(initial);
  }, [draft, initial]);

  function update<K extends keyof ScenarioDraft>(key: K, value: ScenarioDraft[K]) {
    setDraft((d) => (d ? { ...d, [key]: value } : d));
  }

  function applyAndAnalyze() {
    if (!draft) return;
    setLocalError(null);
    try {
      const payload = buildPayload(draft);
      setScenario(payload);
      void analyze();
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : "Invalid scenario");
    }
  }

  function resyncFromScenario() {
    if (scenario) setDraft(draftFromScenario(scenario));
  }

  if (!draft) {
    return (
      <div className="panel-sm text-center py-10 text-muted">Loading scenario...</div>
    );
  }

  const busy = status === "loading" || status === "analyzing";

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Scenario"
        title="Scenario Builder"
        description="Power-user editor for the structured scenario. CSV import and forms arrive in M2; this JSON view stays available as the escape hatch."
        right={
          <div className="flex gap-2">
            <button className="btn btn-secondary" onClick={resyncFromScenario} disabled={busy}>
              Reset to Current
            </button>
            <button className="btn btn-primary" onClick={applyAndAnalyze} disabled={busy}>
              {status === "analyzing" ? "Analyzing..." : "Apply & Analyze"}
            </button>
          </div>
        }
      />

      {localError ? (
        <div className="panel-sm border-[rgba(255,117,117,0.3)] text-[#ff9d9d]">{localError}</div>
      ) : null}

      <section className="panel space-y-4">
        <h2 className="text-lg font-bold m-0">Company</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <Field label="Company Name">
            <input value={draft.companyName} onChange={(e) => update("companyName", e.target.value)} />
          </Field>
          <Field label="Sector">
            <input value={draft.sector} onChange={(e) => update("sector", e.target.value)} />
          </Field>
          <Field label="Active Projects">
            <input value={draft.activeProjects} onChange={(e) => update("activeProjects", e.target.value)} />
          </Field>
          <Field label="Planner Horizon (days)">
            <input value={draft.horizonDays} onChange={(e) => update("horizonDays", e.target.value)} />
          </Field>
          <Field label="Target Service Level %">
            <input value={draft.serviceLevel} onChange={(e) => update("serviceLevel", e.target.value)} />
          </Field>
        </div>
        <Field label="Planner Question">
          <textarea rows={2} value={draft.ask} onChange={(e) => update("ask", e.target.value)} />
        </Field>
      </section>

      <section className="panel space-y-4">
        <h2 className="text-lg font-bold m-0">Data</h2>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          <JsonEditor label="Suppliers" value={draft.suppliersJson} onChange={(v) => update("suppliersJson", v)} />
          <JsonEditor label="Inventory" value={draft.inventoryJson} onChange={(v) => update("inventoryJson", v)} />
          <JsonEditor label="Purchase Orders" value={draft.purchaseOrdersJson} onChange={(v) => update("purchaseOrdersJson", v)} />
          <JsonEditor label="Demand Signals" value={draft.demandSignalsJson} onChange={(v) => update("demandSignalsJson", v)} />
          <div className="lg:col-span-2">
            <JsonEditor label="Incidents" rows={8} value={draft.incidentsJson} onChange={(v) => update("incidentsJson", v)} />
          </div>
        </div>
      </section>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[0.68rem] uppercase tracking-[0.12em] text-muted font-bold">{label}</span>
      {children}
    </label>
  );
}
