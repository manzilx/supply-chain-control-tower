"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { SkeletonCard } from "@/components/skeleton";
import { fetchStoreGrn, fetchStoreGrns } from "@/lib/api";
import { formatTimestamp } from "@/lib/format";
import { useAsync } from "@/lib/use-async";
import type { GrnDetail, GrnStatus, GrnSummary } from "@/lib/types";

const STATUS_TONE: Record<GrnStatus, string> = {
  captured: "severity-medium",
  extracting: "severity-medium",
  matched: "severity-medium",
  suggested: "severity-high",
  triage: "severity-critical",
  confirmed: "severity-low",
  cancelled: "text-muted",
  superseded: "text-muted",
};

const FILTERS: (GrnStatus | "all")[] = ["all", "triage", "suggested", "matched", "confirmed", "cancelled"];

function shortId(g: GrnSummary): string {
  return g.grn_no ?? `${g.grn_id.slice(0, 10)}…`;
}

export default function GrnRegisterPage() {
  const [filter, setFilter] = useState<GrnStatus | "all">("all");
  const query = useAsync(() => fetchStoreGrns(filter === "all" ? {} : { status: filter }), [filter]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const rows = query.data ?? [];

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Site Store"
        title="GRN Register"
        description="Every goods receipt captured from the field, across all match and confirmation states."
        right={
          <button className="btn btn-secondary" onClick={() => query.reload()}>
            Refresh
          </button>
        }
      />

      <div className="flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
              filter === f
                ? "border-accent text-accent bg-accent/[0.06]"
                : "border-line text-muted hover:text-ink"
            }`}
          >
            {f === "all" ? "All" : f}
          </button>
        ))}
      </div>

      <div className="panel overflow-x-auto p-0">
        {query.loading ? (
          <div className="p-6 space-y-3">
            <SkeletonCard />
            <SkeletonCard />
          </div>
        ) : query.error ? (
          <div className="p-6 text-[#ff9d9d]">{query.error}</div>
        ) : rows.length === 0 ? (
          <div className="p-6">
            <EmptyState
              title="No GRNs"
              hint={filter === "all" ? "Captured receipts will appear here." : "No GRNs match this status filter."}
            />
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>GRN</th>
                <th>Status</th>
                <th>Source</th>
                <th>Vendor</th>
                <th>Challan</th>
                <th>Lines</th>
                <th>Observed</th>
                <th>Confirmed</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((g) => (
                <tr key={g.grn_id} className="cursor-pointer" onClick={() => setSelectedId(g.grn_id)}>
                  <td className="font-mono text-xs text-ink">{shortId(g)}</td>
                  <td>
                    <span className={`badge ${STATUS_TONE[g.status]}`}>{g.status}</span>
                  </td>
                  <td className="text-muted capitalize">{g.source_kind.replace(/_/g, " ")}</td>
                  <td className="text-muted">{g.vendor_name ?? "—"}</td>
                  <td className="text-muted">{g.challan_no ?? "—"}</td>
                  <td>{g.line_count}</td>
                  <td className="text-muted text-xs">{formatTimestamp(g.observed_at)}</td>
                  <td className="text-muted text-xs">
                    {g.confirmed_at ? formatTimestamp(g.confirmed_at) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {selectedId ? <GrnDetailModal grnId={selectedId} onClose={() => setSelectedId(null)} /> : null}
    </div>
  );
}

function GrnDetailModal({ grnId, onClose }: { grnId: string; onClose: () => void }) {
  const { data: grn, loading, error } = useAsync(() => fetchStoreGrn(grnId), [grnId]);

  // Close on Escape.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

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
        {loading ? (
          <div className="space-y-3">
            <SkeletonCard />
          </div>
        ) : error || !grn ? (
          <div className="panel-sm border-[rgba(255,117,117,0.3)] text-[#ff9d9d]">
            {error ?? "GRN not found"}
          </div>
        ) : (
          <GrnDetailBody grn={grn} onClose={onClose} />
        )}
      </div>
    </div>
  );
}

function GrnDetailBody({ grn, onClose }: { grn: GrnDetail; onClose: () => void }) {
  return (
    <>
      <div className="flex items-start justify-between mb-4 gap-3">
        <div>
          <div className="text-[0.68rem] uppercase tracking-[0.14em] text-muted font-bold">
            {grn.grn_no ?? grn.grn_id}
          </div>
          <h2 className="m-0 text-xl font-bold mt-1">
            {grn.vendor_name ?? grn.vendor_name_raw ?? "Unknown vendor"}
          </h2>
          <div className="flex items-center gap-2 mt-2">
            <span className={`badge ${STATUS_TONE[grn.status]}`}>{grn.status}</span>
            <span className="text-sm text-muted capitalize">{grn.source_kind.replace(/_/g, " ")}</span>
          </div>
        </div>
        <button className="btn btn-secondary text-xs" onClick={onClose}>
          Close
        </button>
      </div>

      <div className="panel-sm grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-3 text-sm mb-4">
        <Field label="Challan #">{grn.challan_no ?? "—"}</Field>
        <Field label="Challan Date">{grn.challan_date ? formatTimestamp(grn.challan_date) : "—"}</Field>
        <Field label="Vehicle #">{grn.vehicle_no ?? "—"}</Field>
        <Field label="Observed">{formatTimestamp(grn.observed_at)}</Field>
        <Field label="Confirmed">{grn.confirmed_at ? formatTimestamp(grn.confirmed_at) : "—"}</Field>
        <Field label="Confirmed By">{grn.confirmed_by ?? "—"}</Field>
      </div>

      {grn.remarks ? <div className="panel-sm mb-4 text-sm text-muted italic">"{grn.remarks}"</div> : null}

      <table className="data-table">
        <thead>
          <tr>
            <th>Line</th>
            <th>Description</th>
            <th>Code</th>
            <th>Qty Received</th>
            <th>Qty Damaged</th>
            <th>Qty Rejected</th>
            <th>Match</th>
            <th>PO</th>
          </tr>
        </thead>
        <tbody>
          {grn.lines.map((line) => (
            <tr key={line.grn_line_id}>
              <td>{line.line_no}</td>
              <td>{line.description_raw}</td>
              <td className="font-mono text-xs">{line.code ?? "—"}</td>
              <td>{line.qty_received}</td>
              <td>{line.qty_damaged}</td>
              <td>{line.qty_rejected}</td>
              <td>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="capitalize text-muted">{line.match_status.replace(/_/g, " ")}</span>
                  {line.over_receipt ? (
                    <span className="badge severity-high">over receipt</span>
                  ) : null}
                </div>
              </td>
              <td className="font-mono text-xs">
                {line.po_no ? (
                  <Link
                    href={`/audit?po_no=${encodeURIComponent(line.po_no)}`}
                    className="text-accent hover:underline"
                  >
                    {line.po_no}
                  </Link>
                ) : (
                  "—"
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[0.62rem] uppercase tracking-[0.12em] text-muted font-bold">{label}</span>
      <div>{children}</div>
    </div>
  );
}
