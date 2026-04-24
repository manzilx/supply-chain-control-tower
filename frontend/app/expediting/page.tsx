"use client";

import { useMemo, useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { FollowupModal } from "@/components/followup-modal";
import { KpiTile } from "@/components/kpi-tile";
import { PageHeader } from "@/components/page-header";
import { fetchExpediteQueue } from "@/lib/api";
import { formatMoney } from "@/lib/format-date";
import { useAsync } from "@/lib/use-async";
import type { ExpediteItem, ExpediteUrgency } from "@/lib/types";

const URGENCY_TONE: Record<ExpediteUrgency, string> = {
  ok: "severity-low",
  watch: "severity-low",
  nudge: "severity-medium",
  escalate: "severity-critical",
};

export default function ExpeditingPage() {
  const queue = useAsync(fetchExpediteQueue, []);
  const [urgency, setUrgency] = useState<ExpediteUrgency | "all">("all");
  const [source, setSource] = useState<"all" | "scenario" | "sourcing">("all");
  const [selected, setSelected] = useState<ExpediteItem | null>(null);

  const rows = useMemo(() => {
    const items = queue.data?.items ?? [];
    return items
      .filter((i) => urgency === "all" || i.urgency === urgency)
      .filter((i) => source === "all" || i.source === source);
  }, [queue.data, urgency, source]);

  const summary = queue.data?.summary;

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Expediting"
        title="Expediting Queue"
        description="Open orders with predicted slippage. Urgency bucketing drives which orders need a firm nudge or an escalation."
        right={
          <button className="btn btn-secondary" onClick={() => queue.reload()}>
            Refresh
          </button>
        }
      />

      {queue.loading ? (
        <EmptyState title="Building queue..." />
      ) : queue.error ? (
        <div className="panel-sm border-[rgba(255,117,117,0.3)] text-[#ff9d9d]">{queue.error}</div>
      ) : !summary ? (
        <EmptyState title="No data" />
      ) : (
        <>
          <section className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <KpiTile label="Total Orders" value={String(summary.total)} />
            <KpiTile label="OK" value={String(summary.ok)} tone="good" />
            <KpiTile label="Watch" value={String(summary.watch)} />
            <KpiTile label="Nudge" value={String(summary.nudge)} tone={summary.nudge ? "warn" : "neutral"} />
            <KpiTile label="Escalate" value={String(summary.escalate)} tone={summary.escalate ? "bad" : "good"} />
          </section>

          <div className="panel-sm text-sm">
            <span className="text-[0.7rem] uppercase tracking-[0.14em] text-muted font-bold mr-3">Value at risk</span>
            <span className="text-ink font-bold">{formatMoney(summary.value_at_risk_usd)}</span>
            <span className="text-muted text-xs ml-3">(across nudge + escalate)</span>
          </div>

          <div className="panel-sm flex flex-wrap gap-3 items-end">
            <label className="min-w-[160px] flex flex-col gap-1">
              <span className="text-[0.68rem] uppercase tracking-[0.12em] text-muted font-bold">Urgency</span>
              <select value={urgency} onChange={(e) => setUrgency(e.target.value as ExpediteUrgency | "all")}>
                <option value="all">All</option>
                <option value="escalate">Escalate</option>
                <option value="nudge">Nudge</option>
                <option value="watch">Watch</option>
                <option value="ok">OK</option>
              </select>
            </label>
            <label className="min-w-[160px] flex flex-col gap-1">
              <span className="text-[0.68rem] uppercase tracking-[0.12em] text-muted font-bold">Source</span>
              <select value={source} onChange={(e) => setSource(e.target.value as "all" | "scenario" | "sourcing")}>
                <option value="all">All</option>
                <option value="scenario">Scenario</option>
                <option value="sourcing">Sourcing</option>
              </select>
            </label>
            <div className="text-xs text-muted pb-2">{rows.length} of {queue.data?.items.length ?? 0}</div>
          </div>

          <div className="panel overflow-x-auto p-0">
            {rows.length === 0 ? (
              <div className="p-6"><EmptyState title="No orders match filters" /></div>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>PO #</th>
                    <th>Vendor</th>
                    <th>Item</th>
                    <th>Due</th>
                    <th>Status</th>
                    <th>Slip Prob</th>
                    <th>Expected Slip</th>
                    <th>Value</th>
                    <th>Urgency</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((i) => (
                    <tr key={`${i.source}-${i.po_number}`}>
                      <td className="font-mono text-xs">
                        <div className="text-ink font-semibold">{i.po_number}</div>
                        <div className="text-muted text-[0.65rem] uppercase tracking-wider">{i.source}</div>
                      </td>
                      <td className="font-semibold text-ink">{i.supplier_name}</td>
                      <td>
                        <div className="font-mono text-xs text-ink">{i.sku ?? "—"}</div>
                        {i.description ? (
                          <div className="text-xs text-muted mt-0.5 max-w-xs truncate">{i.description}</div>
                        ) : null}
                      </td>
                      <td className={i.due_in_days < 7 ? "text-danger font-bold" : i.due_in_days < 14 ? "text-warning font-bold" : ""}>
                        {i.due_in_days < 0 ? `${Math.abs(i.due_in_days)}d late` : `in ${i.due_in_days}d`}
                      </td>
                      <td className="text-muted capitalize">{i.status.replace(/_/g, " ")}</td>
                      <td className="font-bold">
                        <SlipBar pct={i.slip_probability_pct} />
                      </td>
                      <td>
                        {i.predicted_slip_days > 0 ? (
                          <span className="text-warning font-bold">+{i.predicted_slip_days}d</span>
                        ) : (
                          <span className="text-muted">—</span>
                        )}
                      </td>
                      <td>{formatMoney(i.value_usd)}</td>
                      <td>
                        <span className={`badge ${URGENCY_TONE[i.urgency]}`}>{i.urgency}</span>
                      </td>
                      <td>
                        <button
                          className="btn btn-secondary text-xs"
                          onClick={() => setSelected(i)}
                        >
                          Draft Email
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}

      {selected ? (
        <FollowupModal item={selected} onClose={() => setSelected(null)} />
      ) : null}
    </div>
  );
}

function SlipBar({ pct }: { pct: number }) {
  const color =
    pct >= 70 ? "bg-danger" : pct >= 40 ? "bg-warning" : pct >= 20 ? "bg-steady" : "bg-accent";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 min-w-[60px] h-1.5 bg-white/5 rounded-full overflow-hidden">
        <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-semibold w-10 text-right">{pct}%</span>
    </div>
  );
}
