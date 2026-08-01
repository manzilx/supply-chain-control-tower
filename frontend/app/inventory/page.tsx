"use client";

import { useEffect, useMemo, useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { KpiTile } from "@/components/kpi-tile";
import { PageHeader } from "@/components/page-header";
import { SkeletonCard } from "@/components/skeleton";
import { fetchCodeLedger, fetchStockBalances } from "@/lib/api";
import { formatTimestamp } from "@/lib/format";
import { useAsync } from "@/lib/use-async";
import type { StockBalance } from "@/lib/types";

// A SKU counts as "recently active" if its last movement fell within this
// window — the closest derivable proxy for receipts activity we have here.
const RECENT_WINDOW_DAYS = 7;

export default function InventoryPage() {
  const { data, loading, error, reload } = useAsync(fetchStockBalances, []);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<StockBalance | null>(null);

  const items = data ?? [];

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter(
      (i) => i.code.toLowerCase().includes(q) || i.description.toLowerCase().includes(q),
    );
  }, [items, query]);

  // Counts only — balances span mixed UOMs (EA, KG, M), so summing quantities
  // across rows would produce a number that means nothing.
  const totals = useMemo(() => {
    const cutoff = Date.now() - RECENT_WINDOW_DAYS * 24 * 60 * 60 * 1000;
    const codes = new Set<string>();
    const freeIssueCodes = new Set<string>();
    const stores = new Set<string>();
    let recent = 0;
    for (const i of items) {
      codes.add(i.code);
      if (i.free_issue_qty > 0) freeIssueCodes.add(i.code);
      stores.add(i.store_id);
      const moved = new Date(i.last_movement_at).getTime();
      if (!Number.isNaN(moved) && moved >= cutoff) recent += 1;
    }
    return {
      codes: codes.size,
      freeIssueCodes: freeIssueCodes.size,
      stores: stores.size,
      recent,
    };
  }, [items]);

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Site Store"
        title="Inventory"
        description="Stock on hand by code, split contractor-supplied vs free-issue. Select a row for its movement ledger."
        right={
          <button className="btn btn-secondary" onClick={() => reload()}>
            Refresh
          </button>
        }
      />

      <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiTile
          label="Distinct SKUs"
          value={String(totals.codes)}
          hint={`${items.length} store/UoM balance${items.length === 1 ? "" : "s"}`}
        />
        <KpiTile
          label="Free-Issue SKUs"
          value={String(totals.freeIssueCodes)}
          hint="SKUs holding client free-issue stock"
        />
        <KpiTile label="Stores" value={String(totals.stores)} hint="Site stores with stock on hand" />
        <KpiTile
          label={`Active (${RECENT_WINDOW_DAYS}d)`}
          value={String(totals.recent)}
          hint="Balances with a movement this week"
        />
      </section>

      <div className="panel-sm flex flex-wrap gap-3 items-end">
        <label className="flex-1 min-w-[200px] flex flex-col gap-1">
          <span className="text-[0.68rem] uppercase tracking-[0.12em] text-muted font-bold">Search</span>
          <input
            placeholder="Code or description..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <div className="text-xs text-muted pb-2">
          {loading ? "Loading…" : `${rows.length} of ${items.length}`}
        </div>
      </div>

      <div className="panel overflow-x-auto p-0">
        {loading ? (
          <div className="p-6 space-y-3">
            <SkeletonCard />
            <SkeletonCard />
          </div>
        ) : error ? (
          <div className="p-6 text-[#ff9d9d]">{error}</div>
        ) : rows.length === 0 ? (
          <div className="p-6">
            <EmptyState
              title={items.length === 0 ? "No stock on hand" : "No SKUs match this search"}
              hint={
                items.length === 0
                  ? "Confirmed GRNs post ledger entries that build stock balances here."
                  : undefined
              }
            />
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Code</th>
                <th>Description</th>
                <th>UoM</th>
                <th>Contractor Qty</th>
                <th>Free-Issue Qty</th>
                <th>Total Qty</th>
                <th>Last Movement</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((i) => (
                <tr
                  key={`${i.store_id}-${i.code}-${i.uom}`}
                  className="cursor-pointer"
                  onClick={() => setSelected(i)}
                >
                  <td className="font-semibold text-ink font-mono">{i.code}</td>
                  <td className="text-muted">{i.description}</td>
                  <td>{i.uom}</td>
                  <td>{i.contractor_qty.toLocaleString("en")}</td>
                  <td>{i.free_issue_qty.toLocaleString("en")}</td>
                  <td className="font-bold text-ink">{i.total_qty.toLocaleString("en")}</td>
                  <td className="text-muted text-xs">{formatTimestamp(i.last_movement_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {selected ? <LedgerDrawer item={selected} onClose={() => setSelected(null)} /> : null}
    </div>
  );
}

function LedgerDrawer({ item, onClose }: { item: StockBalance; onClose: () => void }) {
  const { data, loading, error } = useAsync(
    () => fetchCodeLedger(item.code, item.store_id),
    [item.code, item.store_id],
  );

  // Close on Escape.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const rows = data ?? [];

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="panel w-full max-w-3xl max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-4 gap-3">
          <div>
            <div className="text-[0.68rem] uppercase tracking-[0.14em] text-muted font-bold">
              Movement ledger · {item.code}
            </div>
            <h2 className="m-0 text-xl font-bold mt-1">{item.description}</h2>
            <div className="text-sm text-muted mt-1">
              Contractor {item.contractor_qty.toLocaleString("en")} {item.uom} · Free-issue{" "}
              {item.free_issue_qty.toLocaleString("en")} {item.uom} · Total{" "}
              {item.total_qty.toLocaleString("en")} {item.uom}
            </div>
          </div>
          <button className="btn btn-secondary text-xs" onClick={onClose}>
            Close
          </button>
        </div>

        {loading ? (
          <div className="space-y-3">
            <SkeletonCard />
          </div>
        ) : error ? (
          <div className="panel-sm border-[rgba(255,117,117,0.3)] text-[#ff9d9d]">{error}</div>
        ) : rows.length === 0 ? (
          <EmptyState title="No movements recorded" />
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Movement</th>
                <th>Qty</th>
                <th>Source</th>
                <th>Ref</th>
                <th>PO</th>
                <th>Vendor</th>
                <th>Effective</th>
                <th>Entered By</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.entry_id}>
                  <td className="capitalize">{r.movement.replace(/_/g, " ")}</td>
                  <td className={r.qty_signed < 0 ? "text-danger font-bold" : "text-accent font-bold"}>
                    {r.qty_signed > 0 ? "+" : ""}
                    {r.qty_signed.toLocaleString("en")}
                  </td>
                  <td className="text-muted capitalize">{r.source_kind.replace(/_/g, " ")}</td>
                  <td className="font-mono text-xs text-muted">
                    {r.ref_kind}:{r.ref_id}
                  </td>
                  <td className="font-mono text-xs">{r.po_no ?? "—"}</td>
                  <td className="text-muted">{r.vendor ?? "—"}</td>
                  <td className="text-muted text-xs">{formatTimestamp(r.effective_at)}</td>
                  <td className="text-muted">{r.entered_by}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
