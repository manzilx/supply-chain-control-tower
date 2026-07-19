"use client";

import Link from "next/link";

import { Donut, MotionPanel, PRIORITY_COLOR } from "@/components/charts";
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

const ENTITY_PREFIXES = ["vendor:", "project:", "category:", "RFQ-", "PR-", "SPO-", "PO-"] as const;

function isEntityRef(ref: string): boolean {
  return ENTITY_PREFIXES.some((prefix) => ref.startsWith(prefix));
}

function projectIdFromRefs(refs: string[]): string | undefined {
  const hit = refs.find((ref) => ref.startsWith("project:"));
  return hit?.split(":", 2)[1];
}

function refHref(ref: string, refs: string[]): string | null {
  const projectId = projectIdFromRefs(refs);

  if (ref.startsWith("vendor:")) {
    return `/vendors/${encodeURIComponent(ref.split(":", 2)[1])}`;
  }
  if (ref.startsWith("project:")) {
    return `/projects/${ref.split(":", 2)[1]}`;
  }
  if (ref.startsWith("category:")) {
    return null;
  }
  if (ref.startsWith("RFQ-")) {
    return `/sourcing/rfqs/${ref}`;
  }
  if (ref.startsWith("PR-")) {
    return `/sourcing/prs/${ref}`;
  }
  if (ref.startsWith("SPO-") || ref.startsWith("PO-")) {
    return "/pos";
  }
  if (projectId && !isEntityRef(ref)) {
    return `/projects/${projectId}/bom`;
  }
  return null;
}

function RefChip({ label, refs }: { label: string; refs: string[] }) {
  const href = refHref(label, refs);
  const className =
    "inline-flex items-center rounded-full px-2 py-0.5 text-[0.65rem] font-mono bg-white/5 text-muted hover:text-accent hover:bg-white/10 transition-colors";

  if (!href) {
    return <span className={className}>{label}</span>;
  }

  return (
    <Link href={href} className={className}>
      {label}
    </Link>
  );
}

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

      {plan.synthesized_narrative ? (
        <section className="rounded-2xl border border-accent/30 bg-accent/[0.05] p-5">
          <div className="flex items-baseline justify-between gap-3 mb-2">
            <div className="text-[0.65rem] uppercase tracking-[0.14em] text-accent font-bold">
              AI synthesis
            </div>
            <span className="text-[0.6rem] uppercase tracking-[0.14em] text-muted">via grok</span>
          </div>
          <div className="text-sm text-ink/90 whitespace-pre-wrap leading-relaxed">
            {plan.synthesized_narrative}
          </div>
        </section>
      ) : null}

      {!compact && plan.items.length > 0 ? (
        <MotionPanel delay={0.15}>
          <section className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Donut
              title="Actions by priority"
              colorMap={PRIORITY_COLOR}
              data={Object.entries(
                plan.items.reduce((acc: Record<string, number>, i) => {
                  acc[i.priority] = (acc[i.priority] || 0) + 1;
                  return acc;
                }, {})
              ).map(([name, value]) => ({ name, value }))}
              centerLabel="actions"
              centerValue={plan.items.length}
              height={240}
            />
            <Donut
              title="Actions by category"
              data={Object.entries(
                plan.items.reduce((acc: Record<string, number>, i) => {
                  const key = CATEGORY_LABEL[i.category] || i.category;
                  acc[key] = (acc[key] || 0) + 1;
                  return acc;
                }, {})
              ).map(([name, value]) => ({ name, value }))}
              centerLabel="categories"
              centerValue={new Set(plan.items.map((i) => i.category)).size}
              height={240}
            />
          </section>
        </MotionPanel>
      ) : null}

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
                  {item.href ? (
                    <Link
                      href={item.href}
                      className="font-bold text-ink mt-1.5 hover:text-accent hover:underline inline-block"
                    >
                      {item.title}
                    </Link>
                  ) : (
                    <div className="font-bold text-ink mt-1.5">{item.title}</div>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {item.href && item.primary_action ? (
                    <Link href={item.href} className="btn btn-secondary text-xs">
                      {item.primary_action}
                    </Link>
                  ) : null}
                  <span className="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold bg-white/5 text-muted">
                    {item.owner}
                  </span>
                </div>
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
                    <RefChip key={r} label={r} refs={item.supporting_refs} />
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
