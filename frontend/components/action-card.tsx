import type { RecommendedAction } from "@/lib/types";

type Props = {
  action: RecommendedAction;
};

const PRIORITY_TONE: Record<RecommendedAction["priority"], string> = {
  P1: "severity-critical",
  P2: "severity-high",
  P3: "severity-medium",
};

export function ActionCard({ action }: Props) {
  return (
    <article className="panel-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="font-bold text-ink">{action.title}</div>
        <span className={`badge ${PRIORITY_TONE[action.priority]} shrink-0`}>
          {action.priority}
        </span>
      </div>
      <p className="mt-2 text-sm text-muted leading-relaxed">{action.rationale}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Pill>Owner: {action.owner}</Pill>
        <Pill>Due in {action.due_in_days} day{action.due_in_days === 1 ? "" : "s"}</Pill>
      </div>
    </article>
  );
}

function Pill({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold bg-white/5 text-muted">
      {children}
    </span>
  );
}
