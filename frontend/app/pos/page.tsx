"use client";

import { useMemo, useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { useStore } from "@/lib/store-context";
import type { PurchaseOrderStatus } from "@/lib/types";

const STATUS_TONE: Record<PurchaseOrderStatus, string> = {
  planned: "severity-low",
  released: "severity-low",
  in_transit: "severity-medium",
  delayed: "severity-critical",
  received: "severity-low",
};

const STATUSES: PurchaseOrderStatus[] = ["planned", "released", "in_transit", "delayed", "received"];

export default function POsPage() {
  const { scenario } = useStore();
  const pos = scenario?.purchase_orders ?? [];
  const [status, setStatus] = useState<PurchaseOrderStatus | "all">("all");

  const rows = useMemo(
    () =>
      pos
        .filter((p) => status === "all" || p.status === status)
        .sort((a, b) => a.due_in_days - b.due_in_days),
    [pos, status],
  );

  const totalValue = pos.reduce((acc, p) => acc + p.value_usd, 0);
  const atRiskValue = pos
    .filter((p) => p.status === "delayed" || (p.due_in_days <= 14 && p.status !== "received"))
    .reduce((acc, p) => acc + p.value_usd, 0);
  const delayed = pos.filter((p) => p.status === "delayed").length;

  const fmtMoney = (n: number) => `$${n.toLocaleString("en", { maximumFractionDigits: 0 })}`;

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Purchase Orders"
        title="PO Queue"
        description="Active orders by due-in-days and status. Full PR → PO lifecycle arrives in M3."
      />

      <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <SummaryTile label="Open POs" value={String(pos.length)} />
        <SummaryTile label="Total Value" value={fmtMoney(totalValue)} />
        <SummaryTile label="At Risk" value={fmtMoney(atRiskValue)} tone="bad" />
        <SummaryTile label="Delayed" value={String(delayed)} tone={delayed ? "bad" : "neutral"} />
      </section>

      <div className="panel-sm flex flex-wrap gap-3 items-end">
        <label className="min-w-[180px] flex flex-col gap-1">
          <span className="text-[0.68rem] uppercase tracking-[0.12em] text-muted font-bold">Status</span>
          <select value={status} onChange={(e) => setStatus(e.target.value as PurchaseOrderStatus | "all")}>
            <option value="all">All</option>
            {STATUSES.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
          </select>
        </label>
        <div className="text-xs text-muted pb-2">{rows.length} of {pos.length}</div>
      </div>

      <div className="panel overflow-x-auto p-0">
        {rows.length ? (
          <table className="data-table">
            <thead>
              <tr>
                <th>PO #</th>
                <th>Supplier</th>
                <th>SKU</th>
                <th>Qty</th>
                <th>Value</th>
                <th>Due In</th>
                <th>Status</th>
                <th>Expedite</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr key={p.po_number}>
                  <td className="font-semibold text-ink font-mono">{p.po_number}</td>
                  <td className="text-muted">{p.supplier_name}</td>
                  <td className="text-muted font-mono text-xs">{p.sku}</td>
                  <td>{p.quantity}</td>
                  <td>{fmtMoney(p.value_usd)}</td>
                  <td className={p.due_in_days <= 7 ? "text-danger font-bold" : p.due_in_days <= 14 ? "text-warning font-bold" : ""}>
                    {p.due_in_days}d
                  </td>
                  <td>
                    <span className={`badge ${STATUS_TONE[p.status]}`}>{p.status.replace(/_/g, " ")}</span>
                  </td>
                  <td>{p.expedite_possible ? <span className="text-accent text-xs font-semibold">Yes</span> : <span className="text-muted text-xs">No</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="p-6">
            <EmptyState title="No purchase orders" hint="Load the demo scenario to see POs." />
          </div>
        )}
      </div>
    </div>
  );
}

function SummaryTile({ label, value, tone = "neutral" }: { label: string; value: string; tone?: "neutral" | "bad" | "good" }) {
  const color = tone === "bad" ? "text-danger" : tone === "good" ? "text-accent" : "text-ink";
  return (
    <div className="panel-sm">
      <div className="text-[0.7rem] uppercase tracking-[0.14em] text-muted font-bold mb-2">{label}</div>
      <div className={`text-2xl font-extrabold ${color}`}>{value}</div>
    </div>
  );
}
