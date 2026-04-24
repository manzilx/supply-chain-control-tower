"use client";

import Link from "next/link";

import { EmptyState } from "@/components/empty-state";
import { KpiTile } from "@/components/kpi-tile";
import { PageHeader } from "@/components/page-header";
import { PRStatusBadge, RFQStatusBadge } from "@/components/sourcing-badges";
import { fetchAwards, fetchPrs, fetchRfqs, fetchSourcingPos } from "@/lib/api";
import { formatDate, formatMoney } from "@/lib/format-date";
import { useAsync } from "@/lib/use-async";

export default function SourcingPage() {
  const prs = useAsync(fetchPrs, []);
  const rfqs = useAsync(fetchRfqs, []);
  const awards = useAsync(fetchAwards, []);
  const pos = useAsync(fetchSourcingPos, []);

  const openRfqs = (rfqs.data ?? []).filter((r) => r.status !== "awarded" && r.status !== "cancelled").length;
  const pendingPrs = (prs.data ?? []).filter((p) => p.status === "draft" || p.status === "rfq_issued" || p.status === "quoted").length;
  const recentAwards = (awards.data ?? []).slice(0, 5);

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Sourcing"
        title="Sourcing Workbench"
        description="PR → RFQ → Quote → Award → PO. Create a PR from any BOM line, compare quotes, and let the control tower draft the PO."
      />

      <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiTile label="Open PRs" value={String(pendingPrs)} tone={pendingPrs ? "warn" : "neutral"} />
        <KpiTile label="Open RFQs" value={String(openRfqs)} tone={openRfqs ? "warn" : "neutral"} />
        <KpiTile label="Awards" value={String(awards.data?.length ?? 0)} tone="good" />
        <KpiTile label="PO Drafts" value={String(pos.data?.length ?? 0)} />
      </section>

      <section className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        <Panel title="Purchase Requisitions" link="" count={prs.data?.length ?? 0}>
          <PRList prs={prs.data ?? []} loading={prs.loading} error={prs.error} />
        </Panel>
        <Panel title="RFQs" link="" count={rfqs.data?.length ?? 0}>
          <RFQList rfqs={rfqs.data ?? []} loading={rfqs.loading} error={rfqs.error} />
        </Panel>
      </section>

      <section className="panel space-y-3">
        <h2 className="m-0 text-lg font-bold">Recent Awards</h2>
        {awards.loading ? (
          <EmptyState title="Loading awards..." />
        ) : recentAwards.length === 0 ? (
          <EmptyState title="No awards yet" hint="Award an RFQ to see it here." />
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Award</th>
                <th>Vendor</th>
                <th>RFQ</th>
                <th>PO</th>
                <th>Value</th>
                <th>When</th>
                <th>Rationale</th>
              </tr>
            </thead>
            <tbody>
              {recentAwards.map((a) => {
                const po = (pos.data ?? []).find((p) => p.award_id === a.award_id);
                return (
                  <tr key={a.award_id}>
                    <td className="font-mono text-xs text-ink">{a.award_id}</td>
                    <td className="font-semibold text-ink">{a.vendor}</td>
                    <td>
                      <Link href={`/sourcing/rfqs/${a.rfq_no}`} className="text-accent hover:underline font-mono text-xs">
                        {a.rfq_no}
                      </Link>
                    </td>
                    <td className="font-mono text-xs text-muted">{po?.po_no ?? "—"}</td>
                    <td>{formatMoney(a.awarded_value_usd)}</td>
                    <td className="text-muted text-xs">{formatDate(a.awarded_at)}</td>
                    <td className="text-xs text-muted max-w-md">{a.rationale}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

function Panel({ title, count, children }: { title: string; link: string; count: number; children: React.ReactNode }) {
  return (
    <div className="panel space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="m-0 text-lg font-bold">{title}</h2>
        <span className="text-xs text-muted">{count}</span>
      </div>
      {children}
    </div>
  );
}

function PRList({ prs, loading, error }: { prs: Awaited<ReturnType<typeof fetchPrs>>; loading: boolean; error: string | null }) {
  if (loading) return <EmptyState title="Loading..." />;
  if (error) return <div className="text-[#ff9d9d] text-sm">{error}</div>;
  if (!prs.length) return <EmptyState title="No PRs" hint="Create one from a BOM line." />;
  return (
    <div className="space-y-2">
      {prs.slice(0, 8).map((pr) => (
        <Link
          key={pr.pr_no}
          href={`/sourcing/prs/${pr.pr_no}`}
          className="panel-sm flex items-start justify-between gap-3 hover:border-accent/50 transition-colors"
        >
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono text-xs text-muted">{pr.pr_no}</span>
              <span className="font-semibold text-ink">{pr.code}</span>
              <PRStatusBadge status={pr.status} />
            </div>
            <div className="text-sm text-muted truncate mt-1">{pr.description}</div>
            <div className="text-xs text-muted mt-1">
              Qty {pr.quantity} {pr.uom}
              {pr.need_by ? ` · need ${formatDate(pr.need_by)}` : ""} · buyer {pr.buyer}
            </div>
          </div>
          <div className="text-right shrink-0">
            <div className="text-sm font-bold text-ink">{formatMoney(pr.budget_value_usd)}</div>
            {pr.rfq_no ? <div className="text-xs text-accent font-mono">{pr.rfq_no}</div> : null}
          </div>
        </Link>
      ))}
    </div>
  );
}

function RFQList({ rfqs, loading, error }: { rfqs: Awaited<ReturnType<typeof fetchRfqs>>; loading: boolean; error: string | null }) {
  if (loading) return <EmptyState title="Loading..." />;
  if (error) return <div className="text-[#ff9d9d] text-sm">{error}</div>;
  if (!rfqs.length) return <EmptyState title="No RFQs" hint="Issue an RFQ from a PR." />;
  return (
    <div className="space-y-2">
      {rfqs.slice(0, 8).map((r) => (
        <Link
          key={r.rfq_no}
          href={`/sourcing/rfqs/${r.rfq_no}`}
          className="panel-sm flex items-start justify-between gap-3 hover:border-accent/50 transition-colors"
        >
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono text-xs text-muted">{r.rfq_no}</span>
              <span className="font-semibold text-ink">{r.code}</span>
              <RFQStatusBadge status={r.status} />
            </div>
            <div className="text-sm text-muted truncate mt-1">{r.description}</div>
            <div className="text-xs text-muted mt-1">
              {r.vendors.length} vendors · due {formatDate(r.due_at)}
            </div>
          </div>
        </Link>
      ))}
    </div>
  );
}
