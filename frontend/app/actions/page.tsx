"use client";

import { useMemo, useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { useStore } from "@/lib/store-context";
import type { RecommendedAction } from "@/lib/types";

const PRIORITY_TONE: Record<RecommendedAction["priority"], string> = {
  P1: "severity-critical",
  P2: "severity-high",
  P3: "severity-medium",
};

export default function ActionsPage() {
  const { analysis } = useStore();
  const actions = analysis?.recommended_actions ?? [];

  const [completed, setCompleted] = useState<Set<string>>(new Set());
  const [priority, setPriority] = useState<RecommendedAction["priority"] | "all">("all");

  const rows = useMemo(
    () => actions.filter((a) => priority === "all" || a.priority === priority),
    [actions, priority],
  );

  const toggle = (id: string) => {
    setCompleted((s) => {
      const next = new Set(s);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const openCount = actions.length - completed.size;
  const key = (a: RecommendedAction) => `${a.title}::${a.owner}`;

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Actions"
        title="Recommended Actions"
        description="This-week action list derived from top risks. Mark-complete is local in M1; persistence arrives in M3."
      />

      <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatTile label="Total" value={String(actions.length)} />
        <StatTile label="Open" value={String(openCount)} tone={openCount ? "bad" : "good"} />
        <StatTile label="P1" value={String(actions.filter((a) => a.priority === "P1").length)} tone="bad" />
        <StatTile label="Completed" value={String(completed.size)} tone="good" />
      </section>

      <div className="panel-sm flex flex-wrap gap-3 items-end">
        <label className="min-w-[180px] flex flex-col gap-1">
          <span className="text-[0.68rem] uppercase tracking-[0.12em] text-muted font-bold">Priority</span>
          <select value={priority} onChange={(e) => setPriority(e.target.value as RecommendedAction["priority"] | "all")}>
            <option value="all">All</option>
            <option value="P1">P1</option>
            <option value="P2">P2</option>
            <option value="P3">P3</option>
          </select>
        </label>
      </div>

      <div className="space-y-3">
        {rows.length ? (
          rows.map((a) => {
            const id = key(a);
            const done = completed.has(id);
            return (
              <article
                key={id}
                className={`panel-sm transition-opacity ${done ? "opacity-60" : ""}`}
              >
                <div className="flex items-start gap-3">
                  <input
                    type="checkbox"
                    checked={done}
                    onChange={() => toggle(id)}
                    aria-label={`Mark ${a.title} complete`}
                    style={{ width: "1.1rem", marginTop: "0.25rem" }}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-3">
                      <div className={`font-bold text-ink ${done ? "line-through" : ""}`}>
                        {a.title}
                      </div>
                      <span className={`badge ${PRIORITY_TONE[a.priority]} shrink-0`}>
                        {a.priority}
                      </span>
                    </div>
                    <p className="mt-2 text-sm text-muted leading-relaxed">{a.rationale}</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <Pill>Owner: {a.owner}</Pill>
                      <Pill>Due in {a.due_in_days}d</Pill>
                    </div>
                  </div>
                </div>
              </article>
            );
          })
        ) : (
          <EmptyState
            title={actions.length ? "No actions match filters" : "No actions yet"}
            hint={actions.length ? "Change the priority filter." : "Run an analysis to generate this-week actions."}
          />
        )}
      </div>
    </div>
  );
}

function StatTile({ label, value, tone = "neutral" }: { label: string; value: string; tone?: "neutral" | "bad" | "good" }) {
  const color = tone === "bad" ? "text-danger" : tone === "good" ? "text-accent" : "text-ink";
  return (
    <div className="panel-sm">
      <div className="text-[0.7rem] uppercase tracking-[0.14em] text-muted font-bold mb-2">{label}</div>
      <div className={`text-2xl font-extrabold ${color}`}>{value}</div>
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
