"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { SapStatusBadge } from "@/components/sap-status";
import { Skeleton } from "@/components/skeleton";
import { fetchSourcingPos } from "@/lib/api";
import { daysFromNow, formatDate, formatMoney } from "@/lib/format-date";
import { useAsync } from "@/lib/use-async";
import type { SourcingPO } from "@/lib/types";

type PoStatus = SourcingPO["status"];

const STATUS_TONE: Record<PoStatus, string> = {
  draft: "severity-medium",
  released: "severity-low",
  in_transit: "severity-medium",
  delivered: "severity-low",
};

const STATUSES: PoStatus[] = ["draft", "released", "in_transit", "delivered"];

function isAtRisk(po: SourcingPO): boolean {
  if (po.status === "delivered") return false;
  const due = daysFromNow(po.need_by);
  return due !== null && due <= 14;
}

function isOverdue(po: SourcingPO): boolean {
  if (po.status === "delivered") return false;
  const due = daysFromNow(po.need_by);
  return due !== null && due < 0;
}

export default function POsPage() {
  const posQuery = useAsync(fetchSourcingPos, []);
  const pos = posQuery.data ?? [];
  const [status, setStatus] = useState<PoStatus | "all">("all");

  const rows = useMemo(
    () =>
      pos
        .filter((p) => status === "all" || p.status === status)
        .sort((a, b) => {
          const da = daysFromNow(a.need_by) ?? 9999;
          const db = daysFromNow(b.need_by) ?? 9999;
          return da - db;
        }),
    [pos, status],
  );

  const openPos = pos.filter((p) => p.status !== "delivered");
  const totalValue = openPos.reduce((acc, p) => acc + p.value_usd, 0);
  const atRiskValue = openPos.filter(isAtRisk).reduce((acc, p) => acc + p.value_usd, 0);
  const overdueCount = openPos.filter(isOverdue).length;

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Purchase Orders"
        title="PO Queue"
        description="Purchase orders from awarded RFQs. Track draft → release → transit and SAP sync across the PR → PO lifecycle."
        right={
          <button className="btn btn-secondary" onClick={() => posQuery.reload()}>
            Refresh
          </button>
        }
      />

      <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {posQuery.loading ? (
          <>
            <SkeletonTile />
            <SkeletonTile />
            <SkeletonTile />
            <SkeletonTile />
          </>
        ) : (
          <>
            <SummaryTile label="Open POs" value={String(openPos.length)} />
            <SummaryTile label="Open Value" value={formatMoney(totalValue)} />
            <SummaryTile label="At Risk" value={formatMoney(atRiskValue)} tone={atRiskValue ? "bad" : "neutral"} />
            <SummaryTile label="Overdue" value={String(overdueCount)} tone={overdueCount ? "bad" : "neutral"} />
          </>
        )}
      </section>

      <div className="panel-sm flex flex-wrap gap-3 items-end">
        <label className="min-w-[180px] flex flex-col gap-1">
          <span className="text-[0.68rem] uppercase tracking-[0.12em] text-muted font-bold">Status</span>
          <select value={status} onChange={(e) => setStatus(e.target.value as PoStatus | "all")} disabled={posQuery.loading}>
            <option value="all">All</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </label>
        <div className="text-xs text-muted pb-2">
          {posQuery.loading ? "Loading…" : `${rows.length} of ${pos.length}`}
        </div>
      </div>

      <div className="panel overflow-x-auto p-0">
        {posQuery.loading ? (
          <div className="p-6">
            <EmptyState title="Loading purchase orders..." />
          </div>
        ) : posQuery.error ? (
          <div className="p-6 text-[#ff9d9d]">{posQuery.error}</div>
        ) : rows.length ? (
          <table className="data-table">
            <thead>
              <tr>
                <th>PO #</th>
                <th>Vendor</th>
                <th>Item</th>
                <th>Qty</th>
                <th>Value</th>
                <th>Need By</th>
                <th>Due In</th>
                <th>Status</th>
                <th>RFQ</th>
                <th>SAP</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => {
                const dueIn = daysFromNow(p.need_by);
                return (
                  <tr key={p.po_no}>
                    <td className="font-semibold text-ink font-mono text-xs">
                      {p.rfq_no ? (
                        <Link href={`/sourcing/rfqs/${encodeURIComponent(p.rfq_no)}`} className="text-accent hover:underline">
                          {p.po_no}
                        </Link>
                      ) : (
                        p.po_no
                      )}
                    </td>
                    <td className="text-muted">
                      <Link href={`/vendors/${encodeURIComponent(p.vendor)}`} className="font-semibold text-ink hover:underline">
                        {p.vendor}
                      </Link>
                    </td>
                    <td>
                      <div className="font-mono text-xs text-ink">{p.code}</div>
                      {p.description ? (
                        <div className="text-xs text-muted mt-0.5 max-w-xs truncate">{p.description}</div>
                      ) : null}
                    </td>
                    <td>
                      {p.quantity} {p.uom}
                    </td>
                    <td>{formatMoney(p.value_usd)}</td>
                    <td className="text-muted text-xs">{formatDate(p.need_by)}</td>
                    <td
                      className={
                        dueIn !== null && dueIn < 0
                          ? "text-danger font-bold"
                          : dueIn !== null && dueIn <= 7
                            ? "text-danger font-bold"
                            : dueIn !== null && dueIn <= 14
                              ? "text-warning font-bold"
                              : ""
                      }
                    >
                      {dueIn === null ? "—" : dueIn < 0 ? `${Math.abs(dueIn)}d late` : `${dueIn}d`}
                    </td>
                    <td>
                      <span className={`badge ${STATUS_TONE[p.status]}`}>{p.status.replace(/_/g, " ")}</span>
                    </td>
                    <td>
                      {p.rfq_no ? (
                        <Link href={`/sourcing/rfqs/${encodeURIComponent(p.rfq_no)}`} className="text-accent hover:underline font-mono text-xs">
                          {p.rfq_no}
                        </Link>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                    <td>
                      <SapStatusBadge status={p.sap_status} sapDocNo={p.sap_po_no} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <div className="p-6">
            <EmptyState
              title="No purchase orders"
              hint={status === "all" ? "Award an RFQ to draft a PO." : "No POs match this status filter."}
            />
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

function SkeletonTile() {
  return (
    <div className="panel-sm space-y-2">
      <Skeleton height={12} width="55%" />
      <Skeleton height={28} width="40%" />
    </div>
  );
}
