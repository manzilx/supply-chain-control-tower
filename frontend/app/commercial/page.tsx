"use client";

import { EmptyState } from "@/components/empty-state";
import { KpiTile } from "@/components/kpi-tile";
import { PageHeader } from "@/components/page-header";
import { fetchCommercialSummary } from "@/lib/api";
import { formatMoney } from "@/lib/format-date";
import { useAsync } from "@/lib/use-async";
import type { CommercialLine } from "@/lib/types";

const STATE_TONE: Record<CommercialLine["state"], string> = {
  budget_only: "severity-medium",
  quoted: "severity-low",
  awarded: "severity-low",
  delivered: "severity-low",
};

export default function CommercialPage() {
  const { data, loading, error } = useAsync(fetchCommercialSummary, []);

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Commercial"
        title="Commercial Control"
        description="Budget vs quoted vs awarded across all projects. Savings bubble up; overruns are flagged before they reach the bottom line."
      />

      {loading ? (
        <EmptyState title="Rolling commercials..." />
      ) : error ? (
        <div className="panel-sm border-[rgba(255,117,117,0.3)] text-[#ff9d9d]">{error}</div>
      ) : !data ? (
        <EmptyState title="No data" />
      ) : (
        <>
          <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KpiTile label="Total Budget" value={formatMoney(data.total_budget_usd)} />
            <KpiTile label="Awarded" value={formatMoney(data.total_awarded_usd)} />
            <KpiTile
              label="Savings"
              value={formatMoney(data.total_savings_usd)}
              tone={data.total_savings_usd > 0 ? "good" : "neutral"}
              hint={data.savings_pct > 0 ? `${data.savings_pct.toFixed(1)}%` : undefined}
            />
            <KpiTile
              label="Awarded vs Budget"
              value={data.total_budget_usd ? `${((data.total_awarded_usd / data.total_budget_usd - 1) * 100).toFixed(1)}%` : "—"}
              tone={data.total_awarded_usd > data.total_budget_usd ? "bad" : "neutral"}
            />
          </section>

          <section className="panel">
            <h2 className="m-0 text-lg font-bold mb-3">Projects</h2>
            {data.projects.length === 0 ? (
              <EmptyState title="No projects have PRs yet" hint="Create a PR from any BOM line to see commercials roll up." />
            ) : (
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Project</th>
                      <th>Lines</th>
                      <th>Budget</th>
                      <th>Quoted</th>
                      <th>Awarded</th>
                      <th>Savings</th>
                      <th>Variance</th>
                      <th>Over-budget</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.projects.map((p) => (
                      <tr key={p.project_id}>
                        <td>
                          <div className="font-semibold text-ink">{p.project_name}</div>
                          <div className="text-xs text-muted font-mono">{p.project_id}</div>
                        </td>
                        <td>{p.line_count}</td>
                        <td>{formatMoney(p.total_budget_usd)}</td>
                        <td>{formatMoney(p.total_quoted_usd)}</td>
                        <td>{formatMoney(p.total_awarded_usd)}</td>
                        <td className={p.total_savings_usd > 0 ? "text-accent font-semibold" : ""}>
                          {formatMoney(p.total_savings_usd)}
                          {p.savings_pct > 0 ? <div className="text-xs text-muted">({p.savings_pct.toFixed(1)}%)</div> : null}
                        </td>
                        <td className={p.variance_pct > 0 ? "text-danger font-semibold" : p.variance_pct < 0 ? "text-accent font-semibold" : "text-muted"}>
                          {p.variance_pct > 0 ? "+" : ""}
                          {p.variance_pct.toFixed(1)}%
                        </td>
                        <td className={p.over_budget_lines ? "text-warning font-bold" : "text-muted"}>
                          {p.over_budget_lines}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="grid grid-cols-1 xl:grid-cols-2 gap-5">
            <LineList title="Top Savings" lines={data.top_savings} emptyMsg="No savings logged yet." positive />
            <LineList title="Top Overruns" lines={data.top_overruns} emptyMsg="No overruns." positive={false} />
          </section>
        </>
      )}
    </div>
  );
}

function LineList({
  title,
  lines,
  emptyMsg,
  positive,
}: {
  title: string;
  lines: CommercialLine[];
  emptyMsg: string;
  positive: boolean;
}) {
  return (
    <div className="panel space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="m-0 text-lg font-bold">{title}</h2>
        <span className="text-xs text-muted">{lines.length}</span>
      </div>
      {lines.length === 0 ? (
        <EmptyState title={emptyMsg} />
      ) : (
        <div className="space-y-2">
          {lines.map((l) => (
            <article key={l.ref_id} className="panel-sm">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-xs text-muted font-mono">{l.ref_id} · {l.code}</div>
                  <div className="font-semibold text-ink mt-1">{l.description}</div>
                  {l.vendor ? <div className="text-xs text-muted mt-1">Vendor: {l.vendor}</div> : null}
                </div>
                <div className="text-right shrink-0">
                  <div className={`text-lg font-extrabold ${positive ? "text-accent" : "text-danger"}`}>
                    {positive ? "+" : ""}
                    {formatMoney(l.savings_usd)}
                  </div>
                  <div className="text-xs text-muted">
                    {l.variance_pct > 0 ? "+" : ""}
                    {l.variance_pct.toFixed(1)}% variance
                  </div>
                </div>
              </div>
              <div className="mt-2 flex flex-wrap gap-2 text-xs">
                <Pill>Budget {formatMoney(l.budget_value_usd)}</Pill>
                {l.quoted_value_usd != null ? <Pill>Quoted {formatMoney(l.quoted_value_usd)}</Pill> : null}
                {l.awarded_value_usd != null ? <Pill>Awarded {formatMoney(l.awarded_value_usd)}</Pill> : null}
                <span className={`badge ${STATE_TONE[l.state]}`}>{l.state.replace(/_/g, " ")}</span>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

function Pill({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold bg-white/5 text-muted">
      {children}
    </span>
  );
}
