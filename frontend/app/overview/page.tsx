"use client";

import Link from "next/link";

import { ActionCard } from "@/components/action-card";
import { EmptyState } from "@/components/empty-state";
import { KpiTile } from "@/components/kpi-tile";
import { PageHeader } from "@/components/page-header";
import { RiskCard } from "@/components/risk-card";
import { WeeklyPlanView } from "@/components/weekly-plan-view";
import { fetchWeeklyPlan } from "@/lib/api";
import { useStore } from "@/lib/store-context";
import { useAsync } from "@/lib/use-async";
import type { WatchMetric } from "@/lib/types";

function toneFor(metric: WatchMetric): "neutral" | "good" | "warn" | "bad" {
  if (metric.direction === "up") {
    const l = metric.label.toLowerCase();
    return l.includes("risk") || l.includes("shortage") || l.includes("incident") || l.includes("critical") ? "bad" : "warn";
  }
  if (metric.direction === "down") return "good";
  return "neutral";
}

export default function OverviewPage() {
  const { scenario, analysis, status } = useStore();
  const plan = useAsync(fetchWeeklyPlan, []);

  const metrics = analysis?.watch_metrics ?? [];
  const topRisks = (analysis?.top_risks ?? []).slice(0, 5);
  const topActions = (analysis?.recommended_actions ?? []).slice(0, 5);

  const counts = {
    suppliers: scenario?.suppliers.length ?? 0,
    inventory: scenario?.inventory.length ?? 0,
    pos: scenario?.purchase_orders.length ?? 0,
    incidents: scenario?.incidents.length ?? 0,
  };

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Overview"
        title={scenario ? `${scenario.company.company_name} · Daily Brief` : "Control Tower"}
        description={
          analysis?.executive_summary ??
          (status === "loading"
            ? "Loading demo scenario..."
            : "Load the demo scenario or edit the inputs to generate a brief.")
        }
      />

      {metrics.length > 0 ? (
        <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {metrics.map((m) => (
            <KpiTile
              key={m.label}
              label={m.label}
              value={m.value}
              tone={toneFor(m)}
              hint={m.direction === "up" ? "trending up" : m.direction === "down" ? "trending down" : "steady"}
            />
          ))}
        </section>
      ) : (
        <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KpiTile label="Suppliers" value={String(counts.suppliers)} />
          <KpiTile label="SKUs Tracked" value={String(counts.inventory)} />
          <KpiTile label="Open POs" value={String(counts.pos)} />
          <KpiTile label="Open Incidents" value={String(counts.incidents)} tone={counts.incidents ? "warn" : "neutral"} />
        </section>
      )}

      <section>
        <div className="flex items-baseline justify-between mb-3">
          <h2 className="m-0 text-lg font-bold">This Week</h2>
          <Link href="/weekly-plan" className="text-xs text-accent font-semibold uppercase tracking-wider hover:underline">
            Full plan →
          </Link>
        </div>
        <WeeklyPlanView plan={plan.data} loading={plan.loading} error={plan.error} compact />
      </section>

      <section className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        <div className="panel space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold m-0">Top Risks</h2>
            <Link href="/risks" className="text-xs text-accent font-semibold uppercase tracking-wider hover:underline">
              View all →
            </Link>
          </div>
          {topRisks.length ? (
            <div className="space-y-3">
              {topRisks.map((r) => (
                <RiskCard key={`${r.title}-${r.score}`} risk={r} />
              ))}
            </div>
          ) : (
            <EmptyState
              title="No risks yet"
              hint="Run an analysis to surface risks from the current scenario."
            />
          )}
        </div>

        <div className="panel space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold m-0">Top Actions</h2>
            <Link href="/actions" className="text-xs text-accent font-semibold uppercase tracking-wider hover:underline">
              View all →
            </Link>
          </div>
          {topActions.length ? (
            <div className="space-y-3">
              {topActions.map((a) => (
                <ActionCard key={`${a.title}-${a.owner}`} action={a} />
              ))}
            </div>
          ) : (
            <EmptyState
              title="No actions yet"
              hint="Actions are generated from the top risks after analysis."
            />
          )}
        </div>
      </section>

      {analysis?.ai_assistant_response ? (
        <section className="panel">
          <div className="section-title mb-2">AI Brief</div>
          <pre className="whitespace-pre-wrap font-sans leading-relaxed text-sm text-ink/90 m-0">
            {analysis.ai_assistant_response}
          </pre>
        </section>
      ) : null}
    </div>
  );
}
