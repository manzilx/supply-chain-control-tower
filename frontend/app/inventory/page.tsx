"use client";

import { useMemo, useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { useStore } from "@/lib/store-context";
import type { Criticality } from "@/lib/types";

const CRIT_TONE: Record<Criticality, string> = {
  low: "severity-low",
  medium: "severity-medium",
  high: "severity-high",
  "mission-critical": "severity-critical",
};

export default function InventoryPage() {
  const { scenario } = useStore();
  const items = scenario?.inventory ?? [];
  const [onlyShort, setOnlyShort] = useState(false);
  const [query, setQuery] = useState("");

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items
      .map((i) => {
        const daysOfCover = i.daily_demand_qty > 0 ? i.on_hand_qty / i.daily_demand_qty : Infinity;
        const short = i.on_hand_qty <= i.reorder_point_qty || daysOfCover < i.lead_time_days;
        return { ...i, daysOfCover, short };
      })
      .filter((i) => !onlyShort || i.short)
      .filter((i) => !q || i.sku.toLowerCase().includes(q) || i.description.toLowerCase().includes(q))
      .sort((a, b) => a.daysOfCover - b.daysOfCover);
  }, [items, onlyShort, query]);

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Inventory"
        title="Inventory Coverage"
        description="SKU-level on-hand vs reorder, days-of-cover, and criticality. Deep demand/supply view arrives in M5."
      />

      <div className="panel-sm flex flex-wrap gap-3 items-end">
        <label className="flex-1 min-w-[200px] flex flex-col gap-1">
          <span className="text-[0.68rem] uppercase tracking-[0.12em] text-muted font-bold">Search</span>
          <input
            placeholder="SKU or description..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <label className="flex items-center gap-2 text-sm pb-2 cursor-pointer select-none">
          <input
            type="checkbox"
            className="w-4 h-4"
            checked={onlyShort}
            onChange={(e) => setOnlyShort(e.target.checked)}
            style={{ width: "1rem" }}
          />
          <span className="text-muted">Only shortages</span>
        </label>
        <div className="text-xs text-muted pb-2">{rows.length} items</div>
      </div>

      <div className="panel overflow-x-auto p-0">
        {rows.length ? (
          <table className="data-table">
            <thead>
              <tr>
                <th>SKU</th>
                <th>Description</th>
                <th>Supplier</th>
                <th>On Hand</th>
                <th>Reorder</th>
                <th>Daily Dmd</th>
                <th>Days Cover</th>
                <th>Lead Time</th>
                <th>Criticality</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((i) => (
                <tr key={i.sku}>
                  <td className="font-semibold text-ink font-mono">{i.sku}</td>
                  <td className="text-muted">{i.description}</td>
                  <td className="text-muted">{i.supplier_name}</td>
                  <td>{i.on_hand_qty}</td>
                  <td className="text-muted">{i.reorder_point_qty}</td>
                  <td>{i.daily_demand_qty}</td>
                  <td className={i.short ? "text-danger font-bold" : ""}>
                    {Number.isFinite(i.daysOfCover) ? i.daysOfCover.toFixed(0) : "∞"}d
                  </td>
                  <td>{i.lead_time_days}d</td>
                  <td>
                    <span className={`badge ${CRIT_TONE[i.criticality]}`}>{i.criticality}</span>
                  </td>
                  <td>
                    {i.short ? (
                      <span className="badge severity-high">Short</span>
                    ) : (
                      <span className="badge severity-low">OK</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="p-6">
            <EmptyState title="No inventory items" hint="Load the demo scenario or add items in Scenario." />
          </div>
        )}
      </div>
    </div>
  );
}
