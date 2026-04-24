"use client";

import { EmptyState } from "@/components/empty-state";
import { KpiTile } from "@/components/kpi-tile";
import { PageHeader } from "@/components/page-header";
import { ProjectTabs } from "@/components/project-tabs";
import { fetchProcurementPlan } from "@/lib/api";
import { formatDate, formatMoney } from "@/lib/format-date";
import { useAsync } from "@/lib/use-async";
import type { PlanFlag } from "@/lib/types";

export default function PlanPage({ params }: { params: { id: string } }) {
  const plan = useAsync(() => fetchProcurementPlan(params.id), [params.id]);

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={params.id}
        title={plan.data?.project_name ?? "Procurement Plan"}
        description="Generated from the BOM and milestones. Long-lead and missing-spec items bubble up as flags."
      />
      <ProjectTabs projectId={params.id} />

      {plan.loading ? (
        <EmptyState title="Building procurement plan..." />
      ) : plan.error ? (
        <div className="panel-sm border-[rgba(255,117,117,0.3)] text-[#ff9d9d]">{plan.error}</div>
      ) : !plan.data ? (
        <EmptyState title="No plan" />
      ) : (
        <>
          <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KpiTile label="BOM Items" value={String(plan.data.summary.bom_item_count)} />
            <KpiTile label="Packages" value={String(plan.data.summary.packages_count)} />
            <KpiTile
              label="Long-Lead"
              value={String(plan.data.summary.long_lead_count)}
              tone={plan.data.summary.long_lead_count ? "warn" : "neutral"}
            />
            <KpiTile
              label="Missing Specs"
              value={String(plan.data.summary.missing_spec_count)}
              tone={plan.data.summary.missing_spec_count ? "bad" : "good"}
            />
          </section>

          <section className="panel space-y-3">
            <div className="flex items-baseline justify-between">
              <h2 className="m-0 text-lg font-bold">Procurement Packages</h2>
              <div className="text-xs text-muted">
                Total: <span className="text-ink font-bold">{formatMoney(plan.data.summary.total_value_usd)}</span>
              </div>
            </div>
            {plan.data.packages.length === 0 ? (
              <EmptyState title="No packages" hint="Upload a BOM to build packages." />
            ) : (
              <div className="space-y-3">
                {plan.data.packages.map((pkg) => (
                  <article key={pkg.package_id} className="panel-sm">
                    <div className="flex items-start justify-between gap-3 flex-wrap">
                      <div>
                        <div className="text-[0.68rem] uppercase tracking-[0.14em] text-muted font-bold">
                          {pkg.milestone_code} · {pkg.package_id}
                        </div>
                        <div className="font-bold text-ink mt-1">{pkg.milestone_name}</div>
                        <div className="text-xs text-muted mt-1">
                          Required on site: {formatDate(pkg.required_on_site_date)}
                          {pkg.earliest_need_date ? ` · earliest item needed: ${formatDate(pkg.earliest_need_date)}` : ""}
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-xl font-extrabold text-ink">{formatMoney(pkg.total_value_usd)}</div>
                        <div className="text-xs text-muted">{pkg.item_count} items</div>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2 mt-3">
                      {pkg.long_lead_count > 0 ? (
                        <span className="badge severity-high">{pkg.long_lead_count} long-lead</span>
                      ) : null}
                      {pkg.missing_spec_count > 0 ? (
                        <span className="badge severity-critical">{pkg.missing_spec_count} missing spec</span>
                      ) : null}
                      {pkg.long_lead_count === 0 && pkg.missing_spec_count === 0 ? (
                        <span className="badge severity-low">clean</span>
                      ) : null}
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>

          <section className="grid grid-cols-1 xl:grid-cols-2 gap-5">
            <FlagList title="Long-Lead Items" flags={plan.data.long_lead_items} emptyMsg="No long-lead items." />
            <FlagList title="Missing Spec" flags={plan.data.missing_spec_items} emptyMsg="All items have specs." />
          </section>

          <section className="panel">
            <div className="section-title mb-3">Assumptions</div>
            <ul className="space-y-2 text-sm text-muted m-0 pl-5 list-disc">
              {plan.data.assumptions.map((a, i) => <li key={i}>{a}</li>)}
            </ul>
          </section>
        </>
      )}
    </div>
  );
}

function FlagList({ title, flags, emptyMsg }: { title: string; flags: PlanFlag[]; emptyMsg: string }) {
  return (
    <div className="panel space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="m-0 text-lg font-bold">{title}</h2>
        <span className="text-xs text-muted">{flags.length}</span>
      </div>
      {flags.length === 0 ? (
        <EmptyState title={emptyMsg} />
      ) : (
        <div className="space-y-2">
          {flags.map((f) => (
            <article key={`${f.bom_item_id}-${title}`} className="panel-sm">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-semibold text-ink">
                    <span className="font-mono text-xs text-muted mr-2">{f.code}</span>
                    {f.description}
                  </div>
                  <div className="text-sm text-muted mt-1">{f.reason}</div>
                </div>
                <span className={`badge severity-${f.severity} shrink-0`}>{f.severity}</span>
              </div>
              <div className="flex flex-wrap gap-2 mt-2">
                {f.milestone_code ? <Pill>Milestone {f.milestone_code}</Pill> : null}
                {f.long_lead_days != null ? <Pill>Lead {f.long_lead_days}d</Pill> : null}
                {f.days_until_need != null ? (
                  <Pill>{f.days_until_need < 0 ? `${Math.abs(f.days_until_need)}d overdue` : `need in ${f.days_until_need}d`}</Pill>
                ) : null}
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
