"use client";

import { useMemo, useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { useStore } from "@/lib/store-context";
import type { RiskRecord, Severity } from "@/lib/types";

const SEVERITIES: Severity[] = ["low", "medium", "high", "critical"];

export default function RisksPage() {
  const { analysis } = useStore();
  const risks = analysis?.top_risks ?? [];

  const [severity, setSeverity] = useState<Severity | "all">("all");
  const [risk_type, setType] = useState<string>("all");
  const [query, setQuery] = useState("");

  const types = useMemo(() => {
    const s = new Set<string>();
    risks.forEach((r) => s.add(r.risk_type));
    return Array.from(s);
  }, [risks]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return risks
      .filter((r) => severity === "all" || r.severity === severity)
      .filter((r) => risk_type === "all" || r.risk_type === risk_type)
      .filter((r) => !q || r.title.toLowerCase().includes(q) || r.summary.toLowerCase().includes(q))
      .sort((a, b) => b.score - a.score);
  }, [risks, severity, risk_type, query]);

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Risks"
        title="Risk Register"
        description="Every risk surfaced by the current analysis, sortable and filterable."
      />

      <div className="panel-sm flex flex-wrap gap-3 items-end">
        <FilterGroup label="Severity">
          <select value={severity} onChange={(e) => setSeverity(e.target.value as Severity | "all")}>
            <option value="all">All severities</option>
            {SEVERITIES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </FilterGroup>
        <FilterGroup label="Type">
          <select value={risk_type} onChange={(e) => setType(e.target.value)}>
            <option value="all">All types</option>
            {types.map((t) => (
              <option key={t} value={t}>{t.replace(/_/g, " ")}</option>
            ))}
          </select>
        </FilterGroup>
        <FilterGroup label="Search" grow>
          <input
            placeholder="Filter by title or summary..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </FilterGroup>
        <div className="text-xs text-muted pb-2">
          {filtered.length} of {risks.length}
        </div>
      </div>

      <div className="panel overflow-x-auto p-0">
        {filtered.length ? (
          <table className="data-table">
            <thead>
              <tr>
                <th>Risk</th>
                <th>Type</th>
                <th>Severity</th>
                <th>Score</th>
                <th>Supplier</th>
                <th>SKU</th>
                <th>Owner</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r: RiskRecord) => (
                <tr key={`${r.title}-${r.score}`}>
                  <td>
                    <div className="font-semibold text-ink">{r.title}</div>
                    <div className="text-xs text-muted mt-1 max-w-xl">{r.summary}</div>
                  </td>
                  <td className="text-muted capitalize">{r.risk_type.replace(/_/g, " ")}</td>
                  <td>
                    <span className={`badge severity-${r.severity}`}>{r.severity}</span>
                  </td>
                  <td className="font-bold">{r.score}</td>
                  <td className="text-muted">{r.supplier_name ?? "—"}</td>
                  <td className="text-muted">{r.sku ?? "—"}</td>
                  <td className="text-muted">{r.owner}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="p-6">
            <EmptyState
              title={risks.length ? "No risks match filters" : "No risks to show"}
              hint={risks.length ? "Adjust the filters above to see more." : "Run an analysis from the top bar to populate risks."}
            />
          </div>
        )}
      </div>
    </div>
  );
}

function FilterGroup({ label, grow, children }: { label: string; grow?: boolean; children: React.ReactNode }) {
  return (
    <label className={`flex flex-col gap-1 ${grow ? "flex-1 min-w-[200px]" : "min-w-[160px]"}`}>
      <span className="text-[0.68rem] uppercase tracking-[0.12em] text-muted font-bold">{label}</span>
      {children}
    </label>
  );
}
