"use client";

import Link from "next/link";

import { ActionCard } from "@/components/action-card";
import { AnimatedKpiTile, Donut, Gauge, MotionPanel, SEVERITY_COLOR } from "@/components/charts";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { PortfolioDashboard } from "@/components/portfolio-dashboard";
import { RiskCard } from "@/components/risk-card";
import { WeeklyPlanView } from "@/components/weekly-plan-view";
import { fetchWeeklyPlan } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
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
  const { tenant } = useAuth();
  const { analysis } = useStore();
  const plan = useAsync(fetchWeeklyPlan, []);

  const topRisks = (analysis?.top_risks ?? []).slice(0, 5);
  const topActions = (analysis?.recommended_actions ?? []).slice(0, 5);
  const metrics = analysis?.watch_metrics ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Overview"
        title={tenant?.name ? `${tenant.name} · Control Tower` : "Control Tower"}
        description="Real-time portfolio cockpit. Press ⌘K to jump to any project, BOM line, vendor, PR or PO."
      />

      <PortfolioDashboard />

      {analysis ? (
        <>
          <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Gauge
              title="Overall Risk"
              subtitle="Composite of top 20 risks"
              value={analysis.overall_risk_score ?? 0}
              tone={
                (analysis.overall_risk_score ?? 0) >= 80 ? "bad" :
                (analysis.overall_risk_score ?? 0) >= 60 ? "warn" :
                (analysis.overall_risk_score ?? 0) >= 30 ? "neutral" : "good"
              }
              height={220}
            />
            <MotionPanel delay={0.1} className="md:col-span-2">
              {metrics.length > 0 ? (
                <div className="grid grid-cols-2 gap-3 h-full">
                  {metrics.slice(0, 4).map((m, i) => {
                    const numeric = Number(String(m.value).replace(/[^0-9.\-]/g, "")) || 0;
                    const suffix = String(m.value).replace(/[0-9.\-,]/g, "").trim();
                    const spark = Array.from({ length: 8 }, (_, k) => numeric * (0.7 + Math.sin(k + i) * 0.15 + k * 0.04));
                    return (
                      <AnimatedKpiTile
                        key={m.label}
                        label={m.label}
                        value={numeric || 0}
                        suffix={suffix ? " " + suffix : ""}
                        tone={toneFor(m)}
                        hint={m.direction === "up" ? "trending up" : m.direction === "down" ? "trending down" : "steady"}
                        delay={0.15 + i * 0.05}
                        spark={spark}
                      />
                    );
                  })}
                </div>
              ) : null}
            </MotionPanel>
          </section>

          {(analysis.top_risks?.length ?? 0) > 0 ? (
            <MotionPanel delay={0.25}>
              <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Donut
                  title="Risks by type"
                  data={Object.entries(
                    analysis.top_risks.reduce((acc: Record<string, number>, r) => {
                      acc[r.risk_type] = (acc[r.risk_type] || 0) + 1;
                      return acc;
                    }, {})
                  ).map(([name, value]) => ({ name: name.replace(/_/g, " "), value }))}
                  centerLabel="risks"
                  centerValue={analysis.top_risks.length}
                  height={220}
                />
                <Donut
                  title="Risks by severity"
                  colorMap={SEVERITY_COLOR}
                  data={Object.entries(
                    analysis.top_risks.reduce((acc: Record<string, number>, r) => {
                      acc[r.severity] = (acc[r.severity] || 0) + 1;
                      return acc;
                    }, {})
                  ).map(([name, value]) => ({ name, value }))}
                  centerLabel="critical+"
                  centerValue={analysis.top_risks.filter((r) => r.severity === "critical").length}
                  height={220}
                />
                <Donut
                  title="Actions by priority"
                  colorMap={{ P1: "#ff7a9a", P2: "#f0b44c", P3: "#7dc4ff" }}
                  data={Object.entries(
                    (analysis.recommended_actions ?? []).reduce((acc: Record<string, number>, a) => {
                      acc[a.priority] = (acc[a.priority] || 0) + 1;
                      return acc;
                    }, {})
                  ).map(([name, value]) => ({ name, value }))}
                  centerLabel="actions"
                  centerValue={(analysis.recommended_actions ?? []).length}
                  height={220}
                />
              </section>
            </MotionPanel>
          ) : null}

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
                <Link href="/risks" className="text-xs text-accent font-semibold uppercase tracking-wider hover:underline">
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

          {analysis.ai_assistant_response ? (
            <section className="panel">
              <div className="section-title mb-2">AI Brief</div>
              <pre className="whitespace-pre-wrap font-sans leading-relaxed text-sm text-ink/90 m-0">
                {analysis.ai_assistant_response}
              </pre>
            </section>
          ) : null}
        </>
      ) : null}

      <section>
        <div className="flex items-baseline justify-between mb-3">
          <h2 className="m-0 text-lg font-bold">This Week</h2>
          <Link href="/weekly-plan" className="text-xs text-accent font-semibold uppercase tracking-wider hover:underline">
            Full plan →
          </Link>
        </div>
        <WeeklyPlanView plan={plan.data} loading={plan.loading} error={plan.error} compact />
      </section>
    </div>
  );
}
