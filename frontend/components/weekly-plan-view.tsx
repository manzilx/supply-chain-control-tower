"use client";

import { EmptyState } from "@/components/empty-state";
import type { KpiSnapshot, WeeklyCategory, WeeklyPlan, WeeklyPlanItem } from "@/lib/types";

const PRIORITY_TONE: Record<WeeklyPlanItem["priority"], string> = {
  P1: "severity-critical",
  P2: "severity-high",
  P3: "severity-medium",
};

const CATEGORY_LABEL: Record<WeeklyCategory, string> = {
  sourcing: "Sourcing",
  expediting: "Expediting",
  vendor_risk: "Vendor Risk",
  logistics: "Logistics",
  commercial: "Commercial",
  planning: "Planning",
};

const TONE_COLOR: Record<KpiSnapshot["tone"], string> = {
  good: "text-accent",
  warn: "text-warning",
  bad: "text-danger",
  neutral: "text-ink",
};

type Props = {
  plan: WeeklyPlan | null;
  loading: boolean;
  error: string | null;
  compact?: boolean;
};

export function WeeklyPlanView({ plan, loading, error, compact = false }: Props) {
  if (loading) return <EmptyState title="Building weekly plan..." />;
  if (error) return <div className="panel-sm border-[rgba(255,117,117,0.3)] text-[#ff9d9d]">{error}</div>;
  if (!plan) return <EmptyState title="No plan available" />;

  const items = compact ? plan.items.slice(0, 5) : plan.items;

  return (
    <div className="space-y-5">
      <section className="panel">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <div className="text-[0.68rem] uppercase tracking-[0.14em] text-accent font-bold">
              Week of {new Date(plan.week_of).toLocaleDateString("en", { month: "long", day: "numeric" })}
            </div>
            <h2 className="m-0 text-xl font-bold mt-1">{plan.headline}</h2>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mt-4">
          {plan.kpi_snapshot.map((kpi) => (
            <div key={kpi.label} className="panel-sm">
              <div className="text-[0.6rem] uppercase tracking-[0.14em] text-muted font-bold mb-1">
                {kpi.label}
              </div>
              <div className={`text-sm font-bold leading-tight ${TONE_COLOR[kpi.tone]}`}>
                {kpi.value}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        {items.length === 0 ? (
          <EmptyState title="No actions" hint="Nothing requires attention this week." />
        ) : (
          items.map((item, idx) => (
            <article key={`${item.title}-${idx}`} className="panel-sm">
              <div className="flex items-start justify-between gap-3 flex-wrap">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`badge ${PRIORITY_TONE[item.priority]}`}>{item.priority}</span>
                    <span className="text-[0.65rem] uppercase tracking-[0.12em] text-muted font-bold">
                      {CATEGORY_LABEL[item.category]}
                    </span>
                    <span className="text-xs text-muted">· due {item.due_in_days}d</span>
                    <span className="text-xs text-muted">· {item.confidence}% conf</span>
                  </div>
                  <div className="font-bold text-ink mt-1.5">{item.title}</div>
                </div>
                <span className="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold bg-white/5 text-muted shrink-0">
                  {item.owner}
                </span>
              </div>

              <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                <div>
                  <div className="text-[0.6rem] uppercase tracking-[0.14em] text-muted font-bold mb-1">Why</div>
                  <p className="text-ink/90 m-0 leading-relaxed">{item.why}</p>
                </div>
                <div>
                  <div className="text-[0.6rem] uppercase tracking-[0.14em] text-muted font-bold mb-1">Expected impact</div>
                  <p className="text-ink/90 m-0 leading-relaxed">{item.expected_impact}</p>
                </div>
              </div>

              {item.supporting_refs.length > 0 ? (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {item.supporting_refs.map((r) => (
                    <span key={r} className="inline-flex items-center rounded-full px-2 py-0.5 text-[0.65rem] font-mono bg-white/5 text-muted">
                      {r}
                    </span>
                  ))}
                </div>
              ) : null}
            </article>
          ))
        )}
      </section>

      {!compact && plan.assumptions.length > 0 ? (
        <section className="panel-sm">
          <div className="section-title mb-2">Assumptions</div>
          <ul className="text-xs text-muted list-disc pl-5 space-y-1 m-0">
            {plan.assumptions.map((a, i) => <li key={i}>{a}</li>)}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
